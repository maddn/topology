#!/usr/bin/python3
"""
Base hypervisor: common host/SSH access. All concrete hypervisor types
(Docker, Libvirt, Vxr) inherit from this so SSH execution can be obtained
generically via any hypervisor handle.
"""

from virt.ssh import SshExecutor

_ncs = __import__('_ncs')


class Hypervisor:
    """Base for hypervisor connections. Provides host identity and SSH execution."""

    def __init__(self, hypervisor, log):
        self.name = hypervisor.name
        self._host = hypervisor.host
        self._username = hypervisor.username
        self._password = (
            _ncs.decrypt(hypervisor.password) if hypervisor.password is not None
            else None
        )
        self._log = log
        self._ssh_executor = None

    def get_ssh_executor(self):
        """Return a shared SshExecutor for this host. Creates it on first use."""
        if self._ssh_executor is None:
            self._ssh_executor = SshExecutor(
                name=self.name,
                log=self._log,
                host=self._host,
                username=self._username,
                password=self._password,
            )
        return self._ssh_executor
