from common_topology import GetDeviceConfiguration
from ncs.application import Application
from virt.libvirt_get_objects import LibvirtGetObjects
from virt.virt_topology import LibvirtAction, LibvirtNetworkAction
from virt.topology_status import CheckTopologyStatus
from monitor.operational_status import OperationalStateMonitor
from monitor.console_activity import ConsoleActivityMonitor


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
