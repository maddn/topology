import os
import pprint
import re
import subprocess
import threading

from time import sleep
from pyvxr.vxr import Vxr
from pyvxr.errors import PyvxrError

from monitor.console_activity import start_console_logger, stop_console_logger


class VxrSimStarter(threading.Thread):
    def __init__(self, sim_name, output_dir, config, device_path):
        super().__init__()
        self._config = config
        self._output_dir = output_dir
        self._device_path = device_path
        self.name = f'VxrSimStarter-{sim_name}-Thread'

    def run(self):
        vxr_sim=Vxr(self._output_dir)
        vxr_sim.start(self._config)
        start_console_logger(self._device_path)


class ConnectionVxr():
    def __init__(self, hypervisor, log):
        self.name = hypervisor.name
        self._host = hypervisor.host
        self._username = hypervisor.username
        self._log = log

    def output_dir(self, sim_name):
        return f'vxr/{sim_name}'

    def sim_dir(self, sim_name):
        return  f'/nobackup/{sim_name}/pyvxr'

    def get_simulation_config(self, sim_name):
        return {
            'simulation': {
                'sim_host': self._host,
                'sim_host_username': self._username,
                'sim_rel': '/opt/cisco/vxr2/latest',
                'no_image_copy': True,
                'sim_dir': self.sim_dir(sim_name)
            }
        }

    def get_vxr_config(self, sim_name, device_config, connections=None):
        return {
            **self.get_simulation_config(sim_name),
            'devices': {
                sim_name: { **(device_config or {}) }
            },
            'connections': {
                'custom': { **(connections or {}) }
            }
        }

    def get_host(self):
        return self._host

    def get_username(self):
        return self._username

    def start(self, sim_name, vxr_config, device_path):
        self._log.info(
                f'VXR Config:\n{pprint.pformat(vxr_config)}')
        vxr_sim=VxrSimStarter(
                sim_name, self.output_dir(sim_name), vxr_config, device_path)
        vxr_sim.start()

    def stop(self, sim_name, device_path):
        vxr_sim=Vxr(self.output_dir(sim_name))
        self._log.info(f'[{self.name}] Stopping sim {sim_name}')
        try:
            vxr_sim.stop()
            vxr_sim.clean()
        except PyvxrError as err:
            self._log.info(err)
        stop_console_logger(device_path)

    def get_interfaces(self, sim_name):
        tap_file = f'{self.sim_dir(sim_name)}/{sim_name}/line_taps.0.txt'

        taps = None
        interfaces = []
        while taps is None:
            try:
                taps = subprocess.run(["ssh", self._host, f'cat {tap_file}'],
                        check=True, capture_output=True, text=True).stdout
            except subprocess.CalledProcessError:
                self._log.info(f'[{self.name}] Taps not ready. Sleeping 10.')
                sleep(10)

        for line in taps.split('\n'):
            match = re.search(r'^(\S+)\s+\S+0\/0\/0\/(\d+)\s+.*', line)
            if match:
                interfaces.append((match.group(2), match.group(1)))

        return interfaces

    def is_active(self, sim_name):
        output_dir = self.output_dir(sim_name)
        if os.path.isdir(output_dir):
            vxr_sim=Vxr(output_dir)
            try:
                self._log.info('Getting status')
                status = vxr_sim.status()
                self._log.info(status)
                if status:
                    if self._host in status:
                        if status[self._host] == 'running':
                            return True
            except PyvxrError as err:
                self._log.info(err)
                return False
        return False
