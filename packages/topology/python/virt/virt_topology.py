#!/usr/bin/python3
from time import sleep

import os

from ncs.dp import Action
from ncs import maagic
from virt.topology_status import \
        update_device_status_after_action, update_status_after_action, \
        schedule_topology_ping, unschedule_topology_ping

from virt.virt_factory import VirtFactory
from virt.virt_builder import VirtBuilder
from virt.topology_status import write_node_data

_ncs = __import__('_ncs')

PYTHON_DIR = os.path.dirname(__file__)


class Topology():
    def __init__(self, topology, log, output, username):
        hypervisor_name = topology.libvirt.hypervisor

        if hypervisor_name is None:
            raise Exception('No hypervisor defined for this topology')

        self._topology = topology
        self._dev_defs = maagic.cd(topology, '../libvirt/device-definition')
        self._output = output

        self._virt_builder = VirtBuilder(
                VirtFactory(username, topology, self._dev_defs, log))

    def action(self, action, device_name=None):
        output = self._output.libvirt_action.create()
        output.action = action

        if device_name is None:
            self._virt_builder.topology_networks(
                    action, output, self._topology.devices.device)

            for (idx, network) in enumerate(self._topology.networks.network):
                if not network.external_bridge:
                    self._virt_builder.extra_network(action, output, None,
                            network.name, network._path, (0xfe, 0xff-idx))

            for link in self._topology.links.link:
                self._virt_builder.link_network(action, output, link)

        for device in self._topology.devices.device:
            if device_name is not None and device.device_name != device_name:
                continue
            self._virt_builder.domain_networks(action, output, device)

            dev_def = self._dev_defs[device.definition]

            if action == 'define':
                self._virt_builder.volume(action, output, device)
            self._virt_builder.domain(action, output, device)
            if action != 'define':
                self._virt_builder.volume(action, output, device)
            update_device_status_after_action(device,
                    action, dev_def.ned_id is None)

    def wait_for_shutdown(self, device_name=None):
        timer = 0
        while any(self._virt_builder.is_domain_active(device)
                  for device in self._topology.devices.device
                  if (device_name is None or device.device_name == device_name)
                  and self._virt_builder.domain_supports_shutdown(device)
                  ) and timer < 60:
            sleep(10)
            timer += 10

    def get_virt_builder(self):
        return self._virt_builder


class LibvirtAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        topology = maagic.get_node(trans, kp[1:])

        action = name
        if action in ('start', 'define') and not (input.device or input.force):
            if (action == 'start' and
                    topology.provisioning_status != 'defined' or
                action == 'define' and
                    topology.provisioning_status != 'undefined'):
                return

        trans.maapi.install_crypto_keys()
        virt_topology = Topology(topology, self.log, output, uinfo.username)

        def run_action(name):
            action = name
            if name == 'start':
                action = 'create'
            elif name == 'stop':
                virt_topology.action('shutdown', input.device)
                virt_topology.wait_for_shutdown(input.device)
                action = 'destroy'

            virt_topology.action(action, input.device)
            update_status_after_action(topology, action)

            if name == 'start':
                schedule_topology_ping(kp[1:])

            if name == 'stop':
                unschedule_topology_ping(kp[1][0])

        if name in ('reboot', 'hard-reset'):
            run_action('stop')
            action = 'start'

        if name == 'hard-reset':
            run_action('undefine')
            virt_topology = None
            sleep(5)
            virt_topology = Topology(topology, self.log, output, uinfo.username)
            run_action('define')
            virt_topology = None
            sleep(5)
            virt_topology = Topology(topology, self.log, output, uinfo.username)

        run_action(action)


class LibvirtNetworkAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        link = maagic.get_node(trans, kp[1:])
        topology = maagic.get_node(trans, kp[4:])
        self.log.info(topology._path)

        action = name
        if name == 'start':
            action = 'create'
        elif name == 'stop':
            action = 'destroy'
        elif name == 'set-delay':
            write_node_data(link._path, [('libvirt/delay', input.delay)])
            action = 'update'

        action_output = output.libvirt_action.create()
        action_output.action = action

        virt_topology = Topology(topology, self.log, output, uinfo.username)
        virt_topology.get_virt_builder().link_network(
                action, action_output, link)
