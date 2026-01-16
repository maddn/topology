#!/usr/bin/python3

from virt.virt_factory import VirtFactory
from virt.domain_docker import DomainDocker


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
        xr_interfaces = ';'.join([ f'linux:{
                self._generate_iface_dev_name(device.id, iface[0])
                },xr_name=GigabitEthernet0/0/0/{iface[0]}'
            for idx, iface in enumerate(ifaces) if iface[0] is not None ])

        return [
                'XR_EVERY_BOOT_CONFIG=/startup.cfg',
                f'XR_MGMT_INTERFACES=linux:{self._get_mgmt_iface(device)}',
                f'XR_INTERFACES={xr_interfaces}'
        ]
