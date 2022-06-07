# -*- mode: python; python-indent: 4 -*-
from collections import defaultdict
from xml.etree.ElementTree import fromstring
import libvirt


class LibvirtConnection():
    def __init__(self):
        self.conn = None
        self.bridges = defaultdict(lambda: defaultdict(dict, interfaces=[]))
        self.networks = {}
        self.domains = {}
        self.volumes = {} # by pool

    def connect(self, url):
        self.conn = libvirt.open(url)
        if self.conn is None:
            raise Exception(f'Failed to open connection to {url}')

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
                    source_dict[source.get(iface_type)]['interfaces'].append({
                        'domain-name': domain.name(),
                        'host-interface': dev})
