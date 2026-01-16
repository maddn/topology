from abc import abstractmethod
from libvirt import (VIR_DOMAIN_UNDEFINE_NVRAM)
from ncs import maapi
from virt.domain import Domain
from virt.network import generate_network_id, generate_network_name
from virt.template import xml_to_string
from virt.topology_status import get_hypervisor_output_node, write_node_data
from virt.volume import generate_volume_name, generate_day0_volume_name
import ncs


class DomainXmlBuilder():
    def __init__(self, device_id, device_name,
            resource_mgr, network_mgr, templates):
        self._templates = templates
        self._resource_mgr = resource_mgr
        self._network_mgr = network_mgr
        self._device_name = device_name
        self._device_id = int(device_id)
        self._domain_xml_devices = None
        self.domain_xml = None

    def _generate_mac_address(self, last_octet):
        return self._resource_mgr.generate_mac_address(
                self._device_id, last_octet, True)

    def _generate_iface_dev_name(self, other_id):
        return f'vtap-{self._device_id}-{other_id}'

    def _get_disk_xml(self, volume_name, pool_name, base_image_name):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': 'disk',
            'file-format': 'qcow2',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': 'vda',
            'backing-store': 'volume' if base_image_name is not None else '',
            'base-image-name': base_image_name,
            'bus': 'virtio'})

    def _get_raw_disk_xml(self, volume_name, pool_name, device_type, target, bus):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': device_type,
            'file-format': 'raw',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': target,
            'bus': bus})

    def _get_iface_xml(self, network_id, dev_name, mac_address, model_type,
            bridge_name='', source_udp='', dest_udp=''):
        return self._templates.apply_xml_template('interface.xml', {
            'interface-type': 'udp' if dest_udp else 'bridge' if bridge_name else 'network',
            'mac-address': mac_address,
            'network': generate_network_name(network_id) if network_id and not dest_udp else '',
            'bridge': bridge_name if bridge_name and not dest_udp else '',
            'source': source_udp if source_udp else '',
            'dest': dest_udp if dest_udp else '',
            'dev': dev_name if not dest_udp else '',
            'model-type': model_type})

    def create_base(self, vcpus, memory, template):
        self.domain_xml = self._templates.apply_xml_template(
                f'{template}.xml', {
                    'id': f'{self._device_id:02d}',
                    'device-name': self._device_name,
                    'vcpus': vcpus,
                    'memory': memory})
        self._domain_xml_devices = self.domain_xml.find('devices')

    def add_mgmt_iface(self, model_type):
        mac_address = self._generate_mac_address(0xff)
        mgmt_bridge = self._resource_mgr.mgmt_bridge
        mgmt_ip_address = self._resource_mgr.generate_mgmt_ip_address(
                self._device_id)
        iface_dev_name = self._generate_iface_dev_name(mgmt_bridge)

        self._domain_xml_devices.append(self._get_iface_xml(
            None, iface_dev_name, mac_address, model_type, mgmt_bridge))

        return (mgmt_ip_address, mac_address, iface_dev_name)

    def add_extra_mgmt_ifaces(self, ifaces, device_id=None, dev_type='virtio'):
        for (idx, network_name) in enumerate(ifaces):
            network_id = f'{network_name}-{device_id}' if (
                    device_id) else network_name
            self._domain_xml_devices.append(self._get_iface_xml(network_id,
                self._generate_iface_dev_name(f'{network_name}'),
                self._generate_mac_address(0xfe-idx),
                dev_type))

    def add_disk(self, storage_pool, base_image):
        self._domain_xml_devices.append(self._get_disk_xml(
            generate_volume_name(self._device_name), storage_pool, base_image))

    def add_day0_cdrom(self, storage_pool):
        self._domain_xml_devices.append(self._get_raw_disk_xml(
            generate_day0_volume_name(self._device_name), storage_pool,
            'cdrom', 'hdc', 'sata'))

    def add_day0_disk(self, storage_pool):
        self._domain_xml_devices.append(self._get_raw_disk_xml(
            generate_day0_volume_name(self._device_name), storage_pool,
            'disk', 'vdb', 'virtio'))

    def add_day0_usb(self, storage_pool):
        self._domain_xml_devices.append(self._get_raw_disk_xml(
            generate_day0_volume_name(self._device_name), storage_pool,
            'disk', 'sdb', 'usb'))

    def add_data_ifaces(self, include_null_interfaces, model_type,
            min_ifaces = 0, first_iface = 0, device_id = None):
        for iface_id in range(first_iface,
                self._network_mgr.get_num_device_ifaces()):
            bridge_name = self._network_mgr.get_iface_bridge_name(
                    device_id or self._device_id, iface_id)
            network_id = self._network_mgr.get_iface_network_id(
                    device_id or self._device_id, iface_id)
            (source_udp, dest_udp) = self._network_mgr.get_network_udp_ports(
                    device_id or self._device_id, iface_id)


            if (bridge_name or network_id or include_null_interfaces
                    or iface_id < (min_ifaces - 1)):
                iface_dev_name = self._generate_iface_dev_name(iface_id)
                mac_address = self._generate_mac_address(iface_id)

                self._domain_xml_devices.append(self._get_iface_xml(
                    network_id or not bridge_name and
                            generate_network_id(self._device_id, None),
                    iface_dev_name, mac_address, model_type, bridge_name,
                    source_udp, dest_udp))

                if network_id or bridge_name:
                    self._network_mgr.write_iface_data(
                        device_id or self._device_id, iface_id, [
                                ('id', iface_id),
                                ('host-interface', iface_dev_name),
                                ('mac-address', mac_address)])


class DomainLibvirt(Domain):

    DATA_IFACE_TYPE = 'virtio'
    MGMT_IFACE_TYPE = 'virtio'
    INCLUDE_NULL_IFACES = False
    MIN_DATA_IFACES = 0
    FIRST_IFACE_ID = 0
    SHUTDOWN_SUPPORTED = True

    def _load_templates(self):
        self._templates.load_template('templates', 'interface.xml')
        self._templates.load_template('templates', 'disk.xml')
        self._templates.load_template('templates', 'host-interface.xml')

    def load_device_templates(self, devices):
        device_templates = set(self._dev_defs[device.definition].template
                for device in devices)
        for template in device_templates:
            self._templates.load_template('images', f'{template}.xml')

    @abstractmethod
    def add_extra_mgmt_interfaces(self, xml_builder, device):
        pass

    @abstractmethod
    def add_day0_device(self, xml_builder, storage_pool):
        xml_builder.add_day0_disk(storage_pool)

    def _has_data_plane(self, device):
        return True

    def _define(self, device):
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        self._log.info(f'[{libvirt.name}] Defining domain {device_name}')

        dev_def = self._dev_defs[device.definition]
        self._templates.load_template('images', f'{dev_def.template}.xml')
        xml_builder = DomainXmlBuilder(int(device.id), device_name,
                self._resource_mgr, self._network_mgr, self._templates)

        xml_builder.create_base(dev_def.vcpus, dev_def.memory, dev_def.template)
        xml_builder.add_disk(dev_def.storage_pool, dev_def.base_image
                if dev_def.base_image_type == 'backing-store' else None)
        if dev_def.day0_file is not None:
            self.add_day0_device(xml_builder, dev_def.storage_pool)

        (mgmt_ip_address, mac_address, iface_dev_name
                ) = xml_builder.add_mgmt_iface(self.MGMT_IFACE_TYPE)
        write_node_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', iface_dev_name)])

        self.add_extra_mgmt_interfaces(xml_builder, device)

        if self._has_data_plane(device):
            xml_builder.add_data_ifaces(
                    self.INCLUDE_NULL_IFACES, #dev_def.device_type in ('XRv-9000', 'vJunos-Evolved', 'vMX'),
                    self.DATA_IFACE_TYPE, #'e1000' if dev_def.device_type in ('XRv-9000', 'IOSv') else 'virtio',
                    self.MIN_DATA_IFACES, #if dev_def.device_type == 'IOSv' else 0,
                    self.FIRST_IFACE_ID, #1 if dev_def.device_type == 'IOSv' else 0,
                    device.control_plane_id)

        domain_xml_str = xml_to_string(xml_builder.domain_xml)
        self._log.info(domain_xml_str)

        libvirt.conn.defineXML(domain_xml_str)

    def _undefine(self, device):
        return self._action('undefine', device)

    def is_active(self, device):
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        if device_name in libvirt.domains:
            return libvirt.conn.lookupByName(device_name).isActive()
        return False

    def shutdown_supported(self):
        return self.SHUTDOWN_SUPPORTED

    def _action(self, action, *args):
        device, = args
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        if device_name in libvirt.domains:
            domain = libvirt.conn.lookupByName(device_name)
            if self._action_allowed(domain.isActive(), action):
                self._log.info(f'[{libvirt.name}] '
                               f'Running {action} on domain {device_name} ')
                if action == 'undefine':
                    domain.undefineFlags(VIR_DOMAIN_UNDEFINE_NVRAM)
                else:
                    domain_action_method = getattr(domain, action)
                    domain_action_method()
                get_hypervisor_output_node(
                        self._output, libvirt.name).domains.create(device_name)
                return True
        return False
