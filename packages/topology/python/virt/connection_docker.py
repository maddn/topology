import docker

class ConnectionDocker():
    def __init__(self, hypervisor, log):
        self.conn = None
        self.name = hypervisor.name
        self._url = f'ssh://{hypervisor.host}'
        self._tls_certs = None
        if hypervisor.tls.exists():
            self._url = f'tcp://{hypervisor.host}:2376'
            self._tls_certs = (
                    hypervisor.tls.client_certificate,
                    hypervisor.tls.client_key)
        self._log = log
        self.containers = []
        self.networks = []

    def connect(self):
        tls_config = docker.tls.TLSConfig(
                client_cert=self._tls_certs) if self._tls_certs else False
        self.conn = docker.DockerClient(
                base_url=self._url,
                tls=tls_config,
                use_ssh_client=not tls_config)

    def populate_cache(self):
        self.populate_containers()
        self.populate_networks()

    def populate_containers(self):
        self.containers = [ container.name
                for container in self.conn.containers.list(all=True) ]

    def populate_networks(self):
        self.networks = [
                network.name for network in self.conn.networks.list() ]

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
            self.networks.append(bridge_name)

    def delete_network(self, bridge_name):
        if bridge_name in self.networks:
            network = self.conn.networks.get(bridge_name)
            if len(network.containers) == 0:
                self._log.info(
                        f'[{self.name}] Deleting docker network {bridge_name}')
                network.remove()
                self.networks.remove(bridge_name)

    def create(self, container_name, image_name,
               mgmt_bridge, mgmt_ip_address, mac_address, environment, networks):
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
                cap_add=[
                    'NET_ADMIN',
                    'SYS_ADMIN',
                    'IPC_LOCK',
                    'SYS_NICE',
                    'SYS_PTRACE',
                    'SYS_RESOURCE'
                ],
                devices=[
                    '/dev/fuse',
                    '/dev/net/tun'
                ],
                security_opt=[
                    'apparmor=unconfined'
                ],
                environment=environment,
                mounts=[
                    docker.types.Mount(
                        target='/startup.cfg',
                        source=f'/var/lib/libvirt/images/{container_name}-day0.img',
                        type='bind'
                    )
                ],
                mac_address=mac_address,
                network=mgmt_bridge,
                networking_config=networking_config,
                image=image_name,
                stdin_open=True,
                tty=True,
                detach=True)
        self.containers.append(container_name)

    def start(self, container_name):
        if container_name in self.containers:
            self._log.info(f'[{self.name}] Starting container {container_name}')
            container = self.conn.containers.get(container_name)
            container.start()

    def stop(self, container_name):
        if container_name in self.containers:
            self._log.info(f'[{self.name}] Stopping container {container_name}')
            container = self.conn.containers.get(container_name)
            container.stop()

    def remove(self, container_name):
        if container_name in self.containers:
            self._log.info(f'[{self.name}] Removing container {container_name}')
            container = self.conn.containers.get(container_name)
            container.remove()
            self.containers.remove(container_name)

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
        return container_name in {
                container.name for container in self.conn.containers.list() }
