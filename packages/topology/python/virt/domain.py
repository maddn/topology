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


class Domain(VirtBase):
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
