# -*- mode: python; python-indent: 4 -*-
import traceback
from ncs import maapi, dp, Value
_ncs = __import__('_ncs')

class DeviceNameHandler(): # pylint: disable=too-few-public-methods
    def __init__(self, log):
        self.log = log
        self.maapi = maapi.Maapi()

    def cb_get_elem(self, tctx, kp):
        try:
            trans = self.maapi.attach(tctx)
            device_prefix = trans.safe_get_elem(f'{_ncs.pp_kpath(kp[1:])}/prefix')
            device_name = f'{device_prefix}-{kp[1][0]}'
            _ncs.dp.data_reply_value(tctx, Value(device_name))
        except Exception as err:
            self.log.error(err)
            self.log.error(traceback.format_exc())
            raise
        finally:
            self.maapi.detach(tctx)

class StateManager(dp.StateManager):
    def __init__(self, app):
        super().__init__(app.log)
        self.app = app
        self.cp_name = 'device-name-callpoint'

    def setup(self, state, previous_state):
        _ncs.dp.register_data_cb(state.ctx, self.cp_name,
                DeviceNameHandler(self.app.log))

        if previous_state is None:
            self.app.add_running_thread(self.cp_name + ' (data callback)')

    def teardown(self, _, finished):
        if finished:
            self.app.del_running_thread(self.cp_name + ' (data callback)')

class Daemon(dp.Daemon):
    def __init__(self, app):
        super().__init__('device-name-callback-daemon', log=app.log,
                state_mgr=StateManager(app))
