#!/usr/bin/python3
from abc import abstractmethod
from libvirt import (VIR_NETWORK_UPDATE_COMMAND_MODIFY,
                     VIR_NETWORK_SECTION_PORTGROUP)

from virt.connection import Connection, \
        generate_network_id, generate_network_name, generate_bridge_name
from virt.topology_status import \
        get_device_status, write_node_data, get_hypervisor_output_node
from virt.virt_base import VirtBase
from virt.template import xml_to_string

_ncs = __import__('_ncs')


class ConnectionLibvirt(Connection):
    def __init__(self, *args):
        super().__init__(*args)
        self._topology_networks = UserTopologyNetworks(*args)
        self._link_networks = LinkNetworks(*args)

    def network_action_allowed(self, action, device_ids):
        """
        Check if an action is allowed on a network given the states of the
        devices using the network
        """
        allow_states = {
                #Action     #Allowed device states
                'undefine': ('undefined', ),
                'define':   ('undefined', ),
                'destroy':  ('undefined', 'defined', 'unmanaged'),
                'create':   ('undefined', 'defined', 'unmanaged'),
                'update':   ('started', 'ready', 'sync-error')
                }

        if action in allow_states:
            if any(get_device_status(
                   self._domain_mgr.get_device_path(device_id))
                   not in allow_states[action]
                   for device_id in device_ids):
                return False
        return True

    def connection(
            self, action, output, device_id, iface_id, when, is_link_dest):

        # Libvirt networks don't need to respond actions on other the end
        # of the link
        if is_link_dest:
            return False

        # Libvirt networks should be defined/started before the domain and
        # stopped/undefined after the domain
        if action in ('undefine', 'destroy') and when == 'pre-domain':
            return False

        if action in ('define', 'create') and when == 'post-domain':
            return False

        (network_id, devices) = \
                self._network_mgr.get_interface_managed_network_info(
                        device_id, iface_id)
        path = self._network_mgr.get_iface_path(device_id, iface_id)

        if not network_id:
            return False

        link_dest = self._network_mgr.get_iface_link_dest(device_id, iface_id)

        if self.network_action_allowed(action, devices):
            if link_dest:
                self._link_networks.link_network(
                        action, output,
                        device_id, network_id, link_dest[0], path)
            else:
                self._topology_networks.network(
                        action, output, network_id,
                        self._network_mgr.get_network_index(network_id))
            return True

        return False


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
