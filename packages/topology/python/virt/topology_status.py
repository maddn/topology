#!/usr/bin/python3
import time
import ncs
from ncs import maapi, maagic, OPERATIONAL
from ncs.dp import Action
_ncs = __import__('_ncs')

ACTION_STATUS_MAP = {
    'define': 'defined',
    'create': 'not-reachable',
    'shutdown': 'defined',
    'destroy': 'defined',
    'undefine': 'undefined'}

def get_status(node):
    with maapi.single_read_trans('admin', 'python', db=OPERATIONAL) as trans:
        return maagic.get_node(trans, node._path).status

def update_status(node, status):
    with maapi.single_write_trans('admin', 'python', db=OPERATIONAL) as trans:
        trans.set_elem(status, f'{node._path}/status')
        trans.apply()

def update_status_after_action(node, action, unmanaged=False):
    if unmanaged and action == 'create':
        update_status(node, 'unmanaged')
    else:
        update_status(node, ACTION_STATUS_MAP[action])

def schedule_topology_ping(keypath):
    with maapi.single_write_trans('admin', 'python') as trans:
        topology = maagic.get_node(trans, keypath)
        template_vars = ncs.template.Variables()
        template_vars.add('PATH', _ncs.xpath_pp_kpath(keypath))
        template = ncs.template.Template(topology)
        template.apply('schedule-ping-template', template_vars)
        trans.apply()

def unschedule_topology_ping(topology_name):
    with maapi.single_write_trans('admin', 'python') as trans:
        trans.safe_delete(f'/scheduler/task{{ping-topology-{topology_name}}}')
        trans.apply()


class TopologyStatus():
    def __init__(self, log):
        self.log = log
        self.device_states = {}

    def update_device_status(self, topology_device, status):
        self.device_states[topology_device.device_name] = status
        update_status(topology_device, status)

    def ping_device(self, topology_device, root):
        device_name = topology_device.device_name
        nso_device = root.devices.device[device_name]
        self.log.info(f'Pinging {device_name}...')
        device_ping = nso_device.ping()
        self.log.info(device_ping.result)
        if ' 0% packet loss' not in device_ping.result:
            self.update_device_status(topology_device, 'not-reachable')
            return False

        if topology_device.status == 'not-reachable':
            self.update_device_status(topology_device, 'reachable')
        return True

    def fetch_ssh_host_keys(self, topology_device, root):
        device_name = topology_device.device_name
        nso_device = root.devices.device[device_name]
        self.log.info(f'Fetching SSH host keys on {device_name}...')
        nso_device.ssh.fetch_host_keys()

    def sync_device(self, topology_device, root):
        device_name = topology_device.device_name
        nso_device = root.devices.device[device_name]
        self.log.info(f'Syncing {device_name}...')
        nso_device_sync = nso_device.sync_from()
        self.log.info(nso_device_sync.result)
        if not nso_device_sync.result:
            self.update_device_status(topology_device, 'sync-error')
        else:
            self.update_device_status(topology_device, 'ready')

    def check(self, topology):
        root = maagic.get_root(topology)
        reachable_devices = [ device
            for device in topology.devices.device
            if root.topologies.libvirt.device_definition[
                    device.definition].ned_id is not None and
                device.status != 'ready' and
                self.ping_device(device, root) ]

        with maapi.single_read_trans('admin', 'python') as trans:
            root = maagic.get_root(trans)
            for device in reachable_devices:
                self.fetch_ssh_host_keys(device, root)

        time.sleep(2)
        with maapi.single_read_trans('admin', 'python') as trans:
            root = maagic.get_root(trans)
            for device in reachable_devices:
                self.sync_device(device, root)

        if all(status == 'ready' for status in self.device_states.values()):
            topology_status = 'ready'
            unschedule_topology_ping(topology.name)
        elif any(status == 'sync-error'
                 for status in self.device_states.values()):
            topology_status = 'sync-error'
        else:
            topology_status = 'not-reachable'

        update_status(topology, topology_status)
        return self.device_states


class CheckTopologyStatus(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)

        if input.frequency == 'schedule':
            schedule_topology_ping(kp)
        else:
            for (device, status) in TopologyStatus(self.log).check(
                    maagic.get_node(trans, kp)).items():
                output_device = output.device.create()
                output_device.name = device
                output_device.status = status
