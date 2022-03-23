#!/usr/bin/python3
from collections import defaultdict
from io import BytesIO
from ipaddress import IPv4Address
from time import sleep
from xml.etree.ElementTree import fromstring, tostring
from xml.dom.minidom import parseString

import base64
import crypt
import os
import re

import pycdlib

import ncs
from ncs.dp import Action
from ncs import maapi, maagic, OPERATIONAL
from virt.libvirt_connection import LibvirtConnection
from virt.topology_status import \
        update_status_after_action, schedule_topology_ping

_ncs = __import__('_ncs')

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

def generate_ip_address(ip_address_start, device_id):
    return str(IPv4Address(ip_address_start) + int(device_id)) if (
            ip_address_start is not None) else None

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

def nso_device_onboard(device):
    with maapi.single_write_trans('admin', 'python') as trans:
        device_context = maagic.get_node(trans, device._path)
        template_vars = ncs.template.Variables()
        template_vars.add('NAME', device_context.device_name)
        template = ncs.template.Template(device_context)
        template.apply('nso-device-template', template_vars)
        trans.apply()


class NetworkManager():
    def __init__(self, topology):
        self._devices = {device.device_name:int(device.id)
                         for device in topology.devices.device}
        self._max_device_id = max(self._devices.values())

        self._network_ifaces = {
                (self._devices[device], network.interface_id): network.name
                for network in topology.networks.network
                for device in network.devices}
        self._networks = {network.name: network.ip_address_start
                for network in topology.networks.network}

        self._link_networks = {}
        for link in topology.links.link:
            iface_ids = ((self._devices[link.z_end_device],  #a-end-interface-id
                          self._devices[link.a_end_device])) #z-end-interface-id
            device_ids = sort_link_device_ids(iface_ids)
            self._link_networks[device_ids] = (
                generate_network_id(*device_ids),
                iface_ids)

    def _get_link_device_ids(self, link):
        return sort_link_device_ids((self._devices[link.a_end_device],
                                     self._devices[link.z_end_device]))

    def get_link_network(self, link):
        device_ids = self._get_link_device_ids(link)
        return (*self._link_networks[device_ids], device_ids)

    def get_network(self, network_id):
        return self._networks[network_id]

    def get_iface_network_id(self, device_id, iface_id):
        return self._network_ifaces.get((device_id, iface_id),
                self._link_networks.get(
                    sort_link_device_ids((device_id, iface_id)), [None])[0])

    def get_num_device_ifaces(self):
        return self._max_device_id + 1


class ResourceManager():
    def __init__(self, hypervisor, username):
        self._username = username
        self._authgroups = maagic.get_root(hypervisor).devices.authgroups.group

        mgmt_network = hypervisor.management_network
        suffix = '{:02x}:{:02x}:{:02x}'
        self._mac_address_format = f'{hypervisor.mac_address_start}:{suffix}'
        self._mgmt_ip_address_start = mgmt_network.ip_address_start

        self.mgmt_bridge = mgmt_network.bridge
        self.mgmt_network_variables = {
            'gateway-address': mgmt_network.gateway_address,
            'dns-server': mgmt_network.dns_server_address
        }

    def generate_mac_address(self, pen_octet, ult_octet, is_iface=False):
        return self._mac_address_format.format(is_iface, pen_octet, ult_octet)

    def generate_mgmt_ip_address(self, device_id):
        return generate_ip_address(self._mgmt_ip_address_start, device_id)

    def get_authgroup_mapping(self, authgroup_name):
        authgroup = self._authgroups[authgroup_name]
        return authgroup.umap[self._username] if (
                self._username in authgroup.umap) else authgroup.default_map


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
        is_xml = os.path.splitext(template_name)[1] == '.xml'
        result = self._apply_template(template_name, variables)
        return self._clean_xml(result) if is_xml else result

    def apply_xml_template(self, template_name, variables):
        return fromstring(self.apply_template(template_name, variables))

    def load_template(self, path, filename):
        with open(f'{PYTHON_DIR}/{path}/{filename}',
                'r', encoding='utf8') as template_file:
            self.templates[filename] = str(template_file.read())


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
        return generate_iface_dev_name(self._device_id, other_id)

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

    def add_mgmt_iface(self, model_type):
        mac_address = self._generate_mac_address(0xff)
        mgmt_bridge = self._resource_mgr.mgmt_bridge
        mgmt_ip_address = self._resource_mgr.generate_mgmt_ip_address(
                self._device_id)
        iface_dev_name = self._generate_iface_dev_name(mgmt_bridge)

        self._domain_xml_devices.append(self._get_iface_xml(
            None, iface_dev_name, mac_address, model_type, mgmt_bridge))

        return (mgmt_ip_address, mac_address, iface_dev_name)

    def add_extra_mgmt_ifaces(self, ifaces):
        for (idx, network_id) in enumerate(ifaces):
            self._domain_xml_devices.append(self._get_iface_xml(network_id,
                self._generate_iface_dev_name(network_id),
                self._generate_mac_address(0xfe-idx),
                'e1000'))

    def add_disk(self, storage_pool, base_image):
        self._domain_xml_devices.append(self._get_disk_xml(
            generate_volume_name(self._device_name), storage_pool, base_image))

    def add_day0_disk(self, storage_pool):
        self._domain_xml_devices.append(self._get_cdrom_xml(
            generate_day0_volume_name(self._device_name), storage_pool))

    def add_data_ifaces(self, include_null_interfaces):
        for iface_id in range(self._network_mgr.get_num_device_ifaces()):
            network_id = self._network_mgr.get_iface_network_id(
                    self._device_id, iface_id)

            if network_id is not None or include_null_interfaces:
                self._domain_xml_devices.append(self._get_iface_xml(
                    network_id or generate_network_id(self._device_id, None),
                    self._generate_iface_dev_name(iface_id),
                    self._generate_mac_address(iface_id), 'virtio'))


class LibvirtObject(): #pylint: disable=too-few-public-methods
    def __init__(self, libvirt_conn, resource_mgr, network_mgr, dev_defs, log):
        self._libvirt = libvirt_conn
        self._resource_mgr = resource_mgr
        self._network_mgr = network_mgr
        self._dev_defs = dev_defs
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
        (network_id, (a_end_iface_id, z_end_iface_id), device_ids
                ) = self._network_mgr.get_link_network(link)
        mac_address = self._resource_mgr.generate_mac_address(*device_ids)
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
        (network_id, _, _) = self._network_mgr.get_link_network(link)
        return super()._action(action, network_id)


class IsolatedNetwork(Network):
    def define(self, device_id):
        network_id = generate_network_id(device_id, None)
        mac_address = self._resource_mgr.generate_mac_address(device_id, 0x00)
        self._define_network(network_id, mac_address, isolated=True)

    def _action(self, action, *args):
        device_id, = args
        network_id = generate_network_id(device_id, None)
        return super()._action(action, network_id)


class ExtraNetwork(Network):
    def define(self, network_id, mac_octets):
        mac_address = self._resource_mgr.generate_mac_address(*mac_octets)
        self._define_network(network_id, mac_address)


class Volume(LibvirtObject):
    def _load_templates(self):
        self._templates.load_template('templates', 'volume.xml')
        self._templates.load_template('cloud-init', 'meta-data.yaml')
        self._templates.load_template('cloud-init', 'network-config.yaml')
        self._templates.load_template('cloud-init', 'ethernet.yaml')

    def load_day0_templates(self, devices):
        day0_templates = filter(None, set(self._dev_defs[
            device.definition].day0_file for device in devices))
        for template in day0_templates:
            self._templates.load_template('images', template)

    def _add_iso_file(self, iso, file_string, file_name):
        self._log.info(f'{file_name}:\n{file_string}')
        byte_str = file_string.encode()
        iso.add_fp(BytesIO(byte_str), len(byte_str), f'/{file_name}')

    def _create_iosxr_day0_iso_image(self, file_name, variables):
        day0_str = self._templates.apply_template(file_name, variables)
        self._log.info('Writing day0 file to iso stream')

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='config-1')
        self._add_iso_file(iso, day0_str, 'iosxr_config.txt')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()

    def _get_cloud_init_ethernets(self, device_id):
        network_config = ''
        for iface_id in range(self._network_mgr.get_num_device_ifaces()):
            network_id = self._network_mgr.get_iface_network_id(
                    device_id, iface_id)

            if network_id is not None:
                ip_address_start = self._network_mgr.get_network(network_id)

                if ip_address_start is not None:
                    network_config += self._templates.apply_template(
                        'ethernet.yaml', {
                            'iface-id': iface_id,
                            'ip-address': generate_ip_address(
                                ip_address_start, device_id),
                            'mac-address': self._resource_mgr.\
                                    generate_mac_address(
                                        device_id, iface_id, True)
                        })
        return network_config

    def _create_cloud_init_iso_image(self, device_id, file_name, variables):
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

    def _create_day0_volume(self, device_id, device_name, dev_def):
        volume_name = generate_day0_volume_name(device_name)
        mapping = self._resource_mgr.get_authgroup_mapping(dev_def.authgroup)

        variables = {
            'device-name': device_name,
            'ip-address': self._resource_mgr.generate_mgmt_ip_address(device_id),
            'mac-address': self._resource_mgr.generate_mac_address(
                device_id, 0xff, True),
            'username': mapping.remote_name,
            'password': crypt.crypt(_ncs.decrypt(mapping.remote_password),
                crypt.mksalt(crypt.METHOD_SHA512)),
            **self._resource_mgr.mgmt_network_variables}

        if dev_def.day0_upload_file:
            with open(dev_def.day0_upload_file, 'rb') as binary_file:
                byte_array = binary_file.read()
            variables['file-content'] = base64.b64encode(byte_array).decode()

        if dev_def.device_type == 'XRv-9000':
            iso_byte_str = self._create_iosxr_day0_iso_image(
                    dev_def.day0_file, variables)
        else:
            iso_byte_str = self._create_cloud_init_iso_image(
                    device_id, dev_def.day0_file, variables)

        pool = self._libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
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

    def _create_volume(self, volume_name, pool_name,
            base_image_name, clone, new_size):
        pool = self._libvirt.conn.storagePoolLookupByName(pool_name)
        base_image = pool.storageVolLookupByName(base_image_name)
        volume_size = base_image.info()[1] if not clone else ''
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': volume_size,
            'format-type': 'qcow2'})

        if clone:
            self._log.info(
                f'Creating volume {volume_name} from {base_image_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXMLFrom(volume_xml_str, base_image)
        else:
            self._log.info(f'Creating volume {volume_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXML(volume_xml_str)

        if new_size is not None:
            vol.resize(new_size*1024*1024*1024)
        self._output.volumes.create(volume_name)

    def _delete_volume(self, pool, volume_name, volume_type='volume'):
        if volume_name and volume_name in self._libvirt.volumes[pool.name()]:
            volume = pool.storageVolLookupByName(volume_name)
            self._log.info(f'Running delete on {volume_type} {volume_name}')
            volume.delete()
            self._output.volumes.create(volume_name)

    def define(self, device):
        dev_def = self._dev_defs[device.definition]
        device_name = device.device_name
        self._create_volume(generate_volume_name(device_name),
                dev_def.storage_pool, dev_def.base_image,
                dev_def.base_image_type == 'clone', dev_def.disk_size)

        if dev_def.day0_file is not None:
            self._create_day0_volume(int(device.id), device_name, dev_def)

    def undefine(self, device):
        dev_def = self._dev_defs[device.definition]
        device_name = device.device_name
        if dev_def.storage_pool in self._libvirt.volumes:
            pool = self._libvirt.conn.storagePoolLookupByName(
                    dev_def.storage_pool)
            self._delete_volume(pool, generate_volume_name(device_name))

            if dev_def.day0_file is not None:
                day0_volume_name = generate_day0_volume_name(device_name)
                self._delete_volume(pool, day0_volume_name, 'day0 volume')


class Domain(LibvirtObject):
    def _load_templates(self):
        self._templates.load_template('templates', 'interface.xml')
        self._templates.load_template('templates', 'disk.xml')

    def load_device_templates(self, devices):
        device_templates = set(self._dev_defs[device.definition].template
                for device in devices)
        for template in device_templates:
            self._templates.load_template('images', f'{template}.xml')

    def define(self, device):
        device_name = device.device_name
        self._log.info(f'Defining domain {device_name}')

        dev_def = self._dev_defs[device.definition]
        xml_builder = DomainXmlBuilder(int(device.id), device_name,
                self._resource_mgr, self._network_mgr, self._templates)

        xml_builder.create_base(dev_def.vcpus, dev_def.memory, dev_def.template)
        xml_builder.add_disk(dev_def.storage_pool, dev_def.base_image
                if dev_def.base_image_type == 'backing-store' else None)
        if dev_def.day0_file is not None:
            xml_builder.add_day0_disk(dev_def.storage_pool)

        (mgmt_ip_address, mac_address, iface_dev_name
                ) = xml_builder.add_mgmt_iface('e1000'
                        if dev_def.device_type == 'XRv-9000' else 'virtio')
        write_oper_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', iface_dev_name)])

        if dev_def.device_type == 'XRv-9000':
            xml_builder.add_extra_mgmt_ifaces(XRV9K_EXTRA_MGMT_NETWORKS)

        xml_builder.add_data_ifaces(dev_def.device_type == 'XRv-9000')

        domain_xml_str = xml_to_string(xml_builder.domain_xml)
        self._log.info(domain_xml_str)

        self._libvirt.conn.defineXML(domain_xml_str)
        self._output.domains.create(device_name)

        self._log.info(f'Creating device {device_name} in NSO')
        if dev_def.ned_id is not None:
            nso_device_onboard(device)

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
    def __init__(self, libvirt_conn, topology,
            hypervisor, log, output, username):
        self._topology = topology
        self._dev_defs = maagic.cd(topology, '../libvirt/device-definition')
        self._output = output

        args = (libvirt_conn, ResourceManager(hypervisor, username),
                NetworkManager(topology), self._dev_defs, log)

        self._extra_network = ExtraNetwork(*args)
        self._link_network = LinkNetwork(*args)
        self._isolated_network = IsolatedNetwork(*args)
        self._volume = Volume(*args)
        self._domain = Domain(*args)

        self._volume.load_day0_templates(self._topology.devices.device)
        self._domain.load_device_templates(self._topology.devices.device)

    def action(self, action):
        output = self._output.libvirt_action.create()
        output.action = action

        if any(self._dev_defs[device.definition].device_type == 'XRv-9000'
                for device in self._topology.devices.device):
            for (idx, network_id) in enumerate(XRV9K_EXTRA_MGMT_NETWORKS):
                self._extra_network.action(
                        action, output, network_id, (0xff, 0xff-idx))

        for (idx, network) in enumerate(self._topology.networks.network):
            self._extra_network.action(
                    action, output, network.name, (0xfe, 0xff-idx))

        for link in self._topology.links.link:
            self._link_network.action(action, output, link)

        for device in self._topology.devices.device:
            if self._dev_defs[device.definition].device_type == 'XRv-9000':
                self._isolated_network.action(action, output, int(device.id))
            self._domain.action(action, output, device)
            self._volume.action(action, output, device)
            update_status_after_action(device, action)

    def wait_for_shutdown(self):
        timer = 0
        while any(self._domain.is_active(device)
                  for device in self._topology.devices.device) and timer < 60:
            sleep(10)
            timer += 10


class LibvirtAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        topology = maagic.get_node(trans, kp[1:])

        action = name
        if action in ('start', 'define') and not input.force:
            if (action == 'start' and topology.status != 'defined' or
                action == 'define' and topology.status != 'undefined'):
                return

        hypervisor_name = topology.libvirt.hypervisor

        if hypervisor_name is None:
            raise Exception('No hypervisor defined for this topology')

        hypervisor = maagic.cd(topology,
                '../libvirt/hypervisor')[hypervisor_name]

        trans.maapi.install_crypto_keys()
        libvirt_conn = LibvirtConnection()
        libvirt_conn.connect(hypervisor.url)
        libvirt_conn.populate_cache()

        libvirt_topology = Topology(libvirt_conn, topology,
                hypervisor, self.log, output, uinfo.username)

        if name == 'start':
            action = 'create'
        elif name == 'stop':
            libvirt_topology.action('shutdown')
            libvirt_topology.wait_for_shutdown()
            action = 'destroy'

        libvirt_topology.action(action)
        update_status_after_action(topology, action)

        if name == 'start':
            schedule_topology_ping(kp[1:])
