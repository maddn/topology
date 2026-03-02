#!/usr/bin/python3

from io import BytesIO

import pycdlib

from virt.virt_factory import VirtFactory
from virt.volume import Volume
from virt.domain_libvirt import DomainLibvirt

_ncs = __import__('_ncs')


@VirtFactory.register_domain('Catalyst-8000V')
class Catalyst8000VDomain(DomainLibvirt):

    FIRST_IFACE_ID = 2
    INCLUDE_NULL_IFACES = True

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        pass

    def add_day0_device(self, xml_builder, storage_pool):
        xml_builder.add_day0_cdrom(storage_pool)


@VirtFactory.register_volume('Catalyst-8000V')
class Catalyst8000VVolume(Volume):

    def _create_day0_image(self, file_name, variables, _):
        day0_str = self._templates.apply_template(file_name, variables)
        self._log.info('Writing day0 file to iso stream')
        self._log.debug(f'iosxe_config.txt:\n{day0_str}')

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='config-1')
        self._add_iso_file(iso, day0_str, 'iosxe_config.txt')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()
