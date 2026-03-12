#!/usr/bin/python3
from dataclasses import dataclass
from ipaddress import IPv4Address
from ncs import maagic, maapi, OPERATIONAL

from virt.topology_status import write_node_data
from virt.virt_base import VirtBase

_ncs = __import__('_ncs')


@dataclass
class InterfaceEndpoint:
    """Represents one end of a network link"""
    device_name: str
    interface_name: str
    is_container: bool


@dataclass
class GeneveInfo:
    remote_ip_address: str
    vni: int
    interface_name: str


def generate_network_id(device_id, other_id):
    return f'{device_id}-{other_id or "null"}'

def generate_network_name(network_id):
    return f'net-{network_id}'

def generate_bridge_name(network_id):
    return f'vbr-{network_id}'

def generate_iface_dev_name(device_id, other_id):
    return f'veth-{device_id}-{other_id}'

def generate_geneve_iface_name(device_id, iface_id):
    return f'gtun-{device_id}-{iface_id}'

def generate_link_network_id(device_ids):
    return generate_network_id(*sorted(device_ids))

def generate_udp_port(device_id, iface_id):
    return f'1{device_id:02d}{iface_id:02d}'

def generate_geneve_vni(device_ids):
    device_id_1, device_id_2 = sorted(device_ids)
    return (device_id_1 * 1000 + device_id_2) % 16777216

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


class ConnectionManager():
    """
        This class is responsible for assigning and tracking topology
        connectivity. That is, what each device interface is connected
        to and, if applicable, the lifecycle of the connected network.

        There are two types of data connection possible in the topology
        definition:

        - Link: A point-to-point connection between two device interfaces.

        - Network: A managed or unmanaged bridge containing one or more
          device interfaces.

        To implement these, a device interface can be connected to:
            - A libvirt managed network (links or networks)
            - An external existing bridge (links or networks)
            - Another interface (links only):
                - Libvirt UDP networking (VM-VM)
                - GENEVE overlay networking (container-* cross hypervisor)
                - veth pair (container-container same host)
                - Tap interface in container namespace (container-VM same host)

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
        def _add_interface(key, path, network, bridge,
                           dest=None, udp=False, geneve=False):
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

            if geneve and dest:
                self._geneve_ifaces[key] = (
                    hypervisor_mgr.get_device_geneve_tunnel_ip_address(dest[0]),
                    generate_geneve_vni((key[0], dest[0])))

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
        self._geneve_ifaces = {}
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
            cross_host = hypervisors[0] != hypervisors[1]

            # First get requested bridges from the topology definition for
            # cross-host connectivity. Never fallback to default hypervisor
            # bridges if no link-specific bridges are given at all (in this
            # case UDP or GENEVE will be used)
            if (cross_host and
                    (link.external_connection.a_end_bridge is not None or
                     link.external_connection.z_end_bridge is not None)):
                bridges = (link.external_connection.a_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[0]),
                           link.external_connection.z_end_bridge or
                           hypervisor_mgr.get_external_bridge(hypervisors[1]))

            # Next check if the domain specifically requires bridges networking.
            # If so allocate a network_id so a libvirt managed network will
            # be used (and automatically create a managed bridge).
            network_id = generate_link_network_id(device_ids) if (
                    not all(bridges) and (
                    self._domain_mgr.need_bridge_networking(device_ids[0]) or
                    self._domain_mgr.need_bridge_networking(device_ids[1])
                    )) else None

            # If bridges are not required at all, and both ends are Libvirt
            # VMs, use Libvirt UDP overlay.
            use_udp = (not network_id and not all(bridges) and
                    not self._domain_mgr.is_container(device_ids[0]) and
                    not self._domain_mgr.is_container(device_ids[1]))

            # If UDP can't be used for cross-host connectivity (at least one
            # end is a container) use GENEVE overlay.
            use_geneve = (not network_id and not use_udp and
                cross_host and not all(bridges))

            _add_interface((device_ids[0], iface_ids[0]),
                    f'{link._path}/a-end-interface', network_id, bridges[0],
                    (device_ids[1], iface_ids[1]), use_udp, use_geneve)
            _add_interface((device_ids[1], iface_ids[1]),
                    f'{link._path}/z-end-interface', network_id, bridges[1],
                    (device_ids[0], iface_ids[0]), use_udp, use_geneve)

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
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._network_ifaces.get((int(device_id), iface_id), None)

    def get_iface_link_dest(self, device_id, iface_id):
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._link_ifaces.get((int(device_id), iface_id), None)

    def get_iface_bridge_name(self, device_id, iface_id):
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._bridge_ifaces.get((int(device_id), iface_id), None)

    def get_iface_path(self, device_id, iface_id):
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._connected_ifaces.get((int(device_id), iface_id), None)

    def get_iface_geneve_vni(self, device_id, iface_id):
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._geneve_ifaces.get((int(device_id), iface_id), None)

    def get_network_index(self, network_id):
        return self._network_index[network_id]

    def write_iface_data(self, device_id, iface_id, data):
        path = self.get_iface_path(device_id, iface_id)
        if path:
            write_node_data(path, data)

    def get_network_udp_ports(self, device_id, iface_id):
        device_id = self._domain_mgr.resolve_control_plane_id(device_id)
        return self._udp_ifaces.get((int(device_id), iface_id), None)

    def get_num_device_ifaces(self):
        return self._max_iface_id + 1

    def get_interface_geneve_info(self, device_id, iface_id):
        """
        If this interface uses a GENEVE overlay link, return a GeneveInfo.
        Otherwise None.
        """
        geneve = self.get_iface_geneve_vni(device_id, iface_id)
        if geneve is None:
            return None

        (remote_ip_address, vni) = geneve
        iface_name = generate_geneve_iface_name(device_id, iface_id)
        return GeneveInfo(
            remote_ip_address=remote_ip_address,
            vni=vni,
            interface_name=iface_name)

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

        key_dev = self._domain_mgr.resolve_control_plane_id(device_id)
        devices = [device
                for (device, _), network in self._network_ifaces.items()
                if network == network_id and device != key_dev]

        return (network_id, devices)

    def get_interface_direct_link_info(self, device_id, iface_id):
        """
        If this interface is a direct link interface (not using a libvirt
        network, unmanaged bridge or overlay), return the other end of the link

        Returns a tuple of (other_device_id, other_iface_id):
        - other_device_id: the device on the other end
        - other_iface_id: the interface on the other end

        Returns a tuple of (None, None) if the interface is not the end of a
        link of if the link uses a managed libvirt network or unmanaged bridge.
        """
        network_id = self.get_iface_network_id(device_id, iface_id)
        bridge_name = self.get_iface_bridge_name(device_id, iface_id)
        link_dest = self.get_iface_link_dest(device_id, iface_id)
        geneve = self.get_iface_geneve_vni(device_id, iface_id)

        if not network_id and not bridge_name and link_dest and not geneve:
            return link_dest

        return (None, None)

    def get_interface_any_bridge_info(self, device_id, iface_id):
        """
        Check if this interface is connected to any bridge (managed through
        a libvirt network or unmanaged)

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
