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
import subprocess

from passlib.hash import md5_crypt
import fs
import pycdlib

import ncs
from ncs.dp import Action
from ncs import maapi, maagic, OPERATIONAL
from virt.libvirt_connection import LibvirtConnection
from virt.topology_status import \
        update_device_status_after_action, update_status_after_action, \
        schedule_topology_ping

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
        template = ncs.template.Template(trans, device._path)
        template.apply('nso-device-template', None)
        trans.apply()

def nso_device_delete(device):
    with maapi.single_write_trans('admin', 'python') as trans:
        trans.safe_delete(f'/devices/device{{{device.device_name}}}')
        trans.apply()

def force_maagic_leaf_val2str(maagic_node, leaf_name):
    #pylint: disable=protected-access
    leaf_node = maagic_node._children.get_by_yang(leaf_name)
    return leaf_node.get_value_object().val2str(leaf_node._cs_node)


class NetworkManager():
    def __init__(self, topology):
        self._devices = {device.device_name:int(device.id)
                         for device in topology.devices.device}
        self._device_names = {int(device.id):device.device_name
                              for device in topology.devices.device}

        self._network_ifaces = {
                (self._devices[device.name], network.interface_id): (
                        network.name, network._path)
                for network in topology.networks.network
                for device in network.devices.device}
        self._networks = {network.name:
                f'{force_maagic_leaf_val2str(network, "ipv4-subnet-start")}.0'
                for network in topology.networks.network}

        self._link_networks = {}
        for link in topology.links.link:
            iface_ids = ((self._devices[link.z_end_device],  #a-end-interface-id
                          self._devices[link.a_end_device])) #z-end-interface-id
            device_ids = sort_link_device_ids(iface_ids)
            self._link_networks[device_ids] = (
                generate_network_id(*device_ids), link._path, iface_ids)

        self._max_iface_id = max((0, *(max(iface_ids)
                 for (_, _, iface_ids) in self._link_networks.values()),
                 *(iface_id for (_, iface_id) in self._network_ifaces)))

    def _get_link_device_ids(self, link):
        return sort_link_device_ids((self._devices[link.a_end_device],
                                     self._devices[link.z_end_device]))

    def get_link_network(self, link):
        device_ids = self._get_link_device_ids(link)
        return (self._link_networks[device_ids][0], device_ids)

    def get_network(self, network_id):
        return self._networks[network_id]

    def get_iface_network_id(self, device_id, iface_id):
        return self._network_ifaces.get((device_id, iface_id),
                self._link_networks.get(
                    sort_link_device_ids((device_id, iface_id)), [None]))[0]

    def write_iface_oper_data(self, device_id, iface_id, data):
        (_, path) = self._network_ifaces.get(
                (device_id, iface_id), (None, None))
        if path:
            path = f'{path}/devices' \
                   f'/device{{{self._device_names[device_id]}}}/interface'
        else:
            (_, path, link_iface_ids) = self._link_networks.get(
                    sort_link_device_ids((device_id, iface_id)),
                    (None, None, None))
            if path:
                if iface_id == link_iface_ids[0]:
                    path = f'{path}/a-end-interface'
                else:
                    path = f'{path}/z-end-interface'
        if path:
            write_oper_data(path, data)

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

    def _get_raw_disk_xml(self, volume_name, pool_name):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': 'disk',
            'file-format': 'raw',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': 'vdb',
            'bus': 'virtio'})

    def _get_cdrom_xml(self, volume_name, pool_name):
        return self._templates.apply_xml_template('disk.xml', {
            'disk-device-type': 'cdrom',
            'file-format': 'raw',
            'storage-pool': pool_name,
            'volume-name': volume_name,
            'target-dev': 'hdc',
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

    def add_day0_cdrom(self, storage_pool):
        self._domain_xml_devices.append(self._get_cdrom_xml(
            generate_day0_volume_name(self._device_name), storage_pool))

    def add_day0_disk(self, storage_pool):
        self._domain_xml_devices.append(self._get_raw_disk_xml(
            generate_day0_volume_name(self._device_name), storage_pool))

    def add_data_ifaces(self, include_null_interfaces, model_type):
        for iface_id in range(self._network_mgr.get_num_device_ifaces()):
            network_id = self._network_mgr.get_iface_network_id(
                    self._device_id, iface_id)

            if network_id is not None or include_null_interfaces:
                iface_dev_name = self._generate_iface_dev_name(iface_id)
                mac_address = self._generate_mac_address(iface_id)

                self._domain_xml_devices.append(self._get_iface_xml(
                    network_id or generate_network_id(self._device_id, None),
                    iface_dev_name, mac_address, model_type))

                if network_id:
                    self._network_mgr.write_iface_oper_data(
                        self._device_id, iface_id, [
                                ('id', iface_id),
                                ('host-interface', iface_dev_name),
                                ('mac-address', mac_address)])


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

    def _define_network(self, network_id, mac_address, isolated=False,
            path=None):
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
            if path:
                write_oper_data(path, [
                    ('host-bridge', bridge_name),
                    ('mac-address', mac_address)])

    def _action(self, action, *args): #network_id, path
        network_id, *args = args
        path = args[0] if args else None
        if action in ['undefine', 'create', 'destroy']:
            network_name = generate_network_name(network_id)
            if network_name in self._libvirt.networks:
                network = self._libvirt.conn.networkLookupByName(network_name)
                if self._action_allowed(network.isActive(), action):
                    self._log.info(f'Running {action} on network {network_name}')
                    network_action_method = getattr(network, action)
                    network_action_method()
                    if action == 'undefine' and path:
                        write_oper_data(path, [
                            ('host-bridge', None),
                            ('mac-address', None)])
                    self._output.networks.create(network_name)
                    return True
        return False


class LinkNetwork(Network):
    def define(self, link):
        (network_id, device_ids) = self._network_mgr.get_link_network(link)
        mac_address = self._resource_mgr.generate_mac_address(*device_ids)
        self._define_network(network_id, mac_address, path=link._path)

    def _action(self, action, *args):
        link, = args
        (network_id, _) = self._network_mgr.get_link_network(link)
        return super()._action(action, network_id, link._path)


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
    def define(self, network_id, path, mac_octets):
        mac_address = self._resource_mgr.generate_mac_address(*mac_octets)
        self._define_network(network_id, mac_address, path=path)


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

    def _create_raw_disk_image(self, file_name):
        size = 1024 * 1024 #1048576
        bytes_per_sector = 512
        sectors_per_track = 63
        heads = 2

        sectors = size / bytes_per_sector #2048
        actual_sectors = int(sectors // sectors_per_track * sectors_per_track) #32*63 = 2016
        actual_size = actual_sectors * bytes_per_sector #1032192
        cylinders = int(actual_sectors / sectors_per_track / heads) #16
        first_sector = sectors_per_track * 1 #63

        #dd if=/dev/zero of=test.img count=2016
        self._log.info(f'Creating empty disk image using temporary disk file '
                       f'{file_name}')
        with open(file_name, 'wb') as binary_file:
            binary_file.write(b'\x00' * actual_size)

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

            if network_id is None:
                continue

            ip_address_start = self._network_mgr.get_network(network_id)
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
            self._network_mgr.write_iface_oper_data(device_id, iface_id, [
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
        elif dev_def.device_type == 'IOSv':
            image_byte_str = self._create_ios_day0_disk_image(
                    dev_def.day0_file, variables)
        elif dev_def.device_type == 'Linux':
            image_byte_str = self._create_cloud_init_iso_image(
                    device_id, dev_def.day0_file, variables)

        pool = self._libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': len(image_byte_str),
            'format-type': 'raw'})

        self._log.info(f'Creating day0 volume {volume_name}')
        self._log.info(volume_xml_str)
        volume = pool.createXML(volume_xml_str)

        self._log.info(f'Uploading day0 image to volume {volume_name}')
        stream = self._libvirt.conn.newStream()
        volume.upload(stream, 0, len(image_byte_str))
        stream.send(image_byte_str)
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
            if dev_def.device_type == 'IOSv':
                xml_builder.add_day0_disk(dev_def.storage_pool)
            else:
                xml_builder.add_day0_cdrom(dev_def.storage_pool)

        (mgmt_ip_address, mac_address, iface_dev_name
                ) = xml_builder.add_mgmt_iface('e1000' if dev_def.device_type
                        in ('XRv-9000', 'IOSv') else 'virtio')
        write_oper_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', iface_dev_name)])

        if dev_def.device_type == 'XRv-9000':
            xml_builder.add_extra_mgmt_ifaces(XRV9K_EXTRA_MGMT_NETWORKS)

        xml_builder.add_data_ifaces(dev_def.device_type == 'XRv-9000',
                'e1000' if dev_def.device_type == 'XRv-9000' else 'virtio')

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

            for iface_id in range(self._network_mgr.get_num_device_ifaces()):
                self._network_mgr.write_iface_oper_data(
                    device.id, iface_id, [
                            ('id', None),
                            ('ip-address', None),
                            ('host-interface', None),
                            ('mac-address', None)])

            if self._dev_defs[device.definition].ned_id is not None:
                nso_device_delete(device)

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

    def action(self, action, device_name=None):
        output = self._output.libvirt_action.create()
        output.action = action

        if device_name is None:
            if any(self._dev_defs[device.definition].device_type == 'XRv-9000'
                    for device in self._topology.devices.device):
                for (idx, network_id) in enumerate(XRV9K_EXTRA_MGMT_NETWORKS):
                    self._extra_network.action(
                            action, output, network_id, None, (0xff, 0xff-idx))

            for (idx, network) in enumerate(self._topology.networks.network):
                self._extra_network.action(action, output, network.name,
                        network._path, (0xfe, 0xff-idx))

            for link in self._topology.links.link:
                self._link_network.action(action, output, link)

        for device in self._topology.devices.device:
            if device_name is not None and device.device_name != device_name:
                continue
            dev_def = self._dev_defs[device.definition]
            if dev_def.device_type == 'XRv-9000':
                self._isolated_network.action(action, output, int(device.id))
            self._domain.action(action, output, device)
            self._volume.action(action, output, device)
            update_device_status_after_action(device,
                    action, dev_def.ned_id is None)

    def wait_for_shutdown(self):
        timer = 0
        while any(self._domain.is_active(device)
                  for device in self._topology.devices.device
                  if self._dev_defs[device.definition].device_type != 'IOSv'
                  ) and timer < 60:
            sleep(10)
            timer += 10


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

        hypervisor_name = topology.libvirt.hypervisor

        if hypervisor_name is None:
            raise Exception('No hypervisor defined for this topology')

        hypervisor = maagic.cd(topology,
                '../libvirt/hypervisor')[hypervisor_name]

        trans.maapi.install_crypto_keys()
        with LibvirtConnection(hypervisor) as libvirt_conn:
            libvirt_conn.populate_cache()

            libvirt_topology = Topology(libvirt_conn, topology,
                    hypervisor, self.log, output, uinfo.username)

            if name == 'start':
                action = 'create'
            elif name == 'stop':
                libvirt_topology.action('shutdown', input.device)
                libvirt_topology.wait_for_shutdown()
                action = 'destroy'

            libvirt_topology.action(action, input.device)
            update_status_after_action(topology, action)

            if name == 'start':
                schedule_topology_ping(kp[1:])
