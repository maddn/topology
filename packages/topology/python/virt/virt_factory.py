#!/usr/bin/python3
from ipaddress import IPv4Interface
from ncs import maagic

from virt.hypervisor import HypervisorManager
from virt.network import NetworkManager, generate_ip_address


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

    def generate_mgmt_subnet(self):
        return str(IPv4Interface(f'{self._mgmt_ip_address_start}/24').network)

    def get_authgroup_mapping(self, authgroup_name):
        authgroup = self._authgroups[authgroup_name]
        return authgroup.umap[self._username] if (
                self._username in authgroup.umap) else authgroup.default_map


class VirtFactory():
    domain_registry = {}
    volume_registry = {}
    domain_networks_registry = {}
    topology_networks_registry = {}

    def __init__(self, username, topology, dev_defs, log):
        hypervisor_name = topology.libvirt.hypervisor
        hypervisors = maagic.cd(topology, '../libvirt/hypervisor')
        hypervisor = hypervisors[hypervisor_name]

        self._hypervisor_mgr = HypervisorManager(hypervisors, topology, log)
        self._resource_mgr = ResourceManager(hypervisor, username)
        self._network_mgr = NetworkManager(topology, self._hypervisor_mgr, dev_defs)
        self._dev_defs = maagic.cd(topology, '../libvirt/device-definition')
        self._log = log

        self.topology = topology

    def create(self, cls):
        return cls(
                self._hypervisor_mgr,
                self._resource_mgr,
                self._network_mgr,
                self._dev_defs,
                self._log)

    def get_device_type(self, device):
        dev_def = self._dev_defs[device.definition]
        return str(dev_def.device_type)

    @classmethod
    def register_domain(cls, name):
        def inner_wrapper(wrapped_class):
            if name not in VirtFactory.domain_registry:
                VirtFactory.domain_registry[name] = wrapped_class
        return inner_wrapper

    @classmethod
    def register_volume(cls, name):
        def inner_wrapper(wrapped_class):
            if name not in VirtFactory.volume_registry:
                VirtFactory.volume_registry[name] = wrapped_class
        return inner_wrapper

    @classmethod
    def register_domain_networks(cls, name):
        def inner_wrapper(wrapped_class):
            if name not in VirtFactory.domain_networks_registry:
                VirtFactory.domain_networks_registry[name] = wrapped_class
        return inner_wrapper

    @classmethod
    def register_topology_networks(cls, name):
        def inner_wrapper(wrapped_class):
            if name not in VirtFactory.topology_networks_registry:
                VirtFactory.topology_networks_registry[name] = wrapped_class
        return inner_wrapper
