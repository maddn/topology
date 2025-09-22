#! /usr/bin/env python
import multiprocessing
from telnetlib import Telnet
import traceback
from datetime import datetime
import setproctitle

spawn_context = multiprocessing.get_context('spawn')

class Console(spawn_context.Process):
    #pylint:disable=too-few-public-methods
    def __init__(self, name, host, port):
        super().__init__(name=name)
        self._host = host
        self._port = port
        self._file = f'/tmp/{name}-console-output.log'
        self.queue = spawn_context.Queue()
        self.stop_event = spawn_context.Event()

    def run(self):
        try:
            setproctitle.setproctitle(f'python3 {self.name} console-logger')
            while not self.stop_event.is_set():
                try:
                    with Telnet(self._host, self._port) as telnet:
                        while not self.stop_event.is_set():
                            line = telnet.read_until(b'\n', timeout=10)
                            if line:
                                with open(self._file, 'a+b') as log_file:
                                    log_file.write(line)
                                self._send_message(
                                        line.decode('utf-8').strip('\r\n '))
                except (EOFError, ConnectionRefusedError,
                        ConnectionResetError) as err:
                    with open(self._file, 'a', encoding='utf-8') as log_file:
                        log_file.write(f'{str(err)}\r\n')
                        log_file.write(traceback.format_exc())
                self.stop_event.wait(timeout=10)

        except Exception as err:
            with open(self._file, 'a', encoding='utf-8') as log_file:
                log_file.write(f'{str(err)}\r\n')
                log_file.write(traceback.format_exc())
            raise
        finally:
            self.queue.put('stop')

    def _send_message(self, message):
        self.queue.put(
                [datetime.utcnow().isoformat(sep=' ', timespec='seconds'), message])

if __name__ == '__main__':
    cl = Console('node-3', '198.18.134.110', '16003')
    cl.start()
    cl.join()
