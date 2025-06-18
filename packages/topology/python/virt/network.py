#!/usr/bin/python3
from abc import abstractmethod
from ipaddress import IPv4Address
from ncs import maagic
from libvirt import (VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                     VIR_NETWORK_SECTION_PORTGROUP)

from virt.topology_status import write_node_data, get_hypervisor_output_node
from virt.virt_base import VirtBase

_ncs = __import__('_ncs')


def generate_network_id(device_id, other_id):
    return f'{device_id}-{other_id or "null"}'

def generate_network_name(network_id):
    return f'net-{network_id}'

def generate_bridge_name(network_id):
    return f'vbr-{network_id}'

def generate_iface_dev_name(device_id, other_id):
    return f'veth-{device_id}-{other_id}'

def sort_link_device_ids(device_ids):
    return tuple(sorted(device_ids))

def generate_udp_port(device_id, iface_id):
    return f'1{device_id:02d}{iface_id:02d}'

def force_maagic_leaf_val2str(node, leaf_name):
    value = maagic.get_trans(node).get_elem(f'{node._path}/{leaf_name}')
    return value.val2str(_ncs.cs_node_cd(node._cs_node, leaf_name))

def generate_ip_address(ip_address_start, device_id):
    return str(IPv4Address(ip_address_start) + int(device_id)) if (
        ip_address_start is not None) else None

class NetworkManager():
    def __init__(self, topology, hypervisor_mgr, dev_defs):
        def _add_interface(key, path, network=None, bridge=None, dest=None):
            if (bridge and key in self._bridge_ifaces
                    or key in self._network_ifaces):
                raise Exception(
                        'A device interface can only be used in 1 link or ' +
                        f'network (device {key[0]} interface {key[1]})')

            value = (bridge or network, path, dest)
            if bridge:
                self._bridge_ifaces[key] = value
            else:
                self._network_ifaces[key] = value

        self._device_ids = {device.device_name:int(device.id)
                            for device in topology.devices.device}
        device_types = {device.device_name:dev_defs[device.definition].device_type
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

            libvirt_network = (network_id and
                               device_types[link.a_end_device] != 'XRd' and
                               device_types[link.z_end_device] != 'XRd')

            _add_interface((device_ids[0], iface_ids[0]),
                    f'{link._path}/a-end-interface', network_id, bridges[0],
                    (device_ids[1], iface_ids[1]) if libvirt_network else None)
            _add_interface((device_ids[1], iface_ids[1]),
                    f'{link._path}/z-end-interface', network_id, bridges[1],
                    (device_ids[0], iface_ids[0]) if libvirt_network else None)

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

    def get_network_udp_ports(self, device_id, iface_id):
        network_ifaces = self._network_ifaces.get((device_id, iface_id), (None, None, None))
        return ((generate_udp_port(device_id,iface_id),
                 generate_udp_port(*(network_ifaces[2]))) if network_ifaces[2] else (None, None))

    def get_network(self, network_id):
        return self._networks[network_id]

    def get_network_device_ids(self, network):
        return [ device_id for (
            (device_id, iface_id), value) in self._network_ifaces.items()
                if value[1] == network ]

    def get_iface_network_id(self, device_id, iface_id):
        return self._network_ifaces.get((device_id, iface_id), [None])[0]

    def get_iface_bridge_name(self, device_id, iface_id):
        return self._bridge_ifaces.get((device_id, iface_id), [None])[0]

    def write_iface_data(self, device_id, iface_id, data):
        (_, path, _) = self._network_ifaces.get((device_id, iface_id), [None, None, None])
        if not path:
            (_, path, _) = self._bridge_ifaces.get((device_id, iface_id), [None, None, None])
        if path:
            write_node_data(path, data)

    def get_num_device_ifaces(self):
        return self._max_iface_id + 1


class Network(VirtBase): #pylint: disable=too-few-public-methods
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
        if not device_ids:
            device_ids = self._network_mgr.get_network_device_ids(network_id)
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


class DomainNetworks(VirtBase):
    def __init__(self, factory):
        self._extra_network = factory.create(ExtraNetwork)
        self._isolated_network = factory.create(IsolatedNetwork)
        self._output = None

    INCLUDE_NULL_IFACES = True

    @abstractmethod
    def extra_mgmt_networks(self, action, output, device):
        pass

    def _action(self, action, *args):
        device, = args
        self.extra_mgmt_networks(action, self._output, device)
        if self.INCLUDE_NULL_IFACES:
            self._isolated_network(action, self._output, int(device.id))

class TopologyNetworks(VirtBase):
    def __init__(self, factory):
        self._extra_network = factory.create(ExtraNetwork)
        self._output = None

    @abstractmethod
    def extra_mgmt_networks(self, action, output, device_ids):
        pass

    def _action(self, action, *args):
        device_ids, = args
        self.extra_mgmt_networks(action, self._output, device_ids)
