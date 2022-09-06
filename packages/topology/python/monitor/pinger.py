#! /usr/bin/env python
import multiprocessing
import re
import time
import traceback
from datetime import datetime
from sys import platform
from subprocess import Popen, PIPE
import setproctitle

spawn_context = multiprocessing.get_context('spawn')

class Pinger(spawn_context.Process):
    #pylint:disable=too-few-public-methods
    def __init__(self, name, nodes, max_issues=3, loop_time=10):
        super().__init__(name=name)
        self._nodes = nodes
        self._max_issues = max_issues
        self._loop_time = loop_time
        self._issues = {}
        self.queue = spawn_context.Queue()
        self.stop_event = spawn_context.Event()

    def _process_result(self, result, node):
        if result != 0:
            if node in self._issues:
                if len(self._issues[node]) == self._max_issues - 1:
                    self._issues[node].append(result)
                    self._send_message(node, 'offline', self._issues[node])
                elif len(self._issues[node]) <= self._max_issues - 1:
                    self._issues[node].append(result)
            else:
                self._issues[node] = [result]
        elif node in self._issues:
            if len(self._issues[node]) >= self._max_issues:
                self._issues.pop(node)
                self._send_message(node, 'online')
            else:
                self._send_message(node, 'warn', self._issues.pop(node))

    def run(self):
        try:
            setproctitle.setproctitle(f'python3 {self.name} pinger')
            while not self.stop_event.is_set():
                start_time = time.time()
                for node in self._nodes:
                    self._process_result(ping(self._nodes[node], wait=2), node)
                    if self.stop_event.is_set():
                        break
                delta = time.time() - start_time
                self.stop_event.wait(max(0, self._loop_time - delta))
        except Exception as err:
            with open(f'/tmp/python-{self.name}-pinger-error.log',
                    'w', encoding='utf-8') as log_file:
                log_file.write(err)
                log_file.write(traceback.format_exc())
            raise
        finally:
            self.queue.put('stop')

    def _send_message(self, node, event, data=None):
        self.queue.put(
                [datetime.utcnow().isoformat(sep=' ', timespec='seconds'),
                 node, event, data])

def ping(node, num=3, wait=1):
    if platform == 'darwin':
        command = "gping -c %s -W %s %s"
    else:
        command = "ping -c %s -W %s %s"

    with Popen(command % (num, wait, node),
            shell=True, universal_newlines=True, stdout=PIPE) as proc:
        match = re.search(r'^(\d*) packets transmitted, (\d*)',
                proc.stdout.read(), re.MULTILINE)
    if match:
        return int(match.group(1)) - int(match.group(2))
    return 0
