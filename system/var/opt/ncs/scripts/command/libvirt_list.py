#!/usr/bin/env python3
#pylint: disable=consider-using-f-string
import sys
import os
import ncs


def print_command_and_exit():
    print("""
begin command
  modes: oper
  styles: j c i
  cmdpath: libvirt topology list
  help: Display the topology on the given libvirt hypervisor
  more: true
end

begin param
 name: hypervisor
 presence: optional
 flag: --hypervisor
 help: The hypervisor to connect to. If omitted the first hypervisor in the list is used
end

begin param
 name: domains
 type: void
 presence: optional
 flag: --domains
 help: List domains
end

begin param
 name: networks
 type: void
 presence: optional
 flag: --networks
 help: List networks
end

begin param
 name: volumes
 type: void
 presence: optional
 flag: --volumes
 help: List volumes
end

begin param
 name: containers
 type: void
 presence: optional
 flag: --containers
 help: List containers
end
""")
    sys.exit(0)

def print_usage_and_exit():
    print("""
    Usage: {0} [--hypervisor name] [--domains] [--networks] [--volumes]
       {0} --command
       {0} --help

  --help                Display this help and exit
  --command             Display command configuration and exit

  --hypervisor name     The hypervisor to connect to. If omitted all hypervisors will be displayed
  --domains             List domains
  --networks            List networks
  --volumes             List volumes
  --containers          List containers
""".format(sys.argv[0]))
    sys.exit(1)

def sort_by_id(entity):
    return int(entity.name.split('-')[-1])

# Example: vmx-fp-99 vtap-99-0. ID=99
def sort_by_first_id_in_name(name):
    parts = name.split('-')
    for part in parts:
        if part.isdigit():
            return int(part)
    return 0

def run_action(action, hypervisor):
    action_input = action.get_input()
    action_input.hypervisor = hypervisor
    return action(action_input)

def print_containers(hypervisor):
    containers = hypervisor.get.containers()
    print('\nContainers:')
    name_length = max(len(container.name) for container in containers.container
            ) if containers.container else 0

    for container in sorted(containers.container, key=sort_by_id):
        print('    {:{}}  Status {}'.format(
                f'{container.name}:', name_length + 1,
                f'[{container.status}]'))

def print_domains(hypervisor):
    domains = hypervisor.get.domains()
    print('\nDevices:')
    name_length = max(len(domain.name) for domain in domains.domain
            ) if domains.domain else 0

    # Domain name format is prefix-id, sort by the ID part
    for domain in sorted(domains.domain, key=sort_by_id):
        print('    {:{}}  vCPUs {:3}  Memory {:10}  {}'.format(
                f'{domain.name}:', name_length + 1,
                '[{}]'.format(domain.vcpus or ''),
                '[{}]'.format(f'{domain.memory} MB' if domain.memory else ''),
                '[ACTIVE]' if domain.active else '[INACTIVE]'))

def is_unused(network):
    return len(network.interface) == 0

def is_null(network):
    return network.name.endswith('-null') and not is_unused(network)

def is_used(network):
    return not is_null(network) and not is_unused(network)

def print_veth_link_pairs(veth_pairs):
    print('\nContainer-to-Container Links (vEth Pair):')
    for veth_pair in veth_pairs:
        iface_iter = iter(veth_pair.interface)
        a_end = next(iface_iter)
        z_end = next(iface_iter)
        if z_end.container != '<host>':
            print ('    {} {} <--> {} {}'.format(
                a_end.container, a_end.name,
                z_end.container, z_end.name))

def match_tap_to_vm_interface(tap_mac, vm_mac):
    """
    Match TAP interface to VM interface by MAC address.

    Libvirt/KVM transforms MAC addresses:
    - VM interface:  02:c1:5c:00:10:00 (configured MAC)
    - TAP interface: fe:c1:5c:00:10:00 (first octet changed to 0xFE)

    Both MAC addresses are always present (assigned during VM creation).
    We compare by skipping the first 3 characters (first octet + colon).

    Examples:
        "02:c1:5c:00:10:00"[3:] == "fe:c1:5c:00:10:00"[3:]
        → "c1:5c:00:10:00" == "c1:5c:00:10:00" ✓
    """
    return tap_mac[3:] == vm_mac[3:]

def print_tap_interfaces_in_containers(networks, tap_ifaces):
    print('\nVM-to-Container Links (VM Tap in Container Namespace):')

    for tap_iface in tap_ifaces:
        for network in networks:
            for iface in network.interface:
                if match_tap_to_vm_interface(
                        tap_iface.mac_address, iface.mac_address):
                    print ('    {} {} <--> {} {}'.format(
                        tap_iface.container, tap_iface.name,
                        iface.domain_name, iface.host_interface))
                    break

def format_veth_pair_entries(veth_pairs):
    bridges = {}
    for veth_pair in veth_pairs:
        iface_iter = iter(veth_pair.interface)
        a_end = next(iface_iter)
        z_end = next(iface_iter)

        # First interface is always container (see _classify_interfaces)
        # Second interface can be <host> or another container
        if z_end.container == '<host>':
            # This is a container-to-host bridge connection
            if z_end.bridge not in bridges:
                bridges[z_end.bridge] = []
            bridges[z_end.bridge].append(
                '{} {} [{}]'.format(
                    a_end.container, a_end.name, z_end.name))
    return bridges

def format_iface_entries(networks):
    return { network.name: [
                '{} {}'.format(iface.domain_name, iface.host_interface)
                for iface in network.interface ]
             for network in networks }

def merge_entries(iface_list_1, iface_list_2):
    """Merge two dictionaries of interface lists, combining lists for duplicate keys"""
    merged = {}
    for bridge, ifaces in list(iface_list_1.items()) + list(iface_list_2.items()):
        merged.setdefault(bridge, []).extend(ifaces)
    return merged

def print_bridge_networks(iface_entries, veth_pair_entries):
    print('\nExisting Bridge Networks:')
    bridges = merge_entries(iface_entries, veth_pair_entries)

    for bridge, ifaces in sorted(bridges.items(), key=lambda item: item[0]):
        print (f'    {bridge}:')
        for iface in sorted(ifaces, key=sort_by_first_id_in_name):
            print ('        {}'.format(iface))

def print_libvirt_networks(title, networks, veth_pair_entries, include_fn=None):
    print(f'\n{title}:')
    iface_entries = format_iface_entries(networks)
    for network_name in sorted(iface_entries):

        # Find the network object by name
        network = next((n for n in networks if n.name == network_name), None)
        if not network:
            continue

        # veth pairs will only appear in existing bridges (not libvirt-created bridges)
        if network.bridge_name in veth_pair_entries:
            continue

        if include_fn and not include_fn(network):
            continue

        ifaces = iface_entries[network.name]
        print('    {} [{}]{}'.format(
            network.name, network.bridge_name, ':' if len(ifaces) > 0 else ''))
        for iface in sorted(ifaces, key=sort_by_first_id_in_name):
            print('       {}'.format(iface))

def print_networks(hypervisor):
    libvirt_networks = hypervisor.get.networks()
    networks = libvirt_networks.network
    bridges = libvirt_networks.external_bridge

    container_networks = hypervisor.get.container_networks()
    veth_pairs = container_networks.veth_pair
    tap_interfaces = container_networks.tap_interface

    veth_pair_entries = format_veth_pair_entries(veth_pairs)
    bridge_iface_entries = format_iface_entries(bridges)

    print_veth_link_pairs(veth_pairs)
    print_tap_interfaces_in_containers(networks, tap_interfaces)
    print_bridge_networks(bridge_iface_entries, veth_pair_entries)

    print_libvirt_networks(
            'Libvirt Networks', networks, veth_pair_entries, is_used)
    print_libvirt_networks(
            'Null Libvirt Networks', networks, veth_pair_entries, is_null)
    print_libvirt_networks(
            'Unused Libvirt Networks', networks, veth_pair_entries, is_unused)

def print_volumes(hypervisor):
    volumes = hypervisor.get.volumes()
    print('\nStorage Pools:')
    for storage_pool in volumes.storage_pool:
        print(f'    {storage_pool.name}:')
        name_length = max(len(volume.name) for volume in storage_pool.volume
                ) if storage_pool.volume else 0
        for volume in storage_pool.volume:
            print ('        {:{}}  Capacity {:10}  Allocation {}'.format(
                    volume.name, name_length + 1,
                    f'[{volume.capacity} MB]',
                    f'[{volume.allocation} MB]'))

def print_libvirt(hypervisor_name, domains, networks, volumes, containers):
    maapi = ncs.maapi.Maapi()
    ncs_maapi_usid = os.environ.get('NCS_MAAPI_USID')

    if ncs_maapi_usid:
        maapi.set_user_session(int(ncs_maapi_usid))
    else:
        maapi.start_user_session('admin', 'python')

    with maapi.start_read_trans() as trans:
        root = ncs.maagic.get_root(trans)
        libvirt = root.topologies.libvirt

        if not libvirt.hypervisor:
            print("No hypervisors configured")
            sys.exit(1)

        if hypervisor_name and hypervisor_name not in libvirt.hypervisor:
            print(f"Hypervisor {hypervisor_name} does not exist")
            sys.exit(1)

        for hypervisor in libvirt.hypervisor:
            if not hypervisor_name or hypervisor_name == hypervisor.name:

                print(f'\n\n*** Hypervisor: {hypervisor.name} ***')
                print_all = not(domains or networks or volumes or containers)
                if domains or print_all:
                    print_domains(hypervisor)
                if containers or print_all:
                    print_containers(hypervisor)
                if networks or print_all:
                    print_networks(hypervisor)
                if volumes or print_all:
                    print_volumes(hypervisor)

    print()

def main(args):
    hypervisor = None
    domains = False
    networks = False
    volumes = False
    containers = False

    if len(args) == 1:
        if args[0] == "--command":
            print_command_and_exit()

    for (idx, arg) in enumerate(args):
        if arg == '--domains':
            domains = True
        elif arg == '--networks':
            networks = True
        elif arg == '--volumes':
            volumes = True
        elif arg == '--containers':
            containers = True
        elif arg != '--hypervisor':
            if idx > 0 and args[idx-1] == '--hypervisor':
                hypervisor = arg
            else:
                print_usage_and_exit()

    print_libvirt(hypervisor, domains, networks, volumes, containers)


if __name__ == '__main__':
    main(sys.argv[1:])
