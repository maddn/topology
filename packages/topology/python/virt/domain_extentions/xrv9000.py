#!/usr/bin/python3

from io import BytesIO

import pycdlib

from virt.virt_factory import VirtFactory
from virt.volume import Volume
from virt.domain_libvirt import DomainLibvirt
from virt.network import TopologyNetworks

_ncs = __import__('_ncs')

XRV9K_EXTRA_MGMT_NETWORKS = ['ctrl', 'host']


@VirtFactory.register_topology_networks('XRv-9000')
class XRv9000TopologyNetworks(TopologyNetworks):

    def extra_mgmt_networks(self, action, output, device_ids):
        for (idx, network_id) in enumerate(XRV9K_EXTRA_MGMT_NETWORKS):
            self._extra_network(action, output,
                device_ids, network_id, None, (0xff, 0xff-idx))


@VirtFactory.register_domain('XRv-9000')
class XRv9000Domain(DomainLibvirt):

    MGMT_IFACE_TYPE = 'e1000'
    DATA_IFACE_TYPE = 'e1000'
    INCLUDE_NULL_IFACES = True

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        xml_builder.add_extra_mgmt_ifaces(
                XRV9K_EXTRA_MGMT_NETWORKS, None, self.MGMT_IFACE_TYPE)

    def add_day0_device(self, xml_builder, storage_pool):
        xml_builder.add_day0_cdrom(storage_pool)


@VirtFactory.register_volume('XRv-9000')
class XRv9000Volume(Volume):

    def _create_day0_image(self, file_name, variables, _):
        day0_str = self._templates.apply_template(file_name, variables)
        self._log.info('Writing day0 file to iso stream')

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='config-1')
        self._add_iso_file(iso, day0_str, 'iosxr_config.txt')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()
