from virt.connection_docker import ConnectionDocker
from virt.connection_libvirt import ConnectionLibvirt


class HypervisorManager():
    def __init__(self, hypervisors, topology, log):
        self._libvirt_connections = {
                hypervisor.name: ConnectionLibvirt(hypervisor)
                for hypervisor in hypervisors }
        self._docker_connections = {
                hypervisor.name: ConnectionDocker(hypervisor, log)
                for hypervisor in hypervisors }
        self._external_bridges = {
                hypervisor.name: hypervisor.external_bridge
                for hypervisor in hypervisors }
        self._udp_tunnel_ip_addresses = {
                hypervisor.name: hypervisor.udp_tunnel_ip_address
                for hypervisor in hypervisors }
        self._hypervisors = {
                int(device.id): device.hypervisor or topology.libvirt.hypervisor
                for device in topology.devices.device}
        self._log = log

    def get_libvirt(self, hypervisor_name):
        libvirt_conn = self._libvirt_connections[hypervisor_name]
        if libvirt_conn.conn is None:
            libvirt_conn.connect()
            libvirt_conn.populate_cache()
        return libvirt_conn

    def get_docker(self, hypervisor_name):
        docker_conn = self._docker_connections[hypervisor_name]
        if docker_conn.conn is None:
            docker_conn.connect()
            docker_conn.populate_cache()
        return docker_conn

    def get_device_libvirt(self, device_id):
        return self.get_libvirt(self._hypervisors[int(device_id)])

    def get_device_docker(self, device_id):
        return self.get_docker(self._hypervisors[int(device_id)])

    def get_external_bridge(self, hypervisor_name):
        return self._external_bridges[hypervisor_name]

    def get_device_hypervisor(self, device_id):
        return self._hypervisors[device_id]

    def get_device_udp_tunnel_ip_address(self, device_id):
        return self._udp_tunnel_ip_addresses[self._hypervisors[device_id]]
