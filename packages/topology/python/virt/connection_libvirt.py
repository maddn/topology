#!/usr/bin/python3
from virt.network import UserTopologyNetworks, LinkNetworks
from virt.network import Connection
from virt.topology_status import get_device_status

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
