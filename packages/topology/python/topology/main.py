import socket
import json
import yaml
import ncs
import _ncs
from ncs.application import Application
from ncs.dp import Action
from _ncs import maapi
from virt.libvirt_get_objects import LibvirtGetObjects
from virt.virt_topology import LibvirtAction, LibvirtNetworkAction
from virt.topology_status import CheckTopologyStatus
from monitor.operational_status import OperationalStateMonitor
from monitor.console_activity import ConsoleActivityMonitor

class GetDeviceConfiguration(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output):
        self.log.info('action name: ', name)

        with ncs.maapi.single_write_trans(uinfo.username, 'python') as trans:
            device = ncs.maagic.get_node(trans, kp)
            self.log.info(device.device_type)
            if (device.device_type.ne_type == 'cli' and
                    (device.device_type.cli.ned_id.startswith('cisco-iosxr') or
                     device.device_type.cli.ned_id.startswith('cisco-staros'))
                    and (input.format == 'cli' or not input.format)):
                output.format = 'cli'
                format_flags = maapi.CONFIG_C
            elif (device.device_type.ne_type == 'cli' and not input.format or
                  input.format == 'cli'):
                output.format = 'cli'
                format_flags = maapi.CONFIG_C_IOS
            elif (device.device_type.ne_type == 'netconf' and
                  device.device_type.netconf.ned_id.startswith('juniper-junos')
                  and not input.format or
                  input.format == 'curly-braces'):
                output.format = 'curly-braces'
                format_flags = maapi.CONFIG_J
            elif input.format == 'json':
                output.format = 'json'
                format_flags = maapi.CONFIG_JSON
            elif input.format == 'yaml':
                output.format = 'yaml'
                format_flags = maapi.CONFIG_JSON
            else:
                output.format = 'xml'
                format_flags = maapi.CONFIG_XML_PRETTY

            if input.service_meta_data:
                format_flags |= maapi.CONFIG_WITH_SERVICE_META

            config_id = maapi.save_config(trans.maapi.msock, trans.th,
                                          format_flags, str(kp) + '/config')

            sock = socket.socket()
            # pylint: disable=no-member
            _ncs.stream_connect(sock, config_id, 0,
                                '127.0.0.1', _ncs.NCS_PORT)
            config_bytes = b''
            while 1:
                data = sock.recv(1024)
                if not data:
                    break
                config_bytes += data

            sock.close()

        if input.format == 'yaml':
            json_config = json.loads(config_bytes)
            output.config = yaml.safe_dump(json_config,
                                           default_flow_style=False)
        else:
            output.config = config_bytes.decode('utf-8')

# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(Application):
    def setup(self):
        self.log.info('Main RUNNING')
        self.register_action('libvirt-get-objects', LibvirtGetObjects)
        self.register_action('libvirt-action', LibvirtAction)
        self.register_action('libvirt-network-action', LibvirtNetworkAction)
        self.register_action('check-topology-status', CheckTopologyStatus)
        self.register_action('operational-state-monitor', OperationalStateMonitor)
        self.register_action('console-activity-monitor', ConsoleActivityMonitor)
        self.register_action('get-device-configuration', GetDeviceConfiguration)

    def teardown(self):
        self.log.info('Main FINISHED')
