from abc import abstractmethod

from virt.domain import Domain
from virt.network import generate_bridge_name, generate_iface_dev_name
from virt.topology_status import write_node_data, get_hypervisor_output_node


class DomainDocker(Domain):

    SHUTDOWN_SUPPORTED = True
    CAPABILITIES = []
    COMMAND = None
    CONFIG_TARGET = None
    DEVICES = []
    PRIVILEGED = False
    POST_START_COMMANDS = []

    @abstractmethod
    def _get_domain_env(self, device):
        pass

    @abstractmethod
    def _get_mgmt_iface(self, device):
        pass

    def _generate_iface_dev_name(self, device_id, iface_id):
        return generate_iface_dev_name(device_id, iface_id)

    def get_docker_ifaces(self, device, first_iface = 0, device_id = None):
        device_id = int(device.id)
        docker_ifaces = []
        for iface_id in range(first_iface,
                self._network_mgr.get_num_device_ifaces()):
            bridge_name = self._network_mgr.get_iface_bridge_name(
                    device_id or device_id, iface_id)
            network_id = self._network_mgr.get_iface_network_id(
                    device_id or device_id, iface_id)

            if network_id:
                bridge_name = generate_bridge_name(network_id)

            if bridge_name:
                docker_ifaces.append(( iface_id, bridge_name ))

        docker_ifaces.append(( None, self._resource_mgr.mgmt_bridge ))
        return sorted(docker_ifaces, key=lambda x: x[1])

    def _define(self, device):
        device_name = device.device_name
        docker = self._hypervisor_mgr.get_device_docker(device.id)
        self._log.info(f'[{docker.name}] Defining domain {device_name}')

        dev_def = self._dev_defs[device.definition]
        docker.create_network(
                self._resource_mgr.mgmt_bridge,
                self._resource_mgr.generate_mgmt_subnet(),
                False)

        mgmt_ip_address = self._resource_mgr.generate_mgmt_ip_address(device.id)

        ifaces = self.get_docker_ifaces(device)
        for (iface_id, _) in ifaces:
            if iface_id is not None:
                mac_address = self._resource_mgr.generate_mac_address(
                        device.id, iface_id, True)
                self._network_mgr.write_iface_data( device.id, iface_id, [
                        ('id', iface_id),
                        ('host-interface', self._generate_iface_dev_name(
                                           device.id, iface_id)),
                        ('mac-address', mac_address),
                        ('../destroy-behaviour', 'immediate')])

        mac_address = self._resource_mgr.generate_mac_address(device.id, 0xff, True)

        docker.create(
                device.device_name,
                dev_def.base_image,
                mac_address,
                self._resource_mgr.mgmt_bridge,
                mgmt_ip_address,
                [],
                self._get_domain_env(device),
                self.CAPABILITIES,
                self.COMMAND,
                self.CONFIG_TARGET,
                self.DEVICES,
                self.PRIVILEGED)

        write_node_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address),
                ('host-interface', self._get_mgmt_iface(device))])

    def _undefine(self, device):
        return self._action('undefine', device)

    def undefine_container(self, docker, device):
        docker.remove(device.device_name)
        docker.delete_network(self._resource_mgr.mgmt_bridge)

    def create_container(self, docker, device):
        docker.start(device.device_name)

        docker.post_start_commands(
                device.device_name,
                self.POST_START_COMMANDS)

    def shutdown_container(self, docker, device):
        docker.stop(device.device_name)

    def is_active(self, device):
        docker = self._hypervisor_mgr.get_device_docker(device.id)
        return docker and docker.is_active(device.device_name)

    def shutdown_supported(self):
        return self.SHUTDOWN_SUPPORTED

    def _action(self, action, *args):
        device, = args
        container_name = device.device_name
        docker = self._hypervisor_mgr.get_device_docker(device.id)
        if docker and container_name in docker.containers:
            action_name = f'{action}_container'
            if hasattr(self, action_name):
                self._log.info(
                        f'[{docker.name}] '
                        f'Running {action} on container {container_name} ')
                action_method = getattr(self, action_name)
                action_method(docker, *args)

                get_hypervisor_output_node(
                        self._output, docker.name).domains.create(container_name)
                return True
        return False
