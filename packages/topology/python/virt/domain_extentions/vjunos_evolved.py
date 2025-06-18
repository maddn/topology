#!/usr/bin/python3

import os
from fs.tarfs import TarFS

import fs

from virt.virt_factory import VirtFactory
from virt.volume import Volume, generate_day0_volume_name
from virt.domain_libvirt import DomainLibvirt
from virt.network import DomainNetworks

_ncs = __import__('_ncs')

VJUNOS_EXTRA_MGMT_NETWORKS = ['pfe', 'rpio', 'rpio', 'pfe']


@VirtFactory.register_domain_networks('vJunos-Evolved')
class VJunosEvolvedDomainNetworks(DomainNetworks):

    def extra_mgmt_networks(self, action, output, device):
        for (idx, network_name) in enumerate(
                set(VJUNOS_EXTRA_MGMT_NETWORKS)):
            self._extra_network(action, output,
                    [ device.id ], f'{network_name}-{device.id}',
                    None, (0xfd, 0xff-idx))


@VirtFactory.register_domain('vJunos-Evolved')
class VJunosEvolvedDomain(DomainLibvirt):

    MGMT_IFACE_TYPE = 'virtio'
    DATA_IFACE_TYPE = 'virtio'
    INCLUDE_NULL_IFACES = True

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        xml_builder.add_extra_mgmt_ifaces(
                VJUNOS_EXTRA_MGMT_NETWORKS, device.id, self.MGMT_IFACE_TYPE)

    def add_day0_device(self, xml_builder, storage_pool):
        xml_builder.add_day0_usb(storage_pool)


@VirtFactory.register_volume('vJunos-Evolved')
class VJunosEvolvedVolume(Volume):

    def _create_day0_image(self, file_name, variables, _):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file)

        self._log.info('Writing day0 file to partition')
        self._log.info(f'/config/juniper.conf:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            with TarFS(flash_drive.openbin('/vmm-config.tgz', 'wb'),
                                write=True, compression='gz') as tarfile:
                tarfile.makedir('/config')
                tarfile.writetext('/config/juniper.conf', day0_str)

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str
