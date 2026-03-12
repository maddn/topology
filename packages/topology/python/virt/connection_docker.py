from virt.ssh import CommandExecutionError
from virt.connection import Connection
from virt.topology_status import get_device_status


class ConnectionDocker(Connection):
    """
    Orchestrates network plumbing operations across multiple hypervisors.

    Provides high-level interface for domains to request plumbing of their
    interfaces. Determines the correct plumbing method based on what the
    interface is connected to (link vs network, same vs cross-hypervisor, etc.)
    """

    def __init__(self, *args):
        super().__init__(*args)
        self._plumbers = {}  # {hypervisor_name: InterfacePlumber}
        self._plumbed_link_interfaces = set()  # Track which interfaces we've already plumbed


    def _get_plumber(self, device_id):
        """
        Get or create InterfacePlumber for device.
        """
        hypervisor_name = self._hypervisor_mgr.get_device_hypervisor(device_id)
        if hypervisor_name not in self._plumbers:
            self._plumbers[hypervisor_name] = InterfacePlumber(
                hypervisor_name,
                self._hypervisor_mgr.get_docker(
                    hypervisor_name).get_ssh_executor(), self._log
            )

        return self._plumbers[hypervisor_name]

    def create(self, device_id, iface_id, when, is_link_dest):
        """
        Plumb a single interface on a device.
        Figures out what the interface is connected to and plumbs appropriately.

        This function is invoked for each interface on a device.

        For link interfaces, this function will plumb both ends of the link
        only when both ends are ready. Therefore we have to ensure it will be
        called again if the other end device is not ready yet. If the other end
        is not a container, it would not invoke this function for it's own
        interfaces. Therefore each domain interface invokes this function twice,
        once for it's own interface and again for the interface on the other
        end of the link. When the function is invoked for the other end of the
        link, the is_link_dest flag is set to True. This is needed for
        container to VM links.

        For a container (node-1:iface-2) to VM (node-2:iface-1) link, the
        invocations would look like this:
        - node-1 started:
            - node-1:iface-2
                - invoke action for current interface:
                    - device_id=1, iface_id=2, is_link_dest=False
                        -> device 1 is a container, this function is invoked
                        -> other end (node-2) not ready
                - invoke action for interface on other end of link:
                    - device_id=2, iface_id=1, is_link_dest=True
                        -> device 2 is a VM, this function is not invoked
        - node-2 started:
            - node-2:iface-1
                - invoke action for current interface:
                    - device_id=2, iface_id=1, is_link_dest=False
                        -> device 2 is a VM, this function is not invoked
                - invoke action for interface on other end of link:
                    - device_id=1, iface_id=2, is_link_dest=True
                        -> device 1 is a container, this function is invoked
                        -> other end (node-2) is ready, link is plumbed

        This is the only scenario that requires the is_link_dest flag.
        In all other scenarios either:
            - Plumbing is via a bridge or overlay and there is no need to wait.
              The interface is always plumbed
            - Both ends are containers so this function would be invoked
              anyway when the other end is started (in this case the function
              is invoked 4 times per link)

        Returns:
            True if plumbing was done, False if skipped (not ready yet)
        """
        #Interfaces can only be plumbed after the container has been created
        if when == 'pre-domain':
            return False

        (other_device_id, other_iface_id) = \
                self._connection_mgr.get_interface_direct_link_info(
                        device_id, iface_id)

        #Check if this interface is a direct link
        if other_device_id:
            return self._plumb_direct_link_interface(
                device_id, iface_id,
                other_device_id, other_iface_id, is_link_dest)

        if is_link_dest:
            # See function docstring. Only need to consider invocations when
            # is_link_dest is True for direct links where both interfaces are
            # plumbed together.
            return False

        geneve = self._connection_mgr.get_iface_geneve_vni(device_id, iface_id)

        if geneve:
            return self._plumb_overlay_interface(device_id, iface_id)

        bridge = self._connection_mgr.get_interface_any_bridge_info(
            device_id, iface_id)

        if bridge:
            return self._plumb_bridge_interface(device_id, iface_id, bridge)

        return False


    def shutdown(self, device_id, iface_id, when, is_link_dest):
        """
        Unplumb a single interface on a device.

        Called by domains before destroying a device. Cleans up network
        connections (deletes veth pairs, removes bridge attachments, etc.)

        Returns:
            True if unplumbing was done, False if skipped
        """

        #Link interfaces MUST be unplumbed before the container is shutdown
        if when == 'post-domain':
            return False

        (other_device_id, other_iface_id) = \
                self._connection_mgr.get_interface_direct_link_info(
                        device_id, iface_id)

        if other_device_id:
            #Direct link interface
            return self._unplumb_direct_link_interface(
                device_id, iface_id,
                other_device_id, other_iface_id, is_link_dest)

        geneve = self._connection_mgr.get_iface_geneve_vni(device_id, iface_id)

        if geneve and not is_link_dest:
            return self._unplumb_overlay_interface(device_id, iface_id)

        #Can leave bridge interfaces to be automatically removed when container
        #is shut down
        return False


    def _plumb_direct_link_interface(
            self, device_id, iface_id,
            other_device_id, other_iface_id, is_link_dest):
        """
        Plumb a direct point-to-point link interface where both ends need to
        be up before they can be connected (veth pair or tap-to-container)

        Returns:
            True if plumbing was done, False if waiting for other end
        """
        plumber = self._get_plumber(device_id)

        this_end = self._connection_mgr.get_interface_host_info(
                    device_id, iface_id)

        other_end = self._connection_mgr.get_interface_host_info(
                    other_device_id, other_iface_id)

        plumber.log_info(
            f'Checking link: from {this_end.device_name}:{iface_id} '
            f'[to {other_end.device_name}:{other_iface_id}]')

        # Check if we've already plumbed this interface
        if (device_id, iface_id) in self._plumbed_link_interfaces:
            plumber.log_info(
                f'Interface already plumbed: {this_end.device_name}:{iface_id}')
            return False

        (check_device_id, check_device_name) = (
                device_id, this_end.device_name) if is_link_dest else (
                        other_device_id, other_end.device_name)
        if get_device_status(
                self._domain_mgr.get_device_path(check_device_id)) not in (
                'started', 'ready', 'unmanaged'):
            plumber.log_info(
                f'Waiting for other device to be active: {check_device_name}')
            return False

        if other_end.is_container:
            # Direct veth pair
            if plumber.create_container_to_container_link(
                    this_end.device_name,
                    this_end.interface_name,
                    other_end.interface_name):
                self._plumbed_link_interfaces.add((device_id, iface_id))
                return True

        # Container to VM: move VM's TAP into container
        elif plumber.create_tap_to_container_link(
                this_end.device_name,
                this_end.interface_name,
                other_end.interface_name):  # TAP interface
            self._plumbed_link_interfaces.add((device_id, iface_id))
            return True

        return False


    def _plumb_overlay_interface(self, device_id, iface_id):
        """
        Plumb a point-to-point geneve overlay interface.
        """
        plumber = self._get_plumber(device_id)

        this_end = self._connection_mgr.get_interface_host_info(
                    device_id, iface_id)
        geneve = self._connection_mgr.get_interface_geneve_info(
                device_id, iface_id)

        return plumber.create_cross_host_container_link(
                this_end.device_name, this_end.interface_name,
                geneve.interface_name,
                geneve.remote_ip_address, geneve.vni)


    def _plumb_bridge_interface(
            self, device_id, iface_id, bridge_name):
        """
        Plumb a shared network interface (multi-device bridge).
        """

        endpoint = self._connection_mgr.get_interface_host_info(
                device_id, iface_id)

        plumber = self._get_plumber(device_id)

        # Create veth to bridge for this container
        return plumber.create_container_to_bridge_link(
            endpoint.device_name,
            endpoint.interface_name,
            bridge_name
        )

    def _unplumb_direct_link_interface(
            self, device_id, iface_id,
            other_device_id, other_iface_id, is_link_dest):
        """
        Unplumb a point-to-point direct link interface.

        Returns:
            True if unplumbing was done, False if already gone
        """

        iface_key = (device_id, iface_id)
        this_end = self._connection_mgr.get_interface_host_info(
                    device_id, iface_id)

        other_end = self._connection_mgr.get_interface_host_info(
                    other_device_id, other_iface_id)

        plumber = self._get_plumber(device_id)

        if iface_key in self._plumbed_link_interfaces:
            self._plumbed_link_interfaces.remove(iface_key)

        if other_end.is_container:
            if is_link_dest:
                # For container-to-container links only process this end of the
                # link. We don't know that the other end is being shutdown, it
                # maybe be a restart on this end, in which case we want to keep
                # other end of veth pair up.
                return False
            # Direct veth pair
            return plumber.destroy_container_to_container_link(
                this_end.device_name,
                this_end.interface_name,
                other_end.interface_name)

        return plumber.destroy_tap_to_container_link(
            this_end.device_name,       # Container name
            this_end.interface_name,
            other_end.interface_name    # TAP interface
        )


    def _unplumb_overlay_interface(self, device_id, iface_id):
        plumber = self._get_plumber(device_id)
        geneve = self._connection_mgr.get_interface_geneve_info(
                device_id, iface_id)

        return plumber.destroy_geneve_on_host(geneve.interface_name)


# MTU for GENEVE overlay so encapsulated frames are big enough to carry ISIS.
GENEVE_MTU = 1500


class InterfacePlumber:
    """
    Handles low-level network interface plumbing operations for containers.

    Generates shell commands (ip link, ip netns, etc.) and executes them
    via SshExecutor using persistent SSH connections.
    """

    def __init__(self, hypervisor_name, executor, log):
        self._hypervisor_name = hypervisor_name
        self._executor = executor
        self._log = log

    def log_info(self, message):
        self._log.info(f'[{self._hypervisor_name}] {message}')

    def log_warning(self, message):
        self._log.warning(f'[{self._hypervisor_name}] {message}')

    def execute(self, commands, description=None):
        return self._executor.execute(commands, description)

    def _interface_exists_in_container(self, container_name, interface_name):
        result = self.execute(
            f'docker exec {container_name} ip link show {interface_name}')
        return result['exit_code'] == 0

    def _interface_exists_on_host(self, interface_name):
        result = self.execute(f'ip link show {interface_name}')
        return result['exit_code'] == 0

    def _get_container_pid(self, container_name):
        result = self.execute(
            f"docker inspect -f '{{{{.State.Pid}}}}' {container_name}"
        )

        pid = result['stdout'].strip()
        # Let caller decide how to handle missing PID
        return pid if pid and pid != '0' else None

    def _get_container_pid_must_exist(self, container_name):
        # Get container PID and raise CommandExecutionError if not found
        # preserving the command execution error for better debugging
        result = self.execute(
            f"docker inspect -f '{{{{.State.Pid}}}}' {container_name}"
        )
        if result['exit_code'] != 0:
            raise CommandExecutionError(
                f'Failed to get PID for container {container_name}\n'
                f'stderr: {result["stderr"]}'
            )

        pid = result['stdout'].strip()
        return pid

    def _ensure_netns_link(self, pid):
        self.execute([
                'mkdir -p /var/run/netns',
                f'ln -sf /proc/{pid}/ns/net /var/run/netns/{pid}' ])

    def create_container_to_container_link(self,
            device_name, iface_name, other_iface_name):

        self.log_info(
            f'Checking veth pair: {iface_name} <--> {other_iface_name}'
        )

        # Check if interfaces already exist
        # May happen when restarting a container on the other end of this link
        if self._interface_exists_in_container(device_name, iface_name):
            self.log_info(
                f'--> Interface {iface_name} already exists in {device_name}'
            )
            return False

        pid = self._get_container_pid_must_exist(device_name)

        self._ensure_netns_link(pid)

        # Check if veth pair already exists on host
        # Only one end creates the pair, so check if it's already been created
        # by the other end of the link.
        if not self._interface_exists_on_host(iface_name):
            #Command must success so use command list version
            commands = [f'ip link add {iface_name} type veth '
                        f'peer name {other_iface_name}' ]
            self.execute(commands,
                f'--> Creating veth pair: {iface_name} <--> {other_iface_name}')

        # Move interface into container namespace and bring up
        # If the veth pair was just created, the over end will get moved
        # when the other end is processed (next call to this function)
        commands = [
            f'ip link set {iface_name} netns {pid}',
            f'ip netns exec {pid} ip link set {iface_name} up' ]

        self.execute(commands,
            f'--> Moving interface {iface_name} into container '
            f'{device_name} [namespace: {pid}]')

        return True

    def create_cross_host_container_link(
            self, device_name, container_iface_name,
            geneve_iface_name, remote_ip_address, vni):
        """
        Create GENEVE on the host and connect the container via macvtap on the
        GENEVE interface (cross-host link).
        """
        self.log_info(
            f'Checking overlay tunnel interface: '
            f'{device_name}:{container_iface_name} <--> '
            f'{geneve_iface_name} [host] / vni {vni}')

        if self._interface_exists_in_container(
                device_name, container_iface_name):
            self.log_info(
                f'--> Interface {container_iface_name} already in container')
            return False

        self.create_geneve_on_host(geneve_iface_name, vni, remote_ip_address)

        pid = self._get_container_pid_must_exist(device_name)
        self._ensure_netns_link(pid)

        commands = [
            f'ip link add link {geneve_iface_name} '
                        f'name {container_iface_name} type macvtap mode bridge',
            f'ip link set {container_iface_name} netns {pid}',
            f'ip netns exec {pid} ip link set {container_iface_name} up' ]

        self.execute(commands,
                f'--> Connecting container {device_name}:{container_iface_name} '
                f'to tunnel {geneve_iface_name} via macvtap')

        return True

    def create_geneve_on_host(self, iface_name, vni, remote_ip_address):
        self.log_info(
                f'Checking geneve interface {iface_name} on host')

        if self._interface_exists_on_host(iface_name):
            return

        commands = [
            f'ip link add {iface_name} '
                        f'type geneve id {vni} remote {remote_ip_address}',
            f'ip link set {iface_name} mtu {GENEVE_MTU}',
            f'ip link set {iface_name} up' ]

        self.execute(commands,
                f'--> Creating geneve interface {iface_name} [vni:{vni}] on host')

    def destroy_geneve_on_host(self, iface_name):
        self.log_info(f'Checking geneve interface {iface_name}')

        if not self._interface_exists_on_host(iface_name):
            return

        self.execute(
                [f'ip link delete {iface_name}'],
                f'--> Deleting geneve interface {iface_name}')

    def create_container_to_bridge_link(
            self, device_name, iface_name, bridge_name):

        self.log_info(
            f'Checking veth pair: '
            f'{device_name}:{iface_name} <--> bridge:{bridge_name}')

        # Check if interface already exists in container
        # Should not be possible since bridge interfaces are only processed
        # once (unlike direct link interfaces)
        # Don't fail but log warning if it already exists
        if self._interface_exists_in_container(device_name, iface_name):
            self.log_warning(
                f'--> Interface {iface_name} already exists in {device_name}')
            return False

        pid = self._get_container_pid_must_exist(device_name)
        self._ensure_netns_link(pid)
        host_iface = f'{iface_name}-host'

        commands = [
            f'ip link add {iface_name} type veth peer name {host_iface}',
            f'ip link set {iface_name} netns {pid}',
            f'ip link set {host_iface} master {bridge_name}',
            f'ip link set {host_iface} up',
            f'ip netns exec {pid} ip link set {iface_name} up' ]

        self.execute(commands,
                f'--> Creating veth pair: {device_name}:{iface_name} '
                f'[namespace: {pid}] <--> {bridge_name}:{host_iface}')

        return True

    def create_tap_to_container_link(
            self, device_name, container_iface, tap_iface):
        """
        Move tap interface into container and rename it
        """

        self.log_info(f'Checking tap interface: '
                      f'{tap_iface} --> {device_name}:{container_iface}')

        #Check tap interface has not already been moved
        if not self._interface_exists_on_host(tap_iface):
            if self._interface_exists_in_container(device_name, container_iface):
                self.log_info(
                    f'--> Interface {container_iface} already exists in container')
            else:
                self.log_warning(
                    f'--> Tap interface {tap_iface} does not exist on the host')
            return False

        pid = self._get_container_pid_must_exist(device_name)
        self._ensure_netns_link(pid)

        commands = [
            f'ip link set {tap_iface} down',
            f'ip link set {tap_iface} netns {pid}',
            f'ip netns exec {pid} ip link set {tap_iface} name {container_iface}',
            f'ip netns exec {pid} ip link set {container_iface} up' ]

        self.execute(commands,
            f'--> Moving tap {tap_iface} in to container '
            f'{device_name}:{container_iface} [namespace: {pid}]')

        return True

    def destroy_tap_to_container_link(
            self, device_name, container_iface, tap_iface):
        """
        Move ap interface back from container to host namespace.

        CRITICAL: This MUST be called BEFORE the container stops!

        When a container stops, the kernel destroys its network namespace,
        which would destroy any tap interfaces inside it. Since tap interfaces
        are owned by the VM, we need to move them back to the host namespace
        before the container stops so the VM doesn't lose connectivity.
        """
        self.log_info(
            f'Checking tap interface: '
            f'{tap_iface} <-- {device_name}:{container_iface}')

        #Tap interface may have already been removed and/or container may
        #already be stopped (valid scenario when this request is triggered by
        #other end of direct link)
        pid = self._get_container_pid(device_name)
        if not pid:
            self.log_info(f'--> Cannot get pid for container {device_name}')
            return False

        if not self._interface_exists_in_container(device_name, container_iface):
            self.log_info(
                f'--> Interface {container_iface} does not exist in container')
            return False

        # Move TAP back to host namespace (PID 1 = init namespace = host)
        commands = [
            f'ip netns exec {pid} ip link set {container_iface} down',
            f'ip netns exec {pid} ip link set {container_iface} name {tap_iface}',
            f'ip netns exec {pid} ip link set {tap_iface} netns 1',
            f'ip link set {tap_iface} up']

        self.execute(commands,
            f'--> Moving TAP {tap_iface} back to host from '
            f'{device_name}:{container_iface} [namespace: {pid}]')

        return True

    def destroy_container_to_container_link(self,
            device_name, iface_name, other_iface_name):
        """
        Move veth end out of container.
        Only delete veth if other end has already been moved out its
        container (so in the scenario where the device on this end is being
        restarted, there is no need to delete the veth pair, the other end of
        veth pair will stay in its container)
        """

        self.log_info(
            f'Checking veth pair: {iface_name} <--> {other_iface_name}'
        )
        #Container may already be stopped or veth may already have been
        #removed by other end.
        pid = self._get_container_pid(device_name)
        if not pid:
            self.log_info(f'--> Cannot get pid for container {device_name}')
            return False

        processed = False

        if self._interface_exists_in_container(device_name, iface_name):
            commands = [
                    f'ip netns exec {pid} ip link set {iface_name} down',
                    f'ip netns exec {pid} ip link set {iface_name} netns 1' ]

            self._executor.execute(commands,
                    f'--> Moving veth end: {device_name}:{iface_name} '
                    f'out of container [namespace: {pid}]')

            processed = True

        #Checked is other end has also been moved out of it's container
        if self._interface_exists_on_host(other_iface_name):
            # Delete interface (peer is deleted automatically)
            commands = [f'ip link delete {other_iface_name}']

            self.execute(commands,
                f'--> Deleting veth pair: '
                f'{iface_name} <--> {other_iface_name}')

            processed = True

        return processed
