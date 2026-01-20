#!/usr/bin/python3

import os
from fs.tarfs import TarFS

import fs

from virt.virt_factory import VirtFactory
from virt.volume import Volume, generate_day0_volume_name
from virt.domain_libvirt import DomainLibvirt
from virt.network import DomainNetworks

_ncs = __import__('_ncs')

VMX_EXTRA_MGMT_NETWORKS = ['int']


@VirtFactory.register_domain_networks('vMX')
class VmxDomainNetworks(DomainNetworks):

    def extra_mgmt_networks(self, action, output, device):
        if not device.control_plane_id:
            for network_name in VMX_EXTRA_MGMT_NETWORKS:
                self._extra_network(action, output, [ device.id ],
                        f'{network_name}-{device.id}',
                        None, (0xfc, device.id))


@VirtFactory.register_domain('vMX')
class VmxDomain(DomainLibvirt):

    MGMT_IFACE_TYPE = 'virtio'
    DATA_IFACE_TYPE = 'virtio'
    SHUTDOWN_SUPPORTED = False
    INCLUDE_NULL_IFACES = True

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        xml_builder.add_extra_mgmt_ifaces(VMX_EXTRA_MGMT_NETWORKS,
                device.control_plane_id or device.id, self.MGMT_IFACE_TYPE)

    def add_day0_device(self, xml_builder, storage_pool):
        super().add_day0_device(xml_builder, storage_pool)

    def _has_data_plane(self, device):
        return bool(device.control_plane_id)


@VirtFactory.register_volume('vMX')
class VmxVolume(Volume):
    def _load_templates(self):
        super()._load_templates()
        self._templates.load_template('images', 'junos-vmx-loader.conf')

    def _create_day0_image(self, file_name, variables, _):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file, False)

        self._log.info('Writing day0 file to partition')
        self._log.debug(f'/config/juniper.conf:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            with TarFS(flash_drive.openbin('/vmm-config.tgz', 'wb'),
                                write=True, compression='gz') as tarfile:
                tarfile.makedir('/config')
                tarfile.writetext('/config/juniper.conf', day0_str)

                tarfile.makedir('/boot')
                tarfile.writetext('/boot/loader.conf',
                        self._templates.apply_template(
                            'junos-vmx-loader.conf', {}))

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str
