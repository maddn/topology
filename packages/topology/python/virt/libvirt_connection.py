# -*- mode: python; python-indent: 4 -*-
from collections import defaultdict
from xml.etree.ElementTree import fromstring
import libvirt
_ncs = __import__('_ncs')


class LibvirtConnection():
    def __init__(self, hypervisor):
        self.conn = None
        self.bridges = defaultdict(lambda: defaultdict(dict, interfaces=[]))
        self.networks = {}
        self.domains = {}
        self.volumes = {} # by pool

        self._username = hypervisor.username
        username_str = f'{self._username}@' if self._username else ''

        parameters_str = ''
        if hypervisor.transport == 'libssh':
            parameters_str = '?known_hosts_verify=ignore'
        if hypervisor.transport == 'ssh':
            parameters_str = '?no_verify=1'

        self._url = (f'qemu+{hypervisor.transport}://'
                     f'{username_str}{hypervisor.host}/system{parameters_str}')
        self._password = _ncs.decrypt(hypervisor.password) if (
                hypervisor.password is not None) else None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn is not None:
            self.disconnect()

    def _user_interaction_callback(self, credentials, _):
        for credential in credentials:
            if credential[0] == libvirt.VIR_CRED_USERNAME:
                credential[4] = self._username
            elif credential[0] in [
                    libvirt.VIR_CRED_PASSPHRASE,
                    libvirt.VIR_CRED_NOECHOPROMPT]:
                credential[4] = self._password
            else:
                return -1
        return 0

    def connect(self):
        auth = [[libvirt.VIR_CRED_USERNAME,
                 libvirt.VIR_CRED_PASSPHRASE,
                 libvirt.VIR_CRED_NOECHOPROMPT
                ], self._user_interaction_callback, None]
        self.conn = libvirt.openAuth(self._url, auth, 0)
        if self.conn is None:
            raise Exception(f'Failed to open connection to {self._url}')

    def disconnect(self):
        self.conn.close()

    def populate_cache(self):
        self.populate_domains()
        self.populate_volumes()
        self.populate_networks()

    def populate_domains(self):
        for domain in self.conn.listAllDomains():
            active = domain.isActive()
            self.domains[domain.name()] = {
                    'vcpus': domain.maxVcpus() if active else None,
                    'memory': round(domain.maxMemory()/1024) if active else None,
                    'active': active}

    def populate_volumes(self):
        for pool in self.conn.listAllStoragePools():
            pool_volumes = self.volumes[pool.name()] = {}
            for volume in pool.listAllVolumes():
                info = volume.info()
                pool_volumes[volume.name()] = {
                        'capacity': round(info[1]/1024/1024),
                        'allocation': round(info[2]/1024/1024)}

    def populate_networks(self, include_ifaces = False):
        self.networks = {
                network.name(): {
                    'bridge-name': network.bridgeName(),
                    'interfaces': []
                } for network in self.conn.listAllNetworks()}

        if not include_ifaces:
            return

        for domain in self.conn.listAllDomains():
            xml = fromstring(domain.XMLDesc(0))
            ifaces = xml.find('devices').findall('interface')
            for iface in ifaces:
                iface_type = iface.get('type')
                source = iface.find('source')
                if source is not None and iface_type in ['network', 'bridge']:
                    target = iface.find('target')
                    dev = target.get('dev') if target is not None else 'none'
                    source_dict = getattr(self, f'{iface_type}s')
                    name = source.get(iface_type)
                    if name not in source_dict and iface_type == 'network':
                        name = f'***missing*** {name}'
                        if name not in source_dict:
                            source_dict[name] = {'interfaces': []}
                    source_dict[name]['interfaces'].append({
                        'domain-name': domain.name(),
                        'host-interface': dev})
