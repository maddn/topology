#!/usr/bin/python3
import threading
import traceback
from ncs import maapi, maagic, OPERATIONAL
from ncs.dp import Action
from monitor.console import Console
_ncs = __import__('_ncs')


def logger_name(topology_name, device_name):
    return f'{topology_name}-{device_name}'

class ConsoleProcessManager(threading.Thread):
    def __init__(self, topology_name, device_name, log):
        super().__init__()
        self._log = log
        self._console = None
        self._name = logger_name(topology_name, device_name)
        with maapi.single_read_trans(
                'admin', 'python', db=OPERATIONAL) as trans:
            topologies = maagic.get_root(trans).topologies
            device = next((device
                for device in topologies.topology[topology_name].devices.device
                if device.device_name == device_name))
            self._host = topologies.libvirt.hypervisor[device.hypervisor].host
            self._port = f'160{device.id:02d}'
            self._path = f'{device._path}/console'

    def _update_device_console_activity(self, timestamp, line):
        with maapi.single_write_trans(
                'admin', 'python', db=OPERATIONAL) as trans:
            trans.set_elem(timestamp, f'{self._path}/last-activity')
            if line != '':
                trans.set_elem(line, f'{self._path}/last-message')
            trans.apply()

    def stop(self):
        self._console.stop_event.set()

    def get_status(self):
        return ('running' if self._console.is_alive() else 'not-running',
                self._console.pid)

    def run(self):
        self._console = Console(self._name, self._host, self._port)
        self._console.start()

        try:
            while True:
                message = self._console.queue.get()
                if message == 'stop':
                    break
                [timestamp, line] = message
                self._update_device_console_activity(timestamp, line)
        except:
            self.stop()
            self._log.error(traceback.format_exc())
            raise
        finally:
            if not self._console.queue.empty():
                message = self._console.queue.get_nowait()
                self._log.info('Queue not empty: ', message)
            self._console.join()


class ConsoleActivityMonitor(Action):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._console_mgmt_threads = {}


    def start_console(self, topology_name, device_name):
        name = logger_name(topology_name, device_name)
        if name in self._console_mgmt_threads:
            (status, _) = self.console_status(name)
            if status == 'not-running':
                self.stop_console(name)

        if name not in self._console_mgmt_threads:
            self.log.info(f'Starting {name} console process')
            self._console_mgmt_threads[name] = ConsoleProcessManager(
                    topology_name, device_name, self.log)
            self._console_mgmt_threads[name].start()

    def _stop_console(self, name):
        if name in self._console_mgmt_threads:
            (status, _) = self.console_status(name)
            if status == 'running':
                self.log.info(f'Stopping {name} console process')
                console_mgmt_thread = self._console_mgmt_threads[name]
                console_mgmt_thread.stop()

    def _join_console(self, name):
        if name in self._console_mgmt_threads:
            (status, _) = self.console_status(name)
            if status == 'running':
                self.log.info(f'Joining {name} console process')
                console_mgmt_thread = self._console_mgmt_threads[name]
                console_mgmt_thread.join()
            del self._console_mgmt_threads[name]

    def stop_console(self, name):
        self._stop_console(name)
        self._join_console(name)

    def console_status(self, name):
        if name in self._console_mgmt_threads:
            return self._console_mgmt_threads[name].get_status()
        return ('not-running', None)

    def stop(self):
        self.log.info('Stopping all consoles')
        loggers = list(self._console_mgmt_threads)
        self.log.info(loggers)
        for name in loggers:
            self._stop_console(name)
        for name in loggers:
            self._join_console(name)
        super().stop()

    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)
        topology_name = str(kp[4][0])
        device_name = trans.get_elem(f'{kp[1:]}/device-name')
        if name == 'start':
            self.start_console(topology_name, device_name)
        elif name == 'stop':
            self.stop_console(logger_name(topology_name, device_name))
        elif name == 'status':
            (status, pid) = self.console_status(
                    logger_name(topology_name, device_name))
            output.status = status
            output.process_pid = pid
