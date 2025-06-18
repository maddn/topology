#!/usr/bin/python3
from abc import abstractmethod
import ncs
from ncs import maapi
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
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)

        self._define(device)

        get_hypervisor_output_node(
                self._output, libvirt.name).domains.create(device.device_name)

        if dev_def.ned_id is not None:
            self._log.info(f'Creating device {device.device_name} in NSO')
            nso_device_onboard(device._path)

    def undefine(self, device):
        dev_def = self._dev_defs[device.definition]

        if self._undefine(device):
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

            if dev_def.ned_id is not None:
                nso_device_delete(device.device_name)

    @abstractmethod
    def _define(self, _):
        return False

    @abstractmethod
    def _undefine(self, _):
        return False

    @abstractmethod
    def shutdown_supported(self):
        pass
