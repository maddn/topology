#!/usr/bin/python3
from abc import abstractmethod
import ncs
from ncs import maapi, maagic
from virt.virt_base import VirtBase
from virt.topology_status import write_node_data, get_hypervisor_output_node


def nso_device_onboard(path):
    with maapi.single_write_trans('admin', 'python') as trans:
        template = ncs.template.Template(trans, path)
        template.apply('nso-device-template', None)
        trans.apply()

def nso_device_delete(device_name):
    with maapi.single_write_trans('admin', 'python') as trans:
        trans.safe_delete(f'/devices/device{{{device_name}}}')
        trans.apply()

class DomainManager():
    def __init__(self, topology, domain_registry):
        dev_defs = maagic.cd(topology, '../libvirt/device-definition')

        self._device_ids_by_name = {}
        self._device_names = {}
        self._device_paths = {}
        self._device_types = {}
        self._domain_is_container = {}
        self._domain_needs_bridge_networking = {}

        for device in topology.devices.device:
            device_id = int(device.id)
            self._device_ids_by_name[device.device_name] = device_id
            self._device_names[device_id] = device.device_name
            self._device_paths[device_id] = device._path

            device_type = str(dev_defs[device.definition].device_type)
            domain_class = domain_registry.get(device_type)

            self._device_types[device_id] = device_type
            self._domain_is_container[device_id] = (
                    domain_class and domain_class.IS_CONTAINERIZED)
            self._domain_needs_bridge_networking[device_id] = (
                    domain_class and domain_class.BRIDGE_NETWORKING)

    def get_device_id(self, device_name):
        return self._device_ids_by_name.get(device_name, None)

    def get_device_name(self, device_id):
        return self._device_names.get(device_id, None)

    def get_device_path(self, device_id):
        return self._device_paths.get(device_id, None)

    def get_device_type(self, device_id):
        return self._device_types.get(device_id, None)

    def is_container(self, device_id):
        return self._domain_is_container.get(device_id, False)

    def need_bridge_networking(self, device_id):
        return self._domain_needs_bridge_networking.get(device_id, False)


class Domain(VirtBase):
    SHUTDOWN_SUPPORTED = False
    IS_CONTAINERIZED = False
    BRIDGE_NETWORKING = False

    def define(self, device):
        dev_def = self._dev_defs[device.definition]
        hypervisor = self._hypervisor_mgr.get_device_hypervisor(device.id)

        self._define(device)

        get_hypervisor_output_node(
                self._output, hypervisor).domains.create(device.device_name)

        if dev_def.ned_id is not None:
            self._log.info(f'Creating device {device.device_name} in NSO')
            nso_device_onboard(device._path)

    def undefine(self, device):
        real_hypervisor = self._hypervisor_mgr.has_real_hypervisor(device.id)

        if not real_hypervisor or self._undefine(device):
            dev_def = self._dev_defs[device.definition]
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
                            ('mac-address', None),
                            ('../destroy-behaviour', None)])

            if dev_def.ned_id is not None:
                self._log.info(f'Removing device {device.device_name} from NSO')
                nso_device_delete(device.device_name)

    def create(self, device):
        real_hypervisor = self._hypervisor_mgr.has_real_hypervisor(device.id)
        if real_hypervisor:
            self._action('create', device)
        else:
            self._log.info(f'Adding capabililty to {device.device_name}')
            dev_def = self._dev_defs[device.definition]
            nso_device = maagic.get_root(
                    device).devices.device[device.device_name]
            capability = nso_device.add_capability.get_input()
            for module in dev_def.capabilities:
                self._log.info(
                        f'Adding {module} capabililty to {device.device_name}')
                capability.ned_id = dev_def.ned_id
                capability.module = module
                nso_device.add_capability(capability)

    @abstractmethod
    def _define(self, _):
        return False

    @abstractmethod
    def _undefine(self, _):
        return False

    @abstractmethod
    def shutdown_supported(self):
        pass
