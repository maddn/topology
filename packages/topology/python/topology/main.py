# -*- mode: python; python-indent: 4 -*-
from ncs.application import Application
from virt.libvirt_get_objects import LibvirtGetObjects
from virt.libvirt_action import LibvirtAction
from virt.topology_status import CheckTopologyStatus


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(Application):
    def setup(self):
        self.log.info('Main RUNNING')
        self.register_action('libvirt-get-objects', LibvirtGetObjects)
        self.register_action('libvirt-action', LibvirtAction)
        self.register_action('check-topology-status', CheckTopologyStatus)

    def teardown(self):
        self.log.info('Main FINISHED')
