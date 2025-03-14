#!/usr/bin/python3
from collections import defaultdict
from io import BytesIO
from ipaddress import IPv4Address
from time import sleep
from xml.etree.ElementTree import fromstring, tostring
from xml.dom.minidom import parseString
from libvirt import (VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                     VIR_NETWORK_SECTION_PORTGROUP, VIR_DOMAIN_UNDEFINE_NVRAM)

import base64
import crypt
import os
import re
import string
import subprocess

from passlib.hash import md5_crypt
from fs.tarfs import TarFS
import fs
import pycdlib

import ncs
from ncs.dp import Action
from ncs import maapi, maagic
from virt.libvirt_connection import HypervisorManager
from virt.topology_status import \
        update_device_status_after_action, update_status_after_action, \
        schedule_topology_ping, unschedule_topology_ping

_ncs = __import__('_ncs')

PYTHON_DIR = os.path.dirname(__file__)
XRV9K_EXTRA_MGMT_NETWORKS = ['ctrl', 'host']
VJUNOS_EXTRA_MGMT_NETWORKS = ['pfe', 'rpio', 'rpio', 'pfe']
VMX_EXTRA_MGMT_NETWORKS = ['int']


def generate_network_id(device_id, other_id):
    return f'{device_id}-{other_id or "null"}'

def generate_network_name(network_id):
    return f'net-{network_id}'

def generate_bridge_name(network_id):
    return f'vbr-{network_id}'

def generate_volume_name(device_name):
    return f'{device_name}.qcow2'

def generate_day0_volume_name(device_name):
    return f'{device_name}-day0.img'

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


def write_node_data(path, leaf_value_pairs):
    with maapi.single_write_trans('admin', 'python') as trans:
        for leaf, value in leaf_value_pairs:
            if value is None:
                trans.safe_delete(f'{path}/{leaf}')
            else:
                trans.set_elem(value, f'{path}/{leaf}')
        trans.apply()

def nso_device_onboard(device):
    with maapi.single_write_trans('admin', 'python') as trans:
        template = ncs.template.Template(trans, device._path)
        template.apply('nso-device-template', None)
        trans.apply()

def nso_device_delete(device):
    with maapi.single_write_trans('admin', 'python') as trans:
        trans.safe_delete(f'/devices/device{{{device.device_name}}}')
        trans.apply()

def force_maagic_leaf_val2str(node, leaf_name):
    value = maagic.get_trans(node).get_elem(f'{node._path}/{leaf_name}')
    return value.val2str(_ncs.cs_node_cd(node._cs_node, leaf_name))

def get_hypervisor_output_node(output, hypervisor_name):
    if hypervisor_name in output.hypervisor:
        return output.hypervisor[hypervisor_name]
    return output.hypervisor.create(hypervisor_name)


class NetworkManager():
    def __init__(self, topology, hypervisor_mgr):
        def _add_interface(key, path, network=None, bridge=None):
            if (bridge and key in self._bridge_ifaces
                    or key in self._network_ifaces):
                raise Exception(
                        'A device interface can only be used in 1 link or ' +
                        f'network (device {key[0]} interface {key[1]})')

            value = (bridge or network, path)
            if bridge:
                self._bridge_ifaces[key] = value
            else:
                self._network_ifaces[key] = value

        self._device_ids = {device.device_name:int(device.id)
                            for device in topology.devices.device}
        self._networks = {network.external_bridge or network.name:
                f'{force_maagic_leaf_val2str(network, "ipv4-subnet-start")}.0'
                for network in topology.networks.network}

        self._network_ifaces = {}
        self._bridge_ifaces = {}
        self._link_networks = {}
        for link in topology.links.link:
            device_ids = (self._device_ids[link.a_end_device],
                          self._device_ids[link.z_end_device])
            hypervisors = (hypervisor_mgr.get_device_hypervisor(device_ids[0]),
                           hypervisor_mgr.get_device_hypervisor(device_ids[1]))
            iface_ids = (link.a_end_interface.id
                            if link.a_end_interface.id is not None
                            else device_ids[1],
                         link.z_end_interface.id
                            if link.z_end_interface.id is not None
                            else device_ids[0])
            sorted_device_ids = sort_link_device_ids(device_ids)
            network_id = None
            bridges = (None, None)
            if hypervisors[0] == hypervisors[1]:
                network_id = generate_network_id(*sorted_device_ids)
                self._link_networks[sorted_device_ids] = network_id
            else:
                bridges = (link.external_connection.a_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[0]),
                           link.external_connection.z_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[1]))

            _add_interface((device_ids[0], iface_ids[0]),
                    f'{link._path}/a-end-interface', network_id, bridges[0])
            _add_interface((device_ids[1], iface_ids[1]),
                    f'{link._path}/z-end-interface', network_id, bridges[1])

        for network in topology.networks.network:
            for device in network.devices.device:
                key = (self._device_ids[device.name],
                        device.interface.id or network.interface_id)
                _add_interface(key, f'{device._path}/interface',
                        network.name, network.external_bridge)

        self._max_iface_id = max(0, *(iface_id for (_, iface_id) in (
            *self._network_ifaces, *self._bridge_ifaces)))

    def _get_link_device_ids(self, link):
        return sort_link_device_ids((self._device_ids[link.a_end_device],
                                     self._device_ids[link.z_end_device]))

    def get_link_network(self, link):
        device_ids = self._get_link_device_ids(link)
        return (self._link_networks.get(device_ids, None), device_ids)

    def get_network(self, network_id):
        return self._networks[network_id]

    def get_iface_network_id(self, device_id, iface_id):
        return self._network_ifaces.get((device_id, iface_id), [None])[0]

    def get_iface_bridge_name(self, device_id, iface_id):
        return self._bridge_ifaces.get((device_id, iface_id), [None])[0]

    def write_iface_data(self, device_id, iface_id, data):
        (_, path) = self._network_ifaces.get((device_id, iface_id), [None, None])
        if not path:
            (_, path) = self._bridge_ifaces.get((device_id, iface_id), [None, None])
        if path:
            write_node_data(path, data)

    def get_num_device_ifaces(self):
        return self._max_iface_id + 1


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


class Template(string.Template):
    braceidpattern = '(?a:[_a-z\-][_a-z0-9\-]*)'


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
        return Template(self.templates[template_name]
                ).substitute(defaultdict(str, variables))

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

    def _get_raw_disk_xml(self, volume_name, pool_name, device_type, target, bus):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': device_type,
            'file-format': 'raw',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': target,
            'bus': bus})

    def _get_iface_xml(self, network_id, dev_name, mac_address, model_type,
            bridge_name=''):
        return self._templates.apply_xml_template('interface.xml', {
            'interface-type': 'bridge' if bridge_name else 'network',
            'mac-address': mac_address,
            'network': generate_network_name(network_id) if network_id else '',
            'bridge': bridge_name if bridge_name else '',
            'dev': dev_name,
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

            if (bridge_name or network_id or include_null_interfaces
                    or iface_id < (min_ifaces - 1)):
                iface_dev_name = self._generate_iface_dev_name(iface_id)
                mac_address = self._generate_mac_address(iface_id)

                self._domain_xml_devices.append(self._get_iface_xml(
                    network_id or not bridge_name and
                            generate_network_id(self._device_id, None),
                    iface_dev_name, mac_address, model_type, bridge_name))

                if network_id or bridge_name:
                    self._network_mgr.write_iface_data(
                        device_id or self._device_id, iface_id, [
                                ('id', iface_id),
                                ('host-interface', iface_dev_name),
                                ('mac-address', mac_address)])


class LibvirtObject(): #pylint: disable=too-few-public-methods
    def __init__(self,
            hypervisor_mgr, resource_mgr, network_mgr, dev_defs, log):
        self._hypervisor_mgr = hypervisor_mgr
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

    def _define_network(self, hypervisor_name, network_id, mac_address,
            isolated=False, path=None, delay=None):
        uuid = ''
        network_name = generate_network_name(network_id)
        bridge_name = generate_bridge_name(network_id)
        libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)

        if network_name in libvirt.networks:
            network = libvirt.conn.networkLookupByName(network_name)
            uuid = network.UUIDString()

        variables = {
            'uuid': uuid,
            'network': network_name,
            'bridge': bridge_name,
            'mac-address': mac_address,
            'isolated': 'yes' if isolated else '',
            'delay': delay if delay else ''}

        network_xml_str = self._templates.apply_template(
                'network.xml', variables)
        self._log.info(f'[{hypervisor_name}] '
                       f'Defining network {network_name}')
        self._log.info(network_xml_str)
        libvirt.conn.networkDefineXML(network_xml_str)
        get_hypervisor_output_node(self._output,
                hypervisor_name).networks.create(network_name)
        if path:
            write_node_data(path, [
                ('host-bridge', bridge_name),
                ('mac-address', mac_address)])

    def _update_network(self, hypervisor_name, network_id, mac_address,
            isolated=False, delay=None):
        libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)
        network_name = generate_network_name(network_id)

        if network_name in libvirt.networks:
            self._define_network(hypervisor_name, network_id, mac_address,
                    isolated=isolated, delay=delay)
            network = libvirt.conn.networkLookupByName(network_name)
            network.update(
                    VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                    VIR_NETWORK_SECTION_PORTGROUP, -1,
                    '<portgroup name="dummy"/>')

    def _action(self, action, *args): #network_id, path
        hypervisor_name, network_id,  *args = args
        path = args[0] if args else None

        if action in ['undefine', 'create', 'destroy']:
            network_name = generate_network_name(network_id)
            libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)
            if network_name in libvirt.networks:
                network = libvirt.conn.networkLookupByName(network_name)
                if self._action_allowed(network.isActive(), action):
                    self._log.info(
                            f'[{hypervisor_name}] '
                            f'Running {action} on network {network_name}')
                    network_action_method = getattr(network, action)
                    network_action_method()
                    get_hypervisor_output_node(self._output,
                            hypervisor_name).networks.create(network_name)
                    if action == 'undefine' and path:
                        write_node_data(path, [
                            ('host-bridge', None),
                            ('mac-address', None)])

    def _get_hypervisors(self, device_ids):
        return set(self._hypervisor_mgr.get_device_hypervisor(device_id)
                   for device_id in device_ids)

class LinkNetwork(Network):
    def define(self, link):
        (network_id, device_ids) = self._network_mgr.get_link_network(link)
        if network_id:
            self._define_network(
                self._hypervisor_mgr.get_device_hypervisor(device_ids[0]),
                network_id,
                self._resource_mgr.generate_mac_address(*device_ids),
                path=link._path,
                delay=link.libvirt.delay)

    def update(self, link):
        (network_id, device_ids) = self._network_mgr.get_link_network(link)
        if network_id:
            self._update_network(
                self._hypervisor_mgr.get_device_hypervisor(device_ids[0]),
                network_id,
                self._resource_mgr.generate_mac_address(*device_ids),
                delay=link.libvirt.delay)

    def _action(self, action, *args):
        link, = args
        (network_id, device_ids) = self._network_mgr.get_link_network(link)
        if network_id:
            super()._action(action,
                self._hypervisor_mgr.get_device_hypervisor(device_ids[0]),
                network_id, link._path)

class IsolatedNetwork(Network):
    def _get_hypervisor_network(self, device_id):
        return (self._hypervisor_mgr.get_device_hypervisor(device_id),
                generate_network_id(device_id, None))

    def define(self, device_id):
        self._define_network(*self._get_hypervisor_network(device_id),
                self._resource_mgr.generate_mac_address(device_id, 0x00),
                isolated=True)

    def _action(self, action, *args):
        device_id, = args
        super()._action(action, *self._get_hypervisor_network(device_id))

class ExtraNetwork(Network):
    def define(self, device_ids, network_id, path, mac_octets):
        for (idx, hypervisor_name) in enumerate(
                self._get_hypervisors(device_ids)):
            mac_address = self._resource_mgr.generate_mac_address(
                    mac_octets[0] - 0x10*idx, mac_octets[1])
            self._define_network(
                    hypervisor_name, network_id, mac_address, path=path)

    def _action(self, action, *args):
        device_ids, network_id, path, _ = args
        for hypervisor_name in self._get_hypervisors(device_ids):
            super()._action(action, hypervisor_name, network_id, path)

class Volume(LibvirtObject):
    def _load_templates(self):
        self._templates.load_template('templates', 'volume.xml')
        self._templates.load_template('cloud-init', 'meta-data.yaml')
        self._templates.load_template('cloud-init', 'network-config.yaml')
        self._templates.load_template('cloud-init', 'ethernet.yaml')
        self._templates.load_template('images', 'junos-vmx-loader.conf')

    def load_day0_templates(self, devices):
        day0_templates = filter(None, set(self._dev_defs[
            device.definition].day0_file for device in devices))
        for template in day0_templates:
            self._templates.load_template('images', template)

    def _create_raw_disk_image(self, file_name, create_partition_table=True):
        size = 1024 * 1024 #1048576
        bytes_per_sector = 512
        sectors_per_track = 63
        heads = 2

        sectors = size / bytes_per_sector #2048
        actual_sectors = int(sectors // sectors_per_track * sectors_per_track) #32*63 = 2016
        actual_size = actual_sectors * bytes_per_sector #1032192
        cylinders = int(actual_sectors / sectors_per_track / heads) #16
        first_sector = sectors_per_track * int(create_partition_table) #63

        #dd if=/dev/zero of=test.img count=2016
        self._log.info(f'Creating empty disk image using temporary disk file '
                       f'{file_name}')
        with open(file_name, 'wb') as binary_file:
            binary_file.write(b'\x00' * actual_size)

        if first_sector > 0:
            #fdisk --cylinders 16 --heads 2 --sectors 63 test.img
            self._log.info('Creating partition table using fdisk')
            with subprocess.Popen(['fdisk',
                        '--cylinders', str(cylinders),
                        '--heads', str(heads),
                        '--sectors', str(sectors_per_track),
                        file_name],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    text=True) as fdisk:
                fdisk.communicate(
                        f'n\n' #Add partition
                        f'p\n' #Partition type (primary)
                        f'1\n' #Partition number
                        f'{first_sector}\n' #First sector
                        f'{actual_sectors-1}\n' #Last sector
                        f't\n' #Change partition type
                        f'01\n' #01 FAT12
                        f'a\n' #Toggle boot flag
                        f'w\n' #Write table and exit
                    )

        #mkfs.fat -F 12 -g 16/63 -h 1 -R 8 -s 8 -v --offset 63 ./test.img
        self._log.info('Formatting partition using mkfs.fat')
        subprocess.run(['mkfs.fat',
                '-F', '12', #FAT size
                '-g', f'{heads}/{sectors_per_track}', #Geometry
                '-h', '1', #Hiddens sectors
                '-R', '8', #Reserved sectors
                '-s', '8', #Sectors per cluster
                '--offset', f'{first_sector}',
                file_name],
            stdout=subprocess.DEVNULL, check=True)

        return first_sector*bytes_per_sector

    def _create_ios_day0_disk_image(self, file_name, variables):
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

    def _create_junos_day0_disk_image(self, file_name, variables, vmx=True):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file, not vmx)

        self._log.info('Writing day0 file to partition')
        self._log.info(f'/config/juniper.conf:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            with TarFS(flash_drive.openbin('/vmm-config.tgz', 'wb'),
                                write=True, compression='gz') as tarfile:
                tarfile.makedir('/config')
                tarfile.writetext('/config/juniper.conf', day0_str)
                if vmx:
                    tarfile.makedir('/boot')
                    tarfile.writetext('/boot/loader.conf',
                            self._templates.apply_template(
                                'junos-vmx-loader.conf', {}))

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str

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

    def _create_day0_volume(self, libvirt, device_id, device_name, dev_def):
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
            'password-md5': md5_crypt.using(salt_size=4).hash(
                _ncs.decrypt(mapping.remote_password)),
            **self._resource_mgr.mgmt_network_variables}

        if dev_def.day0_upload_file:
            with open(dev_def.day0_upload_file, 'rb') as binary_file:
                byte_array = binary_file.read()
            variables['file-content'] = base64.b64encode(byte_array).decode()

        if dev_def.device_type == 'XRv-9000':
            image_byte_str = self._create_iosxr_day0_iso_image(
                    dev_def.day0_file, variables)
        if dev_def.device_type in ('vJunos-Evolved', 'vMX'):
            image_byte_str = self._create_junos_day0_disk_image(
                    dev_def.day0_file, variables, dev_def.device_type == 'vMX')
        elif dev_def.device_type == 'IOSv':
            image_byte_str = self._create_ios_day0_disk_image(
                    dev_def.day0_file, variables)
        elif dev_def.device_type == 'Linux':
            image_byte_str = self._create_cloud_init_iso_image(
                    device_id, dev_def.day0_file, variables)

        pool = libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': len(image_byte_str),
            'format-type': 'raw'})

        self._log.info(
                f'[{libvirt.name}] Creating day0 volume {volume_name}')
        self._log.info(volume_xml_str)
        volume = pool.createXML(volume_xml_str)

        self._log.info(
                f'[{libvirt.name}] Uploading day0 image to volume {volume_name}')
        stream = libvirt.conn.newStream()
        volume.upload(stream, 0, len(image_byte_str))
        stream.send(image_byte_str)
        stream.finish()
        get_hypervisor_output_node(
                self._output, libvirt.name).volumes.create(volume_name)

    def _create_volume(self, libvirt, volume_name, pool_name,
            base_image_name, clone, new_size):
        pool = libvirt.conn.storagePoolLookupByName(pool_name)
        base_image = pool.storageVolLookupByName(base_image_name)
        volume_size = base_image.info()[1] if not clone else ''
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': volume_size,
            'format-type': 'qcow2'})

        if clone:
            self._log.info(
                    f'[{libvirt.name}] '
                    f'Creating volume {volume_name} from {base_image_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXMLFrom(volume_xml_str, base_image)
        else:
            self._log.info(f'[{libvirt.name}] Creating volume {volume_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXML(volume_xml_str)

        if new_size is not None:
            vol.resize(new_size*1024*1024*1024)
        get_hypervisor_output_node(
                self._output, libvirt.name).volumes.create(volume_name)

    def _delete_volume(self, libvirt, pool, volume_name, volume_type='volume'):
        if volume_name and volume_name in libvirt.volumes[pool.name()]:
            volume = pool.storageVolLookupByName(volume_name)
            self._log.info(f'[{libvirt.name}] '
                           f'Running delete on {volume_type} {volume_name}')
            volume.delete()
            get_hypervisor_output_node(
                    self._output, libvirt.name).volumes.create(volume_name)

    def define(self, device):
        dev_def = self._dev_defs[device.definition]
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        self._create_volume(libvirt, generate_volume_name(device_name),
                dev_def.storage_pool, dev_def.base_image,
                dev_def.base_image_type == 'clone', dev_def.disk_size)

        if dev_def.day0_file is not None:
            self._create_day0_volume(
                    libvirt, int(device.id), device_name, dev_def)

    def undefine(self, device):
        dev_def = self._dev_defs[device.definition]
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        if dev_def.storage_pool in libvirt.volumes:
            pool = libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
            self._delete_volume(
                    libvirt, pool, generate_volume_name(device_name))

            if dev_def.day0_file is not None:
                day0_volume_name = generate_day0_volume_name(device_name)
                self._delete_volume(
                        libvirt, pool, day0_volume_name, 'day0 volume')


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
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        self._log.info(f'[{libvirt.name}] Defining domain {device_name}')

        dev_def = self._dev_defs[device.definition]
        xml_builder = DomainXmlBuilder(int(device.id), device_name,
                self._resource_mgr, self._network_mgr, self._templates)

        xml_builder.create_base(dev_def.vcpus, dev_def.memory, dev_def.template)
        xml_builder.add_disk(dev_def.storage_pool, dev_def.base_image
                if dev_def.base_image_type == 'backing-store' else None)
        if dev_def.day0_file is not None:
            if dev_def.device_type == 'XRv-9000':
                xml_builder.add_day0_cdrom(dev_def.storage_pool)
            elif dev_def.device_type == 'vJunos-Evolved':
                xml_builder.add_day0_usb(dev_def.storage_pool)
            else:
                xml_builder.add_day0_disk(dev_def.storage_pool)

        (mgmt_ip_address, mac_address, iface_dev_name
                ) = xml_builder.add_mgmt_iface('e1000' if dev_def.device_type
                        in ('XRv-9000', 'IOSv') else 'virtio')
        write_node_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', iface_dev_name)])

        if dev_def.device_type == 'XRv-9000':
            xml_builder.add_extra_mgmt_ifaces(XRV9K_EXTRA_MGMT_NETWORKS, None, 'e1000')
        if dev_def.device_type == 'vJunos-Evolved':
            xml_builder.add_extra_mgmt_ifaces(VJUNOS_EXTRA_MGMT_NETWORKS, device.id)
        if dev_def.device_type == 'vMX':
            xml_builder.add_extra_mgmt_ifaces(VMX_EXTRA_MGMT_NETWORKS,
                    device.control_plane_id or device.id)

        if dev_def.device_type != 'vMX' or device.control_plane_id:
            xml_builder.add_data_ifaces(
                    dev_def.device_type in ('XRv-9000', 'vJunos-Evolved', 'vMX'),
                    'e1000' if dev_def.device_type in ('XRv-9000', 'IOSv') else 'virtio',
                    4 if dev_def.device_type == 'IOSv' else 0,
                    1 if dev_def.device_type == 'IOSv' else 0,
                    device.control_plane_id)

        domain_xml_str = xml_to_string(xml_builder.domain_xml)
        self._log.info(domain_xml_str)

        libvirt.conn.defineXML(domain_xml_str)
        get_hypervisor_output_node(
                self._output, libvirt.name).domains.create(device_name)

        self._log.info(f'Creating device {device_name} in NSO')
        if dev_def.ned_id is not None:
            nso_device_onboard(device)

    def undefine(self, device):
        if self._action('undefine', device):
            write_node_data(device.management_interface._path, [
                    ('ip-address', None),
                    ('mac-address', None),
                    ('host-interface', None)])

            for iface_id in range(self._network_mgr.get_num_device_ifaces()):
                self._network_mgr.write_iface_data(
                    device.id, iface_id, [
#                           ('id', None),
                            ('ip-address', None),
                            ('host-interface', None),
                            ('mac-address', None)])

            if self._dev_defs[device.definition].ned_id is not None:
                nso_device_delete(device)

    def is_active(self, device):
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        if device_name in libvirt.domains:
            return libvirt.conn.lookupByName(device_name).isActive()
        return False

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


class Topology():
    def __init__(self, topology, log, output, username):
        hypervisor_name = topology.libvirt.hypervisor

        if hypervisor_name is None:
            raise Exception('No hypervisor defined for this topology')

        hypervisors = maagic.cd(topology, '../libvirt/hypervisor')
        hypervisor = hypervisors[hypervisor_name]
        hypervisor_mgr = HypervisorManager(hypervisors, topology)

        self._topology = topology
        self._dev_defs = maagic.cd(topology, '../libvirt/device-definition')
        self._output = output

        args = (hypervisor_mgr,
                ResourceManager(hypervisor, username),
                NetworkManager(topology, hypervisor_mgr),
                self._dev_defs, log)

        self._extra_network = ExtraNetwork(*args)
        self._link_network = LinkNetwork(*args)
        self._isolated_network = IsolatedNetwork(*args)
        self._volume = Volume(*args)
        self._domain = Domain(*args)

        self._volume.load_day0_templates(self._topology.devices.device)
        self._domain.load_device_templates(self._topology.devices.device)

    def action(self, action, device_name=None):
        output = self._output.libvirt_action.create()
        output.action = action

        if device_name is None:
            device_ids = [device.id for device in self._topology.devices.device
                          if self._dev_defs[device.definition
                                ].device_type == 'XRv-9000']
            if len(device_ids) > 0:
                for (idx, network_id) in enumerate(XRV9K_EXTRA_MGMT_NETWORKS):
                    self._extra_network.action(action, output,
                            device_ids, network_id, None, (0xff, 0xff-idx))

            for (idx, network) in enumerate(self._topology.networks.network):
                if not network.external_bridge:
                    self._extra_network.action(action, output, device_ids,
                            network.name, network._path, (0xfe, 0xff-idx))

            for link in self._topology.links.link:
                self._link_network.action(action, output, link)

        for device in self._topology.devices.device:
            if device_name is not None and device.device_name != device_name:
                continue
            dev_def = self._dev_defs[device.definition]
            if dev_def.device_type == 'vJunos-Evolved':
                for (idx, network_name) in enumerate(
                        set(VJUNOS_EXTRA_MGMT_NETWORKS)):
                    self._extra_network.action(action, output,
                            [ device.id ], f'{network_name}-{device.id}',
                            None, (0xfd, 0xff-idx))
            if dev_def.device_type == 'vMX' and not device.control_plane_id:
                for (idx, network_name) in enumerate(
                        set(VMX_EXTRA_MGMT_NETWORKS)):
                    self._extra_network.action(action, output, [ device.id ],
                            f'{network_name}-{device.id}',
                            None, (0xfc, device.id))
            if dev_def.device_type != 'Linux':
                self._isolated_network.action(action, output, int(device.id))
            self._domain.action(action, output, device)
            self._volume.action(action, output, device)
            update_device_status_after_action(device,
                    action, dev_def.ned_id is None)

    def wait_for_shutdown(self, device_name=None):
        timer = 0
        while any(self._domain.is_active(device)
                  for device in self._topology.devices.device
                  if (device_name is None or device.device_name == device_name)
                  and self._dev_defs[device.definition].device_type not in (
                        'IOSv', 'vMX')
                  ) and timer < 60:
            sleep(10)
            timer += 10

    def get_link_network_helper(self):
        return self._link_network


class LibvirtAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        topology = maagic.get_node(trans, kp[1:])

        action = name
        if action in ('start', 'define') and not (input.device or input.force):
            if (action == 'start' and
                    topology.provisioning_status != 'defined' or
                action == 'define' and
                    topology.provisioning_status != 'undefined'):
                return

        trans.maapi.install_crypto_keys()
        libvirt_topology = Topology(topology, self.log, output, uinfo.username)

        def run_action(name):
            action = name
            if name == 'start':
                action = 'create'
            elif name == 'stop':
                libvirt_topology.action('shutdown', input.device)
                libvirt_topology.wait_for_shutdown(input.device)
                action = 'destroy'

            libvirt_topology.action(action, input.device)
            update_status_after_action(topology, action)

            if name == 'start':
                schedule_topology_ping(kp[1:])

            if name == 'stop':
                unschedule_topology_ping(kp[1][0])

        if name in ('reboot', 'hard-reset'):
            run_action('stop')
            action = 'start'

        if name == 'hard-reset':
            run_action('undefine')
            libvirt_topology = None
            sleep(5)
            libvirt_topology = Topology(topology, self.log, output, uinfo.username)
            run_action('define')
            libvirt_topology = None
            sleep(5)
            libvirt_topology = Topology(topology, self.log, output, uinfo.username)

        run_action(action)


class LibvirtNetworkAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        link = maagic.get_node(trans, kp[1:])
        topology = maagic.get_node(trans, kp[4:])
        self.log.info(topology._path)

        action = name
        if name == 'start':
            action = 'create'
        elif name == 'stop':
            action = 'destroy'
        elif name == 'set-delay':
            write_node_data(link._path, [('libvirt/delay', input.delay)])
            action = 'update'

        action_output = output.libvirt_action.create()
        action_output.action = action

        libvirt_topology = Topology(topology, self.log, output, uinfo.username)
        libvirt_topology.get_link_network_helper().action(
                action, action_output, link)
