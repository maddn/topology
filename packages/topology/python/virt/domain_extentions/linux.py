#!/usr/bin/python3

from io import BytesIO

import pycdlib

from virt.virt_factory import VirtFactory
from virt.network import generate_ip_address
from virt.volume import Volume

_ncs = __import__('_ncs')


@VirtFactory.register_volume('Linux')
class LinuxVolume(Volume):
    def _load_templates(self):
        super()._load_templates()
        self._templates.load_template('cloud-init', 'meta-data.yaml')
        self._templates.load_template('cloud-init', 'network-config.yaml')
        self._templates.load_template('cloud-init', 'ethernet.yaml')

    def _get_cloud_init_ethernets(self, device_id):
        network_config = ''
        for iface_id in range(self._network_mgr.get_num_device_ifaces()):
            network = self._network_mgr.get_iface_network_id(device_id,
                    iface_id) or self._network_mgr.get_iface_bridge_name(
                    device_id, iface_id)

            if network is None:
                continue

            ip_address_start = self._network_mgr.get_network(network)
            if ip_address_start is None:
                continue

            ip_address = generate_ip_address(ip_address_start, device_id)
            network_config += self._templates.apply_template(
                'ethernet.yaml', {
                    'iface-id': iface_id,
                    'ip-address': ip_address,
                    'mac-address': self._resource_mgr.\
                            generate_mac_address(device_id, iface_id, True)
                    })
            self._network_mgr.write_iface_data(device_id, iface_id, [
                ('ip-address', ip_address)])
        return network_config

    def _create_day0_image(self, file_name, variables, device_id):
        meta_data = self._templates.apply_template('meta-data.yaml', variables)
        network_config = self._templates.apply_template(
                'network-config.yaml',variables)
        network_config += self._get_cloud_init_ethernets(device_id)
        user_data = self._templates.apply_template(file_name, variables)

        self._log.info('Writing cloud-init files to iso stream')
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='cidata')

        self._add_iso_file(iso, meta_data, 'meta-data')
        self._add_iso_file(iso, network_config, 'network-config')
        self._add_iso_file(iso, user_data, 'user-data')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()
