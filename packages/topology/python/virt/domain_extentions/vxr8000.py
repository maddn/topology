#!/usr/bin/python3

from virt.virt_factory import VirtFactory
from virt.volume import Volume, generate_day0_volume_name
from virt.domain_vxr import DomainVxr


@VirtFactory.register_domain('VXR-8000')
class Vxr8000Domain(DomainVxr):

    IFACE_PREFIX = 'FourHundredGigE0/0/0'
    MGMT_IFACE = 'eth0'


@VirtFactory.register_volume('VXR-8000')
class Vxr8000Volume(Volume):

    def _create_day0_image(self, file_name, variables, _):
        image_str = self._templates.apply_template(
            file_name, variables)

        with open(generate_day0_volume_name(variables['device-name']),
                  'wt', encoding='utf-8') as file:
            file.write(image_str)

        return image_str.encode()
