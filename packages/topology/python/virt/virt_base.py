#!/usr/bin/python3
from abc import ABC, abstractmethod
from virt.template import Templates


class VirtBase(ABC):
    def __init__(self, hypervisor_mgr, resource_mgr, network_mgr, dev_defs, log):
        self._hypervisor_mgr = hypervisor_mgr
        self._resource_mgr = resource_mgr
        self._network_mgr = network_mgr
        self._dev_defs = dev_defs
        self._log = log

        self._templates = Templates()
        self._output = None
        self._load_templates()

    def _load_templates(self):
        pass

    @staticmethod
    def _action_allowed(active, action):
        return (active and action in ['shutdown', 'destroy'] or
                (not active) and action in ['create', 'undefine'])

    @abstractmethod
    def _action(self, action, *args):
        pass

    def __call__(self, action, output, *args):
        self._output = output
        if hasattr(self, action):
            action_method = getattr(self, action)
            action_method(*args)
        else:
            self._action(action, *args)
