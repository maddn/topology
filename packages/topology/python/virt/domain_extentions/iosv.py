#!/usr/bin/python3

import os
import fs

from virt.virt_factory import VirtFactory
from virt.volume import Volume, generate_day0_volume_name
from virt.domain_libvirt import DomainLibvirt

_ncs = __import__('_ncs')


@VirtFactory.register_domain('IOSv')
class IOSvDomain(DomainLibvirt):

    MGMT_IFACE_TYPE = 'e1000'
    DATA_IFACE_TYPE = 'e1000'
    MIN_DATA_IFACES = 4
    FIRST_IFACE_ID = 1
    SHUTDOWN_SUPPORTED = False

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        pass

    def add_day0_device(self, xml_builder, storage_pool):
        super().add_day0_device(xml_builder, storage_pool)


@VirtFactory.register_volume('IOSv')
class IOSvVolume(Volume):

    def _create_day0_image(self, file_name, variables, _):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file)

        self._log.info('Writing day0 file to partition')
        self._log.info(f'ios_config.txt:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            flash_drive.writetext('/ios_config.txt', day0_str)

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str
