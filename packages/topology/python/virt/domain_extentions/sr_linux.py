#!/usr/bin/python3

from virt.virt_factory import VirtFactory
from virt.domain_docker import DomainDocker


@VirtFactory.register_domain('SR-Linux')
class SrLinuxDomain(DomainDocker):
    CONFIG_TARGET = '/etc/opt/srlinux/startup-config.cli'
    COMMAND = 'sudo bash /opt/srlinux/bin/sr_linux'
    POST_START_COMMANDS = [
         'sudo bash -c \'while ! /opt/srlinux/bin/sr_cli -d "info from state system app-management application mgmt_server state" | grep running; do sleep 1; done\'',
         'sudo bash -c \'while ! cat /etc/opt/srlinux/devices/app_ephemeral.mgmt_server.ready_for_config | grep "loaded initial configuration"; do sleep 1; done\'',
        f'sudo bash -c "/opt/srlinux/bin/sr_cli -ed < {CONFIG_TARGET}"',
         'sudo bash -c "/opt/srlinux/bin/sr_cli -ed commit save"'
    ]
    PRIVILEGED = True

    def _get_mgmt_iface(self, device):
        return 'eth0'

    def _get_domain_env(self, device):
        return None

    def _generate_iface_dev_name(self, device_id, iface_id):
        return f'e1-{iface_id}'
