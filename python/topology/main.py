# -*- mode: python; python-indent: 4 -*-
from ncs.application import Application
from virt.libvirt_get_objects import LibvirtGetObjects
from virt.libvirt_action import LibvirtAction
from topology.device_name_cb import Daemon as DeviceNameCallbackDaemon


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(Application):
    def __init__(self, *args, **kwds):
        self.device_name_cb = None
        super().__init__(*args, **kwds)

    def setup(self):
        self.log.info('Main RUNNING')
        self.register_action('libvirt-get-objects', LibvirtGetObjects)
        self.register_action('libvirt-action', LibvirtAction)

        self.device_name_cb = DeviceNameCallbackDaemon(app=self)
        self.device_name_cb.start()

    def teardown(self):
        self.device_name_cb.finish()
        self.log.info('Main FINISHED')
