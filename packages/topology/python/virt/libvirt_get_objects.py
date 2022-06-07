# -*- mode: python; python-indent: 4 -*-
from ncs.dp import Action
from ncs import maagic
from virt.libvirt_connection import LibvirtConnection


def create_list_item(name, yang_list):
    list_item = yang_list.create()
    if name is not None:
        list_item.name = name
    return list_item

# Single level dict: convert dict keys to yang container leafs
def dict_to_yang_container(dict_object, yang_container):
    for key, value in dict_object.items():
        yang_container[key] = value

# Two level dict: convert first level dict keys to yang list keys,
#                 and second level dict to yang list entry container leafs
def dict_dict_to_yang_list(dict_dict, yang_list):
    for name, dict_object in dict_dict.items():
        dict_to_yang_container(dict_object, create_list_item(name, yang_list))

# List of dicts: convert list to yang keyless list
def list_dict_to_yang_list(list_dict, yang_list):
    for dict_object in list_dict:
        dict_to_yang_container(dict_object, create_list_item(None, yang_list))


class LibvirtGetObjects(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        self.log.info('action name: ', name)
        hypervisor = maagic.get_node(trans, kp[1:])

        libvirt_conn = LibvirtConnection()
        libvirt_conn.connect(hypervisor.url)

        if name == 'domains':
            libvirt_conn.populate_domains()
            dict_dict_to_yang_list(libvirt_conn.domains, output.domain)

        elif name == 'volumes':
            libvirt_conn.populate_volumes()
            for pool_name, volumes in libvirt_conn.volumes.items():
                pool_node = create_list_item(pool_name, output.storage_pool)
                dict_dict_to_yang_list(volumes, pool_node.volume)

        elif name == 'networks':
            def _networks_to_yang(networks, yang_list):
                for network_name, network in networks.items():
                    network_node = create_list_item(network_name, yang_list)
                    if 'bridge-name' in network:
                        network_node.bridge_name = network['bridge-name']
                    list_dict_to_yang_list(
                            network['interfaces'], network_node.interface)

            libvirt_conn.populate_networks(include_ifaces=True)
            _networks_to_yang(libvirt_conn.networks, output.network)
            _networks_to_yang(libvirt_conn.bridges, output.external_bridge)
