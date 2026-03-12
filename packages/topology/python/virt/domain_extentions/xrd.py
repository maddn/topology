#!/usr/bin/python3

from virt.virt_factory import VirtFactory
from virt.domain_docker import DomainDocker
from virt.connection_docker import ConnectionDocker


@VirtFactory.register_connection('XRd')
class XrdConnection(ConnectionDocker):

    def _exec(self, device_id, command):
        docker = self._hypervisor_mgr.get_device_docker(device_id)
        device_name = self._domain_mgr.get_device_name(device_id)
        return docker.exec(device_name, command)

    def _plumb_direct_link_interface(
            self, device_id, iface_id, other_device_id, other_iface_id, is_link_dest):

        (exit_code, output) = self._exec(device_id,
                f'ip netns exec vrf-default ip link show Gi0_0_0_{iface_id}')
        is_existing_interface = exit_code == 0

        if super()._plumb_direct_link_interface(
                device_id, iface_id,
                other_device_id, other_iface_id, is_link_dest):

            if is_existing_interface:
                # Interface was just plumbed even though XRD container already
                # had this interface.
                self._log.info(
                    'Interface inside XRd device updated. '
                    'Removing old interface and restarting spp.')
                self._exec(device_id,
                        f'ip netns exec vrf-default '
                        f'ip link delete Gi0_0_0_{iface_id}')
                self._exec(device_id, 'killall spp')

            return True

        return False


@VirtFactory.register_domain('XRd')
class XRdDomain(DomainDocker):
    CONFIG_TARGET = '/startup.cfg'
    CAPABILITIES = [
        'NET_ADMIN',
        'SYS_ADMIN',
        'IPC_LOCK',
        'SYS_NICE',
        'SYS_PTRACE',
        'SYS_RESOURCE'
    ]
    DEVICES = [
        '/dev/fuse',
        '/dev/net/tun'
    ]

    def _get_mgmt_iface(self, device):
        return 'eth0'

    def _get_domain_env(self, device):
        ifaces = self.get_docker_ifaces(device)
        xr_interfaces = ';'.join([ f'linux:'
                f'{self._generate_iface_dev_name(device.id, iface)}'
                f',xr_name=GigabitEthernet0/0/0/{iface}'
            for iface in ifaces ])

        return [
                'XR_EVERY_BOOT_CONFIG=/startup.cfg',
                f'XR_MGMT_INTERFACES=linux:{self._get_mgmt_iface(device)}',
                f'XR_INTERFACES={xr_interfaces}'
        ]
