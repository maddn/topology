#!/usr/bin/python3
from abc import abstractmethod
from dataclasses import dataclass
from ipaddress import IPv4Address
from ncs import maagic, maapi, OPERATIONAL
from libvirt import (VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                     VIR_NETWORK_SECTION_PORTGROUP)

from virt.topology_status import write_node_data, get_hypervisor_output_node
from virt.virt_base import VirtBase
from virt.template import xml_to_string

_ncs = __import__('_ncs')


@dataclass
class InterfaceEndpoint:
    """Represents one end of a network link"""
    device_name: str
    interface_name: str
    is_container: bool

def generate_network_id(device_id, other_id):
    return f'{device_id}-{other_id or "null"}'

def generate_network_name(network_id):
    return f'net-{network_id}'

def generate_bridge_name(network_id):
    return f'vbr-{network_id}'

def generate_iface_dev_name(device_id, other_id):
    return f'veth-{device_id}-{other_id}'

def generate_link_network_id(device_ids):
    return generate_network_id(*sorted(device_ids))

def generate_udp_port(device_id, iface_id):
    return f'1{device_id:02d}{iface_id:02d}'

def force_maagic_leaf_val2str(node, leaf_name):
    value = maagic.get_trans(node).get_elem(f'{node._path}/{leaf_name}')
    return value.val2str(_ncs.cs_node_cd(node._cs_node, leaf_name))

def generate_ip_address(ip_address_start, device_id):
    return str(IPv4Address(ip_address_start) + int(device_id)) if (
        ip_address_start is not None) else None

def get_host_iface_name(path):
    with maapi.single_read_trans('admin', 'python', db=OPERATIONAL) as trans:
        interface = maagic.get_node(trans, path)
        return interface.host_interface

class NetworkManager():
    """
        This class is repsonsible for assigning and tracking topology
        connectivity. That is, what each device interface is connected
        to and, if applicable, the lifecycle of the connected network.

        There are two types of data connection possible in the toplogy
        definition:

        - Link: A point-to-point connection between two device interfaces.

        - Network: A managed or unmanaged bridge containing one or more
          device interfaces.

        To implement these, a device interface can be connected to:
            - A libvirt managed network (links or networks)
            - An external existing bridge (links or networks)
            - Another interace (links only):
                - Libvirt UDP networking
                - veth pair
                - Tap interface in container namespace

        If an interface connects to an external existing bridge, the
        bridge is unmanaged. This means there is no need to track what
        else is connected to the bridge or even if the bridge is used
        for a Link or Network.

        If the interface is not connected to an external bridge then:

          - For a link interface, the other end of the link must be tracked.
            For example, veth pairs cannot be created until both ends of the
            link are up, and must be removed before the containers at each end
            are stopped.

          - For network interfaces connected to libvirt managed networks, the
            other devices in the network must be tracked. Networks should be
            started before any device endpoint and should not be stopped until
            all device endpoints have been stopped.

        Therefore this class tracks three types of interfaces:

        - link_ifaces:
            - Direct links not using any type of bridge (managed or unmanaged)
            - Track other end of link
        - network_ifaces:
            - Links and networks using libvirt managed networks
            - Track other devices interfaces in the network (using network_id)
        - bridge_ifaces:
            - Links and networks using external unmanaged bridges
            - Track nothing
    """

    def __init__(self, topology, hypervisor_mgr, domain_mgr, resource_mgr):
        def _add_interface(key, path, network, bridge, dest=None, udp=False):
            if key in self._connected_ifaces:
                raise Exception(
                        'A device interface can only be used in 1 link or ' +
                        f'network (device {key[0]} interface {key[1]})')

            if bridge:
                self._bridge_ifaces[key] = bridge
            elif network:
                self._network_ifaces[key] = network

            if dest:
                self._link_ifaces[key] = dest

            if udp and dest:
                self._udp_ifaces[key] = (
                        hypervisor_mgr.get_device_udp_tunnel_ip_address(key[0]),
                        generate_udp_port(*key),
                        hypervisor_mgr.get_device_udp_tunnel_ip_address(dest[0]),
                        generate_udp_port(*dest))

            self._connected_ifaces[key] = path

        self._network_index = {network.name:idx
                for idx, network in enumerate(topology.networks.network)}

        self._networks = {network.external_bridge or network.name:
                f'{force_maagic_leaf_val2str(network, "ipv4-subnet-start")}.0'
                for network in topology.networks.network}

        self._resource_mgr = resource_mgr
        self._domain_mgr = domain_mgr

        self._network_ifaces = {}
        self._bridge_ifaces = {}
        self._link_ifaces = {}
        self._udp_ifaces = {}
        self._connected_ifaces = {}

        for link in topology.links.link:
            device_ids = (self._domain_mgr.get_device_id(link.a_end_device),
                          self._domain_mgr.get_device_id(link.z_end_device))
            hypervisors = (hypervisor_mgr.get_device_hypervisor(device_ids[0]),
                           hypervisor_mgr.get_device_hypervisor(device_ids[1]))
            iface_ids = (link.a_end_interface.id
                            if link.a_end_interface.id is not None
                            else device_ids[1],
                         link.z_end_interface.id
                            if link.z_end_interface.id is not None
                            else device_ids[0])

            bridges = (None, None)
            if hypervisors[0] != hypervisors[1]:
                bridges = (link.external_connection.a_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[0]),
                           link.external_connection.z_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[1]))

            network_id = generate_link_network_id(device_ids) if (
                    not all(bridges) and (
                    self._domain_mgr.need_bridge_networking(device_ids[0]) or
                    self._domain_mgr.need_bridge_networking(device_ids[1])
                    )) else None

            udp_networking = (not network_id and
                    not self._domain_mgr.is_container(device_ids[0]) and
                    not self._domain_mgr.is_container(device_ids[1]))

            _add_interface((device_ids[0], iface_ids[0]),
                    f'{link._path}/a-end-interface', network_id, bridges[0],
                    (device_ids[1], iface_ids[1]), udp_networking)
            _add_interface((device_ids[1], iface_ids[1]),
                    f'{link._path}/z-end-interface', network_id, bridges[1],
                    (device_ids[0], iface_ids[0]), udp_networking)

        for network in topology.networks.network:
            for device in network.devices.device:
                key = (self._domain_mgr.get_device_id(device.name),
                        device.interface.id or network.interface_id)
                _add_interface(key, f'{device._path}/interface',
                        network.name, network.external_bridge)

        self._max_iface_id = max(0, *(iface_id for (_, iface_id) in
            self._connected_ifaces))

    def get_network(self, network_id):
        return self._networks[network_id]

    def get_iface_network_id(self, device_id, iface_id):
        return self._network_ifaces.get((int(device_id), iface_id), None)

    def get_iface_link_dest(self, device_id, iface_id):
        return self._link_ifaces.get((int(device_id), iface_id), None)

    def get_iface_bridge_name(self, device_id, iface_id):
        return self._bridge_ifaces.get((int(device_id), iface_id), None)

    def get_iface_path(self, device_id, iface_id):
        return self._connected_ifaces.get((int(device_id), iface_id), None)

    def get_network_index(self, network_id):
        return self._network_index[network_id]

    def write_iface_data(self, device_id, iface_id, data):
        path = self.get_iface_path(device_id, iface_id)
        if path:
            write_node_data(path, data)

    def get_network_udp_ports(self, device_id, iface_id):
        return self._udp_ifaces.get((device_id, iface_id), None)

    def get_num_device_ifaces(self):
        return self._max_iface_id + 1

    def get_interface_host_info(self, device_id, iface_id):
        """
        Get all information needed to plumb an interface.

        Returns an InterfaceEndpoint, or None if not connected.
        """
        path = self.get_iface_path(device_id, iface_id)
        if not path:
            return None
        return InterfaceEndpoint(
                device_name=self._domain_mgr.get_device_name(device_id),
                interface_name=get_host_iface_name(path),
                is_container=self._domain_mgr.is_container(device_id),
            )

    def get_interface_managed_network_info(self, device_id, iface_id):
        """
        Check if this interface is connected to a libvirt managed network

        Returns a tuple of (network_id, devices):
        - network_id: the id part of the libvirt network name
        - devices: list of other devices in the network

        Returns a tuple of (None, None) if the interface is not connected to
        a libvirt managed network
        """
        network_id = self.get_iface_network_id(device_id, iface_id)
        if not network_id:
            return (None, None)

        devices = [device
                for (device, _), network in self._network_ifaces.items()
                if network == network_id and device != device_id]

        return (network_id, devices)

    def get_interface_direct_link_info(self, device_id, iface_id):
        """
        If this interface is a direct link interface (not using a libvirt
        network or unmanaged bridge), return the other end of the link

        Returns a tuple of (other_device_id, other_iface_id):
        - other_device_id: the device on the other end
        - other_iface_id: the interface on the other end

        Returns a tuple of (None, None) if the interface is not the end of a
        link of if the link uses a managed libvirt network or unmanaged bridge.
        """
        network_id = self.get_iface_network_id(device_id, iface_id)
        bridge_name = self.get_iface_bridge_name(device_id, iface_id)
        link_dest = self.get_iface_link_dest(device_id, iface_id)

        if not network_id and not bridge_name and link_dest:
            return link_dest

        return (None, None)

    def get_interface_any_bridge_info(self, device_id, iface_id):
        """
        Check if this interface is connected to any bridge (managed through
        a libivrt network or unmanaged)

        Returns str with the name of the bridge

        Returns None if interface is not connected to any bridge
        """
        bridge_name = self.get_iface_bridge_name(device_id, iface_id)
        if not bridge_name:
            network_id = self.get_iface_network_id(device_id, iface_id)
            if network_id:
                bridge_name = generate_bridge_name(network_id)

        return bridge_name


class Connection(VirtBase):
    def connection(
            self, action, output, device_id, iface_id, when, link_dest):
        pass

    def _action(self, action, *args):
        device_id, iface_id, when, link_dest = args
        if hasattr(self, action):
            action_method = getattr(self, action)
            action_method(device_id, iface_id, when, link_dest)
        else:
            self.connection(
                    action, self._output, device_id, iface_id, when, link_dest)


class Network(VirtBase): #pylint: disable=too-few-public-methods
    def _load_templates(self):
        self._templates.load_template('templates', 'network.xml')

    def define(self, hypervisor_name, network_id, path, mac_address,
               isolated=False, delay=None):
        uuid = ''
        network_name = generate_network_name(network_id)
        libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)

        if not libvirt:
            return

        if network_name in libvirt.networks:
            if delay:
                network = libvirt.conn.networkLookupByName(network_name)
                uuid = network.UUIDString()
            else:
                self._log.info(f'[{hypervisor_name}] '
                       f'Network {network_name} already defined')
                return

        bridge_name = generate_bridge_name(network_id)

        variables = {
            'uuid': uuid,
            'network': network_name,
            'bridge': bridge_name,
            'mac-address': mac_address,
            'isolated': 'yes' if isolated else '',
            'delay': delay if delay else '',
        }

        network_xml = self._templates.apply_xml_template(
                'network.xml', variables)

        network_xml_str = xml_to_string(network_xml)

        self._log.info(f'[{hypervisor_name}] {"Re-d" if uuid else "D"}'
                       f'efining network {network_name}')
        self._log.debug(network_xml_str)
        libvirt.conn.networkDefineXML(network_xml_str)
        get_hypervisor_output_node(self._output,
                hypervisor_name).networks.create(network_name)
        if path:
            write_node_data(path, [
                ('host-bridge', bridge_name),
                ('mac-address', mac_address)])

        if network_name not in libvirt.networks:
            libvirt.networks[network_name] = { 'bridge-name': bridge_name }

    def _update_network(self, hypervisor_name, network_id):
        libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)

        if not libvirt:
            return

        network_name = generate_network_name(network_id)

        if network_name in libvirt.networks:
            self._log.info(f'[{hypervisor_name}] Updating network {network_name}')
            network = libvirt.conn.networkLookupByName(network_name)
            network.update(
                    VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                    VIR_NETWORK_SECTION_PORTGROUP, -1,
                    '<portgroup name="dummy"/>')

    def _action(self, action, *args): #hypervisor_name, network_id, path
        hypervisor_name, network_id,  *args = args
        path = args[0] if args else None

        if action in ['undefine', 'create', 'destroy']:
            network_name = generate_network_name(network_id)
            libvirt = self._hypervisor_mgr.get_libvirt(hypervisor_name)
            is_active = None
            if libvirt and network_name in libvirt.networks:
                network = libvirt.conn.networkLookupByName(network_name)
                is_active = network.isActive()
                if self._action_allowed(is_active, action):
                    self._log.info(
                            f'[{hypervisor_name}] '
                            f'Running {action} on network {network_name}')
                    network_action_method = getattr(network, action)
                    network_action_method()
                    get_hypervisor_output_node(self._output,
                            hypervisor_name).networks.create(network_name)
                    if action == 'undefine':
                        if path:
                            write_node_data(path, [
                                ('host-bridge', None),
                                ('mac-address', None)])
                        del libvirt.networks[network_name]
                    return

            if libvirt:
                self._log.info(f'[{hypervisor_name}] Skipping {action} on '
                               f'{"ACTIVE" if is_active else
                                  "INACTIVE" if is_active == 0 else
                                  "NON-EXISTENT"} '
                               f'network {network_name}. is_active={is_active}')

    def _get_hypervisors(self, device_ids):
        return set(self._hypervisor_mgr.get_device_hypervisor(device_id)
                   for device_id in device_ids)


class DomainNetworks(VirtBase):
    MGMT_OCTET = 0xff
    INCLUDE_NULL_IFACES = True

    def __init__(self, *args):
        super().__init__(*args)
        self._network = Network(*args)

    @abstractmethod
    def extra_mgmt_networks(self, action, output, device):
        pass

    def mgmt_network(
            self, action, output, device_id, network_id, mgmt_index):
        network_id = f'{network_id}-{device_id}'
        mac_address = self._resource_mgr.generate_mac_address(
            device_id, self.MGMT_OCTET - mgmt_index)

        self.network(action, output, device_id, network_id, None, mac_address)

    def isolated_network(self, action, output, device_id):
        network_id = generate_network_id(device_id, None)
        mac_address = self._resource_mgr.generate_mac_address(device_id, 0x00)

        self.network(
                action, output, device_id, network_id, None, mac_address,
                isolated=True)

    def network(self, action, output,
            device_id, network_id, path, mac_address, isolated=False):
        hypervisor = self._hypervisor_mgr.get_device_hypervisor(device_id)
        self._network(
                action, output, hypervisor, network_id, path, mac_address,
                isolated)

    def _extra_network(self, action, output, device_ids, network_id,
                       path, mac_octets):
        for device_id in device_ids:
            hypervisor = self._hypervisor_mgr.get_device_hypervisor(device_id)
            self._network(
                    action, output, hypervisor, network_id, path,
                    self._resource_mgr.generate_mac_address(*mac_octets))

    def _action(self, action, *args):
        device,  = args
        self.extra_mgmt_networks(action, self._output, device)
        if self.INCLUDE_NULL_IFACES:
            self.isolated_network(action, self._output, int(device.id))


class LinkNetworks(DomainNetworks):
    def extra_mgmt_networks(self, action, output, device):
        pass

    def link_network(
            self, action, output, device_id, network_id, other_device_id, path):

        mac_address = self._resource_mgr.generate_mac_address(
            *sorted((device_id, other_device_id)))

        self.network(action, output, device_id, network_id, path, mac_address)


class TopologyNetworks(VirtBase):
    MAC_OCTET_BASE = 0xff

    def __init__(self, *args):
        super().__init__(*args)
        self._network = Network(*args)

    @abstractmethod
    def extra_mgmt_networks(self, action, output, device_ids):
        pass

    def network(self, action, output, network_id, network_index):
        for hypervisor_index, hypervisor in enumerate(
                self._hypervisor_mgr.get_hypervisors()):
            self._network(
                    action, output, hypervisor, network_id, None,
                    self._resource_mgr.generate_mac_address(
                        self.MAC_OCTET_BASE - hypervisor_index,
                        0xff - network_index
                    ))

    def _extra_network(self, action, output, device_ids, network_id,
                       path, mac_octets):
        for hypervisor_index, hypervisor in enumerate(
                self._hypervisor_mgr.get_hypervisors()):
            self._network(
                    action, output, hypervisor, network_id, None,
                    self._resource_mgr.generate_mac_address(
                        mac_octets[0] - hypervisor_index, mac_octets[1]))

    def _action(self, action, *args):
        self.extra_mgmt_networks(action, self._output, None)

class UserTopologyNetworks(TopologyNetworks):
    MAC_OCTET_BASE = 0xaf

    def extra_mgmt_networks(self, action, output, device_ids):
        pass
