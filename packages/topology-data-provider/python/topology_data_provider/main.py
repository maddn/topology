# -*- mode: python; python-indent: 4 -*-
import traceback
from ncs.application import Application
from ncs import maapi, dp, Value
_ncs = __import__('_ncs')


class MaapiTransactions():
    def __init__(self, log):
        self.log = log
        self.transactions = {}

    def get(self, tctx):
        if tctx.th not in self.transactions:
            self.log.debug(f'Creating Maapi socket and attaching to '
                           f'transaction {tctx.th}')
            self.transactions[tctx.th] = maapi.Maapi().attach(tctx)
        return self.transactions[tctx.th]

    def release(self, tctx):
        self.log.debug(
                f'Detaching from transaction {tctx.th} and closing socket')
        trans = self.transactions[tctx.th]
        trans.maapi.detach(tctx)
        trans.maapi.close()
        del self.transactions[tctx.th]


class TransactionCallback(dp.TransactionCallback):
    def __init__(self, transactions, *args, **kwargs):
        self.transactions = transactions
        super().__init__(*args, **kwargs)

    def cb_finish(self, tctx):
        self.transactions.release(tctx)
        super().cb_finish(tctx)


class DeviceNameHandler(): # pylint: disable=too-few-public-methods
    def __init__(self, transactions, log):
        self.transactions = transactions
        self.log = log

    def cb_get_elem(self, tctx, kp):
        try:
            device_prefix = self.transactions.get(tctx).safe_get_elem(
                    f'{_ncs.pp_kpath(kp[1:])}/prefix')
            device_name = f'{device_prefix}-{kp[1][0]}'
            _ncs.dp.data_reply_value(tctx, Value(device_name))
        except Exception as err:
            self.log.error(err)
            self.log.error(traceback.format_exc())
            raise


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(Application):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.transactions = MaapiTransactions(self.log)

    def get_transaction_callback(self, *args, **kwargs):
        return TransactionCallback(self.transactions, *args, **kwargs)

    def setup(self):
        self.log.info('Main RUNNING')
        self.register_trans_cb(self.get_transaction_callback)
        self.register_fun(self.start, lambda fun_data: None)

    def start(self, state):
        _ncs.dp.register_data_cb(state.ctx, 'device-name-callpoint',
                DeviceNameHandler(self.transactions, self.log))

    def teardown(self):
        self.log.info('Main FINISHED')
