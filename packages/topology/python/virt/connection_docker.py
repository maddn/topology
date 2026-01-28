import docker
import subprocess

class ConnectionDocker():
    def __init__(self, hypervisor, log):
        self.conn = None
        self.name = hypervisor.name
        self._url = f'ssh://{hypervisor.host}'
        self._host = hypervisor.host
        self._tls_certs = None
        if hypervisor.tls.exists():
            self._url = f'tcp://{hypervisor.host}:2376'
            self._tls_certs = (
                    hypervisor.tls.client_certificate,
                    hypervisor.tls.client_key)
        self._log = log
        self.containers = {}
        self.networks = {}
        self.veths = []
        self.taps = []

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def connect(self):
        tls_config = docker.tls.TLSConfig(
                client_cert=self._tls_certs) if self._tls_certs else False
        self.conn = docker.DockerClient(
                base_url=self._url,
                tls=tls_config,
                use_ssh_client=not tls_config)

    def populate_cache(self):
        self._log.info(f'[{self.name}] Populating docker connection cache')
        self.populate_containers()
        self.populate_networks()

    def populate_containers(self):
        for container in self.conn.containers.list(all=True):
            self.containers[container.name] = {
                    'status': container.status
                    }

    def process_ip_link_output(self, output):
        """
        Parse 'ip link' output to extract interface information.

        Parses multi-line output where each interface has:
        - Line 1: index, name, flags, mtu, state
        - Line 2+: link type, MAC address, namespace info

        Extracts:
        - Interface index (kernel assigned, used for veth peer matching)
        - Interface name (strips @ifXX peer notation if present)
        - Peer index (from @ifXX notation, indicates veth pair)
        - Master bridge (from "master bridge_name" in flags)
        - MAC address (from link/ether line)
        - Namespace info (link-netns/link-netnsid for cross-namespace detection)

        Special handling:
        - Interfaces with link-netns that aren't numeric are probably internal
          ones created by the device and so are ignored
          (i.e. iface gway-2801 with link-netns srbase-default on SR Linux)
        - Interfaces with link-netnsid 0 (peer in host namespace) get key
          modified to "index@peer" to prevent collisions with other
          container-local interface indices. The matching logic will still work
          because we only match from the container and not from the host.

        Returns:
        dict: {interface_key: [name, peer, bridge, mac]}
        where interface_key is int (unique index)
        or str (index@peer for potential collisions)
        """
        ifaces = {}
        iface_index = None
        iface_peer = None
        for line in output.split('\n'):
            if len(line) > 0 and line[0].isdigit():
                parts = line.split(': ')
                if len(parts) >= 3:
                    iface_index = int(parts[0])
                    iface_name = parts[1]
                    iface_peer = None
                    master_name = None

                    # Get peer index for veth interfaces
                    if '@' in iface_name:
                        iface_name_parts = iface_name.split('@')
                        iface_name = iface_name_parts[0]
                        iface_peer = iface_name_parts[1].lstrip('if')

                    # Get master bridge name
                    if 'master' in parts[2]:
                        master_parts = parts[2].split()
                        master_index = master_parts.index('master')
                        if master_index + 1 < len(master_parts):
                            master_name = master_parts[master_index + 1]
                    ifaces[iface_index] = [iface_name, iface_peer, master_name]
            else:
                # Additional lines for the same interface
                if iface_index is not None:
                    # Extract MAC address
                    if 'link/' in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            mac_address = parts[1]
                            ifaces[iface_index].append(mac_address)
                    # If there is link-netns, make sure it is numerical
                    if 'link-netns' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == 'link-netns' and i + 1 < len(parts):
                                netns = parts[i + 1]
                                if not netns.isdigit():
                                    del ifaces[iface_index]
                                    iface_index = None  # Invalidate this iface
                    if 'link-netnsid' in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == 'link-netnsid' and i + 1 < len(parts):
                                netnsid = int(parts[i + 1])
                                if netnsid == 0:
                                    # Index may collide with other interfaces
                                    # So make it unique by adding peer
                                    index_with_peer = f'{iface_index}@{iface_peer}'
                                    ifaces[index_with_peer] = ifaces[iface_index]
                                    del ifaces[iface_index]
        return ifaces

    def _collect_all_interfaces(self):
        """
        Collect all network interfaces from host and containers.
        """
        ifaces = {}

        # Get host interfaces
        result = subprocess.run(["ssh", self._host, "ip link"],
                check=True, capture_output=True, text=True).stdout
        host_ifaces = self.process_ip_link_output(result)
        for index, (iface, peer, bridge, mac) in host_ifaces.items():
            ifaces[index] = ('<host>', iface, peer, bridge, mac)

        # Get container interfaces
        for container in self.conn.containers.list(all=True):
            if container.status == 'running':
                result = container.exec_run('ip link')
                container_ifaces = self.process_ip_link_output(result.output.decode())
                for index, (iface, peer, bridge, mac) in container_ifaces.items():
                    ifaces[index] = (container.name, iface, peer, bridge, mac)

        return ifaces

    def _classify_interfaces(self, ifaces):
        """
        Classify interfaces into veth pairs (container-to-container or
        container-to-host) and TAP interfaces (VM interfaces moved into
        containers).

        Classification logic:
        - veth pair: interface has a peer AND peer exists in our interface list
        - TAP: interface in container with NO peer (created by libvirt VM)

        Note: Some interface keys may be strings like "2@57" (index@peer) to
        avoid collisions, but peer values are always the numeric peer index.
        """
        veths = {}

        for index, (device, iface, peer, bridge, mac) in ifaces.items():
            # Only process container interfaces (not host)
            if device == '<host>':
                continue

            # Check if this is a veth pair (has peer)
            if peer is not None and int(peer) in ifaces:
                # It's a veth pair - create entry (avoid duplicates by using sorted key)
                (other_device, other_iface, _, other_bridge, *_) = ifaces[int(peer)]
                key = sorted((str(index), str(peer)))
                veths[f'{key[0]}-{key[1]}'] = {
                    'interfaces': [
                        { 'container': device,
                           'name': iface,
                           'bridge': bridge },
                        { 'container': other_device,
                           'name': other_iface,
                           'bridge': other_bridge }
                    ]
                }
            # Check if this is a TAP interface (no peer)
            elif peer is None:
                self.taps.append({
                    'container': device,
                    'name': iface,
                    'mac-address': mac,
                    'bridge': bridge
                })

        self.veths = list(veths.values())

    def populate_networks(self):
        # Collect docker network membership
        for network in self.conn.networks.list(greedy=True):
            self.networks[network.name] = {
                    'containers': [ { 'name': container.name }
                        for container in network.containers
                        ]
                    }

        # Collect all interfaces indexed by kernel interface index
        ifaces = self._collect_all_interfaces()

        # Classify interfaces as veth pairs or TAPs
        self._classify_interfaces(ifaces)

    def create_network(self, bridge_name, subnet, internal=True):
        if bridge_name not in self.networks:
            self._log.info(
                    f'[{self.name}] Creating docker network {bridge_name}')
            self.conn.networks.create(
                name=bridge_name,
                driver='bridge',
                options={
                    'com.docker.network.bridge.name': bridge_name,
                    'com.docker.network.bridge.inhibit_ipv4': 'true',
                    'com.docker.network.bridge.enable_ip_masquerade': 'false'
                },
                ipam=docker.types.IPAMConfig(
                    driver='default',
                    pool_configs=[
                        docker.types.IPAMPool(
                            subnet=subnet
                        )
                    ]
                ) if subnet else None,
                internal=internal
            )
            self.networks[bridge_name] = { 'containers': [] }

    def delete_network(self, bridge_name):
        if bridge_name in self.networks:
            network = self.conn.networks.get(bridge_name)
            if len(network.containers) == 0:
                self._log.info(
                        f'[{self.name}] Deleting docker network {bridge_name}')
                network.remove()
                del self.networks[bridge_name]

    def create(self,
               container_name,
               image_name,
               mac_address,
               mgmt_bridge,
               mgmt_ip_address,
               networks,
               environment,
               capabilities,
               command,
               config_target,
               devices,
               privileged):
        self._log.info(f'[{self.name}] Creating container {container_name}')
        networking_config=({
            mgmt_bridge: self.conn.api.create_endpoint_config(
                ipv4_address=mgmt_ip_address
            )
        })
        for network in networks:
            networking_config[network] = self.conn.api.create_endpoint_config(
                mac_address=networks[network]
            )
        self.conn.containers.create(
                name=container_name,
                cap_add=capabilities,
                command=command,
                detach=True,
                devices=devices,
                environment=environment,
                image=image_name,
                mac_address=mac_address,
                mounts=[
                    docker.types.Mount(
                        target=config_target,
                        source=f'/var/lib/libvirt/images/{container_name}-day0.img',
                        type='bind'
                    )
                ] if config_target else None,
                network=mgmt_bridge,
                networking_config=networking_config,
                privileged=privileged,
                security_opt=[ 'apparmor=unconfined' ],
                stdin_open=True,
                tty=True)
        self.containers[container_name] = { 'status': 'created' }
        self.networks[mgmt_bridge]['containers'].append(container_name)

    def start(self, container_name):
        if (container_name in self.containers and
                    not self.is_active(container_name)):
            self._log.info(f'[{self.name}] Starting container {container_name}')
            container = self.conn.containers.get(container_name)
            container.start()

    def stop(self, container_name):
        if container_name in self.containers and self.is_active(container_name):
            self._log.info(f'[{self.name}] Stopping container {container_name}')
            container = self.conn.containers.get(container_name)
            container.stop()

    def remove(self, container_name):
        if (container_name in self.containers and
                    not self.is_active(container_name)):
            self._log.info(f'[{self.name}] Removing container {container_name}')
            container = self.conn.containers.get(container_name)
            container.remove()
            del self.containers[container_name]

    def connect_network(self, container_name, network_name):
        self._log.info(
                f'[{self.name}] Connecting network {network_name} '
                f'to container {container_name}')
        network = self.conn.networks.get(network_name)
        network.connect(container_name)

    def disconnect_network(self, container_name, network_name):
        if network_name in self.networks:
            self._log.info(
                    f'[{self.name}] Disconnecting network {network_name} '
                    f'from container {container_name}')
            network = self.conn.networks.get(network_name)
            network.disconnect(container_name)

    def is_active(self, container_name):
        return container_name in (
                container.name for container in self.conn.containers.list() )
