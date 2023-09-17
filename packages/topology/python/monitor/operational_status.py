#!/usr/bin/python3
import threading
from ncs import maapi, maagic, OPERATIONAL
from ncs.dp import Action
from monitor.pinger import Pinger
_ncs = __import__('_ncs')


class PingerProcessManager(threading.Thread):
    def __init__(self, topology_name, topology_keypath, log):
        super().__init__()
        self._topology_name = topology_name
        self._topology_keypath = topology_keypath
        self._log = log
        self._pinger = None
        with maapi.single_read_trans(
                'admin', 'python', db=OPERATIONAL) as trans:
            topology = maagic.get_node(trans, self._topology_keypath)
            self._device_ip_addresses = {
                    device.device_name: device.management_interface.ip_address
                    for device in topology.devices.device }
            self._device_paths = { device.device_name: device._path
                                  for device in topology.devices.device }

    def _log_event(self, timestamp, device, event_type, ping_missed_packets):
        with maapi.single_write_trans(
                'admin', 'python', db=OPERATIONAL) as trans:
            topology = maagic.get_node(trans, self._topology_keypath)
            event = topology.state_events.event.create()
            event.timestamp = timestamp
            event.device = device
            event.event_type = event_type
            event.ping_missed_packets = ping_missed_packets
            trans.apply()

    def _update_device_status(self, device_name, status):
        with maapi.single_write_trans(
                'admin', 'python', db=OPERATIONAL) as trans:
            trans.set_elem(status,
                    f'{self._device_paths[device_name]}/operational-status')
            trans.apply()

    def stop(self):
        self._pinger.stop_event.set()

    def get_status(self):
        return ('running' if self._pinger.is_alive() else 'not-running',
                self._pinger.pid)

    def run(self):
        self._pinger = Pinger(
                self._topology_name, self._device_ip_addresses)
        self._pinger.start()

        try:
            while True:
                message = self._pinger.queue.get()
                if message == 'stop':
                    break
                [timestamp, device, event_type, data] = message
                event = f'{event_type} - {data}' if data else event_type
                self._log.info(f'{timestamp} {device}: {event}')
                self._log_event(timestamp, device, event_type, data)
                if event_type == 'online':
                    self._update_device_status(device, 'reachable')
                elif event_type == 'offline':
                    self._update_device_status(device, 'not-reachable')
        except:
            self.stop()
            raise
        finally:
            self._pinger.join()


class OperationalStateMonitor(Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinger_mgmt_threads = {}

    def start_pinger(self, topology_name, topology_keypath):
        if topology_name in self._pinger_mgmt_threads:
            (status, _) = self.pinger_status(topology_name)
            if status == 'not-running':
                self.stop_pinger(topology_name)

        if topology_name not in self._pinger_mgmt_threads:
            self.log.info(f'Starting {topology_name} pinger process')
            self._pinger_mgmt_threads[topology_name] = PingerProcessManager(
                    topology_name, topology_keypath, self.log)
            self._pinger_mgmt_threads[topology_name].start()

    def stop_pinger(self, topology_name):
        if topology_name in self._pinger_mgmt_threads:
            (status, _) = self.pinger_status(topology_name)
            if status == 'running':
                self.log.info(f'Stopping {topology_name} pinger process')
                pinger_mgmt_thread = self._pinger_mgmt_threads[topology_name]
                pinger_mgmt_thread.stop()
                pinger_mgmt_thread.join()
            del self._pinger_mgmt_threads[topology_name]

    def pinger_status(self, topology_name):
        if topology_name in self._pinger_mgmt_threads:
            return self._pinger_mgmt_threads[topology_name].get_status()
        return ('not-running', None)

    def stop(self):
        self.log.info('Stopping all pingers')
        pingers = list(self._pinger_mgmt_threads)
        for pinger in pingers:
            self.stop_pinger(pinger)
        super().stop()

    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)
        topology_name = str(kp[1][0])
        if name == 'start':
            self.start_pinger(topology_name, kp[1:])
        elif name == 'stop':
            self.stop_pinger(topology_name)
        elif name == 'status':
            (status, pid) = self.pinger_status(topology_name)
            output.status = status
            output.process_pid = pid
        elif name == 'clear':
            with maapi.single_write_trans(
                    'admin', 'python', db=OPERATIONAL) as write_trans:
                write_trans.delete(f'{kp[1:]}/state-events')
                write_trans.apply()
