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
 help: List all networks
end

begin param
 name: links
 type: void
 presence: optional
 flag: --links
 help: List link networks only
end

begin param
 name: volumes
 type: void
 presence: optional
 flag: --volumes
 help: List volumes
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

  --hypervisor name     The hypervisor to connect to. If omitted the first hypervisor in the list is used
  --domains             List domains
  --networks            List all networks
  --links               List link network only
  --volumes             List volumes
""".format(sys.argv[0]))
    sys.exit(1)

def run_action(action, hypervisor):
    action_input = action.get_input()
    action_input.hypervisor = hypervisor
    return action(action_input)

def print_domains(hypervisor):
    domains = hypervisor.get.domains()
    print('\nDevices:')
    name_length = max(len(domain.name) for domain in domains.domain)

    for domain in domains.domain:
        print('    {:{}}  vCPUs {:3}  Memory {:10}  {}'.format(
                f'{domain.name}:', name_length + 1,
                '[{}]'.format(domain.vcpus or ''),
                '[{}]'.format(f'{domain.memory} MB' if domain.memory else ''),
                '[ACTIVE]' if domain.active else '[INACTIVE]'))

def is_link(network):
    if len(network.interface) == 2 and \
            network.name not in ['default', 'internal']:
        iface_iter = iter(network.interface)
        if next(iface_iter).domain_name != next(iface_iter).domain_name:
            return True
    return False

def is_not_link(network):
    return not(is_link(network) or is_unused(network))

def is_unused(network):
    return len(network.interface) == 0

def print_link_networks(networks):
    print('\nLink Networks:')
    for network in networks.network:
        if is_link(network):
            iface_iter = iter(network.interface)
            a_end = next(iface_iter)
            z_end = next(iface_iter)
            print ('    {} {} {} <--> {} {}'.format(
                f'{network.name} [{network.bridge_name}]:',
                a_end.domain_name, a_end.host_interface,
                z_end.domain_name, z_end.host_interface))

def print_other_networks(title, list_entries, include_fn=None):
    print(f'\n{title}:')
    for entry in list_entries:
        if not include_fn or include_fn(entry):
            print('    {}{}{}'.format(entry.name,
                f' [{entry.bridge_name}]' \
                        if hasattr(entry, 'bridge_name') else '',
                ':' if len(entry.interface) > 0 else ''))
            for iface in entry.interface:
                print('       {} {}'.format(iface.domain_name,
                        iface.host_interface))

def print_networks(hypervisor):
    networks = hypervisor.get.networks()
    print_link_networks(networks)
    print_other_networks('Other Networks', networks.network, is_not_link)
    print_other_networks('External Bridges', networks.external_bridge)
    print_other_networks('Unused Networks', networks.network, is_unused)

def print_links(hypervisor):
    networks = hypervisor.get.networks()
    print_link_networks(networks)

def print_volumes(hypervisor):
    volumes = hypervisor.get.volumes()
    print('\nStorage Pools:')
    for storage_pool in volumes.storage_pool:
        print(f'    {storage_pool.name}:')
        name_length = max(len(volume.name) for volume in storage_pool.volume)
        for volume in storage_pool.volume:
            print ('        {:{}}  Capacity {:10}  Allocation {}'.format(
                    volume.name, name_length + 1,
                    f'[{volume.capacity} MB]',
                    f'[{volume.allocation} MB]'))

def print_libvirt(hypervisor_name, domains, networks, links, volumes):
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

        if not hypervisor_name:
            hypervisor_name = next(iter(libvirt.hypervisor)).name

        if hypervisor_name not in libvirt.hypervisor:
            print(f"Hypervisor {hypervisor_name} does not exist")
            sys.exit(1)

        hypervisor = libvirt.hypervisor[hypervisor_name]

        print_all = not(domains or networks or links or volumes)
        if domains or print_all:
            print_domains(hypervisor)
        if networks or print_all:
            print_networks(hypervisor)
        if links and not networks:
            print_links(hypervisor)
        if volumes or print_all:
            print_volumes(hypervisor)

    print()

def main(args):
    hypervisor = None
    domains = False
    networks = False
    links = False
    volumes = False

    if len(args) == 1:
        if args[0] == "--command":
            print_command_and_exit()

    for (idx, arg) in enumerate(args):
        if arg == '--domains':
            domains = True
        elif arg == '--networks':
            networks = True
        elif arg == '--links':
            links = True
        elif arg == '--volumes':
            volumes = True
        elif arg != '--hypervisor':
            if idx > 0 and args[idx-1] == '--hypervisor':
                hypervisor = arg
            else:
                print_usage_and_exit()

    print_libvirt(hypervisor, domains, networks, links, volumes)


if __name__ == '__main__':
    main(sys.argv[1:])
