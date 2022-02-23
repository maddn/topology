#!/usr/bin/python3
from collections import defaultdict
from io import BytesIO
from ipaddress import IPv4Address
from time import sleep
from xml.etree.ElementTree import fromstring, tostring
from xml.dom.minidom import parseString
import os
import re
import pycdlib
from ncs.dp import Action
from ncs import maapi, maagic, OPERATIONAL
from virt.libvirt_connection import LibvirtConnection

PYTHON_DIR = os.path.dirname(__file__)
XRV9K_EXTRA_MGMT_NETWORKS = ['ctrl', 'host']


def generate_network_id(device_id, other_id):
    return f'{device_id}-{other_id or "null"}'

def generate_network_name(network_id):
    return f'net-{network_id}'

def generate_bridge_name(network_id):
    return f'vbr-{network_id}'

def generate_volume_name(device_name):
    return f'{device_name}.qcow2'

def generate_day0_volume_name(device_name):
    return f'{device_name}-day0.iso'

def generate_iface_dev_name(device_id, other_id):
    return f'veth-{device_id}-{other_id}'

def sort_link_device_ids(device_ids):
    return tuple(sorted(device_ids))

def xml_to_string(xml):
    xml_stripped = re.sub(r'>\s+<', '><', tostring(xml, 'unicode'))
    return parseString(xml_stripped).toprettyxml('  ')


def write_oper_data(path, leaf_value_pairs):
    with maapi.single_write_trans('admin', 'python', db=OPERATIONAL) as trans:
        for leaf, value in leaf_value_pairs:
            if value is None:
                trans.safe_delete(f'{path}/{leaf}')
            else:
                trans.set_elem(value, f'{path}/{leaf}')
        trans.apply()

def nso_device_onboard(device_name, ip_address):
    with maapi.single_write_trans('admin', 'python') as trans:
        root = maagic.get_root(trans)
        device = root.devices.device.create(device_name)
        device.address = ip_address
        device.device_type.cli.ned_id = 'cisco-iosxr-cli-7.33'
        device.authgroup = 'cisco'
        device.state.admin_state = 'unlocked'
        device.ssh_algorithms.public_key.create('rsa-sha2-256')
        trans.apply()


class ResourceManager():
    def __init__(self, topology, hypervisor):
        self._mac_address_format = hypervisor.mac_address_format
        self._mgmt_ip_address_start = hypervisor.management_ip_address_start
        self._mgmt_bridge = hypervisor.management_bridge

        self._devices = {device.device_name:int(device.id)
                         for device in topology.devices.device}
        self._max_device_id = max(self._devices.values())
        self._networks = {}

        for link in topology.links.link:
            iface_ids = ((self._devices[link.z_end_device],  #a-end-interface-id
                          self._devices[link.a_end_device])) #z-end-interface-id
            device_ids = sort_link_device_ids(iface_ids)
            self._networks[device_ids] = (
                generate_network_id(*device_ids),
                self.generate_mac_address(*device_ids),
                iface_ids)

    def _get_link_device_ids(self, link):
        return sort_link_device_ids((self._devices[link.a_end_device],
                                     self._devices[link.z_end_device]))

    def get_link_network(self, link):
        return self._networks[self._get_link_device_ids(link)]

    def get_iface_network_id(self, device_id, iface_id):
        return self._networks.get(sort_link_device_ids((device_id, iface_id)),
                [generate_network_id(device_id, None)])[0]

    def get_mgmt_bridge(self):
        return self._mgmt_bridge

    def get_num_device_ifaces(self):
        return self._max_device_id + 1

    def generate_mac_address(self, pen_octet, ult_octet):
        return self._mac_address_format.format(pen_octet, ult_octet)

    def generate_mgmt_ip_address(self, device_id):
        return str(IPv4Address(self._mgmt_ip_address_start) + device_id)


class Templates():
    def __init__(self):
        self.templates = {}

    def _remove_nodes_with_empty_attributes(self, element):
        for child in list(element):
            if any(value == '' for (attrib, value) in child.items()):
                element.remove(child)
            else:
                self._remove_nodes_with_empty_attributes(child)

    def _clean_xml(self, xml_str):
        xml = fromstring(xml_str)
        self._remove_nodes_with_empty_attributes(xml)
        return xml_to_string(xml)

    def _apply_template(self, template_name, variables):
        return self.templates[template_name].format_map(
                defaultdict(str, variables))

    def apply_template(self, template_name, variables):
        is_xml = os.path.splitext(template_name) == '.xml'
        result = self._apply_template(template_name, variables)
        return self._clean_xml(result) if is_xml else result

    def apply_xml_template(self, template_name, variables):
        return fromstring(self.apply_template(template_name, variables))

    def load_template(self, path, filename):
        with open(f'{PYTHON_DIR}/{path}/{filename}',
                'r', encoding='utf8') as template_file:
            self.templates[filename] = str(template_file.read())


class DomainXmlBuilder():
    def __init__(self, device_id, device_name, resource_mgr, templates):
        self._templates = templates
        self._resource_mgr = resource_mgr
        self._device_name = device_name
        self._device_id = device_id
        self._domain_xml_devices = None
        self.domain_xml = None

    def _generate_mac_address(self, last_octet):
        return self._resource_mgr.generate_mac_address(
                self._device_id, last_octet)

    def _generate_iface_dev_name(self, other_id):
        return generate_iface_dev_name(self._device_id, other_id)

    def _get_disk_xml(self, volume_name, pool_name):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': 'disk',
            'file-format': 'qcow2',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': 'vda',
            'bus': 'virtio'})

    def _get_cdrom_xml(self, volume_name, pool_name):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': 'cdrom',
            'file-format': 'raw',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': 'vdc',
            'bus': 'ide'})

    def _get_iface_xml(self, network_id, dev_name, mac_address, model_type,
            bridge_name=''):
        return self._templates.apply_xml_template('interface.xml', {
            'interface-type': 'bridge' if bridge_name else 'network',
            'mac-address': mac_address,
            'network': generate_network_name(network_id) if network_id else '',
            'bridge': bridge_name,
            'dev': dev_name,
            'model-type': model_type})

    def create_base(self, vcpus, memory, template):
        self.domain_xml = self._templates.apply_xml_template(
                f'{template}.xml', {
                    'id': self._device_id,
                    'device-name': self._device_name,
                    'vcpus': vcpus,
                    'memory': memory})
        self._domain_xml_devices = self.domain_xml.find('devices')

    def add_mgmt_iface(self):
        mac_address = self._generate_mac_address(0xff)
        mgmt_bridge = self._resource_mgr.get_mgmt_bridge()
        mgmt_ip_address = self._resource_mgr.generate_mgmt_ip_address(
                self._device_id)
        iface_dev_name = self._generate_iface_dev_name(mgmt_bridge)

        self._domain_xml_devices.append(self._get_iface_xml(
            None, iface_dev_name, mac_address, 'e1000', mgmt_bridge))

        return (mgmt_ip_address, mac_address, iface_dev_name)

    def add_extra_mgmt_ifaces(self, ifaces):
        for (idx, network_id) in enumerate(ifaces):
            self._domain_xml_devices.append(self._get_iface_xml(network_id,
                self._generate_iface_dev_name(network_id),
                self._generate_mac_address(0xfe-idx),
                'e1000'))

    def add_disk(self, storage_pool):
        self._domain_xml_devices.append(self._get_disk_xml(
            generate_volume_name(self._device_name), storage_pool))

    def add_day0_disk(self, storage_pool):
        self._domain_xml_devices.append(self._get_cdrom_xml(
            generate_day0_volume_name(self._device_name), storage_pool))

    def add_data_ifaces(self):
        for iface_id in range(
                self._resource_mgr.get_num_device_ifaces()):
            network_id = self._resource_mgr.get_iface_network_id(
                    self._device_id, iface_id)

            self._domain_xml_devices.append(self._get_iface_xml(
                network_id,
                self._generate_iface_dev_name(iface_id),
                self._generate_mac_address(iface_id), 'virtio'))


class LibvirtObject(): #pylint: disable=too-few-public-methods
    def __init__(self, libvirt_conn, resource_mgr, log):
        self._libvirt = libvirt_conn
        self._resource_mgr = resource_mgr
        self._log = log
        self._templates = Templates()
        self._output = None
        self._load_templates()

    def _load_templates(self):
        pass

    @staticmethod
    def _action_allowed(active, action):
        return (active and action in ['shutdown', 'destroy'] or
                (not active) and action in ['create', 'undefine'])

    def _action(self, action, *args):
        pass

    def action(self, action, output, *args):
        self._output = output
        if hasattr(self, action):
            action_method = getattr(self, action)
            action_method(*args)
        else:
            self._action(action, *args)



class Network(LibvirtObject): #pylint: disable=too-few-public-methods
    def _load_templates(self):
        self._templates.load_template('templates', 'network.xml')

    def _define_network(self, network_id, mac_address, isolated=False):
        network_name = generate_network_name(network_id)
        bridge_name = generate_bridge_name(network_id)
        if network_name not in self._libvirt.networks:
            variables = {
                'network': network_name,
                'bridge': bridge_name,
                'mac-address': mac_address,
                'isolated': 'yes' if isolated else ''}

            network_xml_str = self._templates.apply_template(
                    'network.xml', variables)
            self._log.info(f'Defining network {network_name}')
            self._log.info(network_xml_str)
            self._libvirt.conn.networkDefineXML(network_xml_str)
            self._output.networks.create(network_name)
        return bridge_name

    def _action(self, action, *args):
        network_id, *_ = args
        if action in ['undefine', 'create', 'destroy']:
            network_name = generate_network_name(network_id)
            if network_name in self._libvirt.networks:
                network = self._libvirt.conn.networkLookupByName(network_name)
                if self._action_allowed(network.isActive(), action):
                    self._log.info(f'Running {action} on network {network_name}')
                    network_action_method = getattr(network, action)
                    network_action_method()
                    self._output.networks.create(network_name)
                    return True
        return False


class LinkNetwork(Network):
    def define(self, link):
        (network_id, mac_address, (a_end_iface_id, z_end_iface_id)
                ) = self._resource_mgr.get_link_network(link)
        host_bridge = self._define_network(network_id, mac_address)
        write_oper_data(link._path, [
            ('host-bridge', host_bridge),
            ('mac-address', mac_address),
            ('a-end-interface-id', a_end_iface_id),
            ('z-end-interface-id', z_end_iface_id)])

    def undefine(self, link):
        if self._action('undefine', link):
            write_oper_data(link._path, [
                ('host-bridge', None),
                ('mac-address', None),
                ('a-end-interface-id', None),
                ('z-end-interface-id', None)])

    def _action(self, action, *args):
        link, = args
        (network_id, _, _) = self._resource_mgr.get_link_network(link)
        return super()._action(action, network_id)


class IsolatedNetwork(Network):
    def define(self, device_id):
        network_id = generate_network_id(device_id, None)
        mac_address = self._resource_mgr.generate_mac_address(device_id, 0x00)
        self._define_network(network_id, mac_address)

    def _action(self, action, *args):
        device_id, = args
        network_id = generate_network_id(device_id, None)
        return super()._action(action, network_id)


class ManagementNetwork(Network):
    def define(self, network_id, idx):
        mac_address = self._resource_mgr.generate_mac_address(0xff, 0xfe-idx)
        self._define_network(network_id, mac_address)


class Volume(LibvirtObject):
    def _load_templates(self):
        self._templates.load_template('templates', 'volume.xml')

    def load_day0_templates(self, devices):
        for device in devices:
            if device.day0_file is not None:
                self._templates.load_template('images', device.day0_file)

    def _create_iosxr_day0_iso_image(self, filename, variables):
        day0_str = self._templates.apply_template(filename, variables)
        day0_byte_str = day0_str.encode()
        self._log.info('Writing day0 file to iso stream')
        self._log.info(day0_str)

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='config-1')
        iso.add_fp(BytesIO(day0_byte_str),
                len(day0_byte_str), '/iosxr_config.txt')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()

    def _create_day0_volume(self, volume_name, pool_name, file_name, variables):
        iso_byte_str = self._create_iosxr_day0_iso_image(file_name, variables)

        pool = self._libvirt.conn.storagePoolLookupByName(pool_name)
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': len(iso_byte_str),
            'format-type': 'raw'})

        self._log.info(f'Creating day0 volume {volume_name}')
        self._log.info(volume_xml_str)
        volume = pool.createXML(volume_xml_str)

        self._log.info(f'Uploading day0 iso to volume {volume_name}')
        stream = self._libvirt.conn.newStream()
        volume.upload(stream, 0, len(iso_byte_str))
        stream.send(iso_byte_str)
        stream.finish()
        self._output.volumes.create(volume_name)

    def _clone_volume(self, volume_name, pool_name, base_image_name):
        pool = self._libvirt.conn.storagePoolLookupByName(pool_name)
        base_image = pool.storageVolLookupByName(base_image_name)
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'format-type': 'qcow2'})

        self._log.info(f'Creating volume {volume_name} from {base_image_name}')
        self._log.info(volume_xml_str)
        pool.createXMLFrom(volume_xml_str, base_image)
        self._output.volumes.create(volume_name)

    def _delete_volume(self, pool, volume_name, volume_type='volume'):
        if volume_name and volume_name in self._libvirt.volumes[pool.name()]:
            volume = pool.storageVolLookupByName(volume_name)
            self._log.info(f'Running delete on {volume_type} {volume_name}')
            volume.delete()
            self._output.volumes.create(volume_name)

    def define(self, device):
        device_name = device.device_name
        self._clone_volume(generate_volume_name(device_name),
                device.storage_pool, device.base_image)

        if device.day0_file is not None:
            self._create_day0_volume(generate_day0_volume_name(device_name),
                    device.storage_pool, device.day0_file, {
                    'management-ip-address': self._resource_mgr.\
                            generate_mgmt_ip_address(int(device.id))})

    def undefine(self, device):
        if device.storage_pool in self._libvirt.volumes:
            device_name = device.device_name
            pool = self._libvirt.conn.storagePoolLookupByName(
                    device.storage_pool)
            self._delete_volume(pool, generate_volume_name(device_name))

            if device.day0_file is not None:
                day0_volume_name = generate_day0_volume_name(device_name)
                self._delete_volume(pool, day0_volume_name, 'day0 volume')


class Domain(LibvirtObject):
    def _load_templates(self):
        self._templates.load_template('templates', 'interface.xml')
        self._templates.load_template('templates', 'disk.xml')

    def load_device_templates(self, devices):
        for device in devices:
            self._templates.load_template('images', f'{device.template}.xml')

    def define(self, device):
        device_name = device.device_name
        self._log.info(f'Defining domain {device_name}')

        xml_builder = DomainXmlBuilder(int(device.id), device_name,
                self._resource_mgr, self._templates)

        xml_builder.create_base(device.vcpus, device.memory, device.template)
        xml_builder.add_disk(device.storage_pool)
        if device.day0_file is not None:
            xml_builder.add_day0_disk(device.storage_pool)

        (mgmt_ip_address, mac_address, iface_dev_name
                ) = xml_builder.add_mgmt_iface()
        write_oper_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', iface_dev_name)])

        if device.device_type == 'XRv-9000':
            xml_builder.add_extra_mgmt_ifaces(XRV9K_EXTRA_MGMT_NETWORKS)

        xml_builder.add_data_ifaces()

        domain_xml_str = xml_to_string(xml_builder.domain_xml)
        self._log.info(domain_xml_str)

        self._libvirt.conn.defineXML(domain_xml_str)
        self._output.domains.create(device_name)

        self._log.info(f'Creating device {device_name} in NSO')
        nso_device_onboard(device_name, mgmt_ip_address)

    def undefine(self, device):
        if self._action('undefine', device):
            write_oper_data(device.management_interface._path, [
                    ('ip-address', None),
                    ('mac-address', None),
                    ('host-interface', None)])

    def is_active(self, device):
        device_name = device.device_name
        if device_name in self._libvirt.domains:
            return self._libvirt.conn.lookupByName(device_name).isActive()
        return False

    def _action(self, action, *args):
        device, = args
        device_name = device.device_name
        if device_name in self._libvirt.domains:
            domain = self._libvirt.conn.lookupByName(device_name)
            if self._action_allowed(domain.isActive(), action):
                self._log.info(f'Running {action} on domain {device_name}')
                domain_action_method = getattr(domain, action)
                domain_action_method()
                self._output.domains.create(device_name)
                return True
        return False


class Topology():
    def __init__(self, libvirt_conn, topology, hypervisor, log, output):
        self._devices = topology.devices.device
        self._links = topology.links.link
        self._output = output

        args = (libvirt_conn, ResourceManager(topology, hypervisor), log)

        self._mgmt_network = ManagementNetwork(*args)
        self._link_network = LinkNetwork(*args)
        self._isolated_network = IsolatedNetwork(*args)
        self._volume = Volume(*args)
        self._domain = Domain(*args)

        self._volume.load_day0_templates(self._devices)
        self._domain.load_device_templates(self._devices)

    def action(self, action):
        output = self._output.libvirt_action.create()
        output.action = action

        if any(device.device_type == 'XRv-9000' for device in self._devices):
            for (idx, network_id) in enumerate(XRV9K_EXTRA_MGMT_NETWORKS):
                self._mgmt_network.action(action, output, network_id, idx)

        for link in self._links:
            self._link_network.action(action, output, link)

        for device in self._devices:
            self._isolated_network.action(action, output, int(device.id))
            self._domain.action(action, output, device)
            self._volume.action(action, output, device)

    def wait_for_shutdown(self):
        timer = 0
        while any(self._domain.is_active(device)
                  for device in self._devices) and timer < 60:
            sleep(10)
            timer += 10


class LibvirtAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        topology = maagic.get_node(trans, kp[1:])
        hypervisor_name = topology.libvirt.hypervisor

        if hypervisor_name is None:
            raise Exception('No hypervisor defined for this topology')

        hypervisor = maagic.get_root(
                trans).topologies.libvirt.hypervisor[hypervisor_name]

        libvirt_conn = LibvirtConnection()
        libvirt_conn.connect(hypervisor.url)
        libvirt_conn.populate_cache()

        topology = Topology(
                libvirt_conn, topology, hypervisor, self.log, output)

        action = name
        if name == 'start':
            action = 'create'
        elif name == 'stop':
            topology.action('shutdown')
            topology.wait_for_shutdown()
            action = 'destroy'

        topology.action(action)
