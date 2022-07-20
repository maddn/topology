# 🌐 NSO Topology Manager

> Use [Cisco NSO](https://developer.cisco.com/docs/nso/#!getting-and-installing-nso/getting-nso)
> to manage existing network topologies and automatically create new ones with
> [libvirt/KVM](https://libvirt.org/)!


## Overview

This project provides a simple [topology YANG
model](packages/topology/src/yang/topology-base.yang) in NSO and a
corresponding set of NSO services that can be used to configure the topology
devices with basic network configuration.

In addition the topology model is
[extended](packages/topology/src/yang/topology-libvirt.yang) with NSO actions
to optionally define and create the topology in KVM using libvirt.


## Getting Started

The easiest way to get started is to clone this repository, then build and run
a Docker image using the Make targets. See [docker](#docker) for full
details.


### Dependencies

- NSO 5.6
- IOS-XR CLI NED
- IOS CLI NED

The following dependencies are required on the NSO system, these are included
automatically when using Docker.

**Linux packages**
- Libvirt API (libvirt-dev)
- fdisk
- mkfs.fat (dosfstools)

**Python PIP**
- libvirt-python
- passlib
- pycdlib
- pyfatfs


### Docker

A complete Docker image for this project can be built using the `docker‑build`
Make target, and started using the `docker‑start` target. The Dockerfile will
create a Linux container with NSO installed, and all the dependencies required
to run this project.

The [system](system) folder is copied to the filesystem root during the build.
Any additional files required in the Docker container (for example, NEDs and
SSH keys) can be copied to the appropriate directory in this folder before
running the build.

To build and run the Docker container, follow these steps:

1. Clone this git repository.

   ```shell
   git clone https://github.com/maddn/topology.git
   ```

2. Copy the NSO installer binary to the `nso‑install‑file` directory.
   ```shell
   cp nso-5.6.3.1.linux.x86_64.installer.bin topology/nso-install-file
   ```

3. Copy the IOS-XR and IOS CLI NEDs to the `system/opt/ncs/packages`
   directory.
   ```shell
   cp ncs-5.6.3-cisco-ios-6.77.12.tar.gz topology/system/opt/ncs/packages
   cp ncs-5.6.3-cisco-iosxr-7.38.5.tar.gz topology/system/opt/ncs/packages
   ```

4. **Optional.** To enable passwordless SSH login from the Docker container to
   the KVM host, copy the SSH public and private keys for the KVM host to the
   `system/root/.ssh` directory. This directory first has to be created.

   ```shell
   mkdir -p topology/system/root/.ssh
   cp id_ed25519 topology/system/root/.ssh
   cp id_ed25519.pub topology/system/root/.ssh
   ```

5. Run the `docker‑build` make target.
   ```shell
   cd topology
   make docker-build
   ```

6. Run the `docker‑start` make target.
   ```shell
   make docker-start
   ```

After the container has started, the NSO Web UI can be accessed on standard
HTTP port 80, and the CLI on the standard SSH port 22. A bash shell can be
started using the `docker‑shell` Make target.


### Existing NSO Instance

The project can be installed into an existing NSO instance by copying the
packages to the NSO instance packages directory. 

When using an existing NSO instance, the [dependencies](#dependencies) must be
installed on the NSO machine.

To install this project on an existing NSO instance, follow these steps:

1. Copy the IOS-XR and IOS CLI NEDs to the NSO instance `packages` directory.
   ```shell
   cp ncs-5.6.3-cisco-ios-6.77.12.tar.gz <nso-run-dir>/packages
   cp ncs-5.6.3-cisco-iosxr-7.38.5.tar.gz <nso-run-dir>/packages
   ```

2. Clone this git repository.

   ```shell
   git clone https://github.com/maddn/topology.git
   ```

3. Copy the topology packages to the NSO instance `packages` directory.
   ```shell
   cd topology
   cp -r packages/topology-data-provider <nso-run-dir>/packages
   cp -r packages/topology <nso-run-dir>/packages
   ```

4. **Optional.** To enable the [`libvirt topology
   list`](#current-libvirt-topology) command, copy the `libvirt_list.py`
   command script to the NSO instance `scripts/command` directory.
   ```shell
   cp system/var/opt/ncs/scripts/command/libvirt_list.py <nso-run-dir>/scripts/command
   ```

5. Compile the topology YANG model:
   ```shell
   cd <nso-run-dir>/packages/topology/src
   make
   ```

6. From the NSO CLI, reload the packages and scripts.
   ```
   packages reload
   script reload
   ```

### Libvirt/KVM

To use the libvirt actions in NSO, a KVM host must be available with libvirt
installed. The following must be configured on the host:

- A management bridge.
- A storage pool.
- A base image volume for each device type (uploaded to the storage pool).

A [hypervisor](#hypervisors) must be created in NSO to connect to the KVM host.


## Topology Model

> YANG submodule |
> [topology-base.yang](packages/topology/src/yang/topology-base.yang) | Path |
> `/topologies/topology`

A topology is a list of devices, links and networks, and optionally, an
associated [hypervisor](#hypervisors).

| List     | Description |
| :------- | :---------- |
| Devices  | A device is created with a numeric `id` and a `prefix`. The `id` is used extensively by the services and libvirt actions to generate resource names such as networks, MAC addresses and IP addresses. The `device‑name` is automatically populated by combining the `prefix` and `id`. Optionally the device can refer to a [device-definition](#device-definitions) if the device is to be created using libvirt. |
| Links    | These are point-to-point links between two devices in the `device` list (`a‑end‑device` and `z‑end‑device`). When defining a topology to be created in libvirt, the interface ids are refined as operational data and will be automatically populated. |
| Networks | A network connects multiple devices to a single network using the same `interface‑id` on each device. |


## Services

These services use the topology model to configure the network devices. An
overview of each one is included below, but refer to the individual YANG models
for full details.

These services are all template-based with no code, which means they
can easily be extended to support new configuration.


### IP Connectivity

> YANG submodule |
> [ip-connectivity.yang](packages/topology/src/yang/ip-connectivity.yang) |
> Path | `/topologies/topology/ip-connectivity`

This service extends the topology model and will configure IPv4 and IPv6
addresses on the topology interfaces. The interfaces are configured as follows:

| For Each | Configure |
| :------- | :-------- |
| Device   | A loopback interface for each entry in the `loopback‑interfaces` list with an IPv4 address in the format `{ipv4‑subnet‑start}.device‑id`. An optional IPv6 address is configured in similar format. |
| Link     | An IPv4 address on each of the two interfaces (`a‑end‑interface/id` and `z‑end‑interface/id`) in the format `{physical‑interfaces/ipv4‑subnet‑start}.x.y.device‑id` where `x` is the lower device id and `y` is the higher. An optional IPv6 address is configured in similar format. |
| Network  | An IPv4 address for each entry in the `devices` list on the device `interface‑id` in the format `{physical‑interfaces/ipv4‑subnet‑start}.device‑id`. An optional IPv6 address is configured in similar format. |

The `loopback‑interfaces` list allows one interface to be selected as the
`primary` interface. This will be the default loopback interface used by the
other services if one isn't explicitly given (for example for BGP and PCE
peering).


### Base Configuration

> YANG submodule |
> [base-config.yang](packages/topology/src/yang/base-config.yang) | Path |
> `/topologies/base-config` | Dependency (key) |
> [topology](#topology-model)

This service configures each device in the topology with common standalone
device configuration that would typically be found in a golden config. This
includes login-banner, SNMP, NTP, default terminal line settings, interface
bandwidth and LLDP. In addition, the service will:

- Set the hostname to the `device‑name`.
- Create static routes between the loopback interfaces of two devices for each
  route in the `static‑routes/routes` list.
- Create static routes between the management and loopback interfaces of each
  device in the topology.
- Create PCE configuration on the router identified as the PCE.


### BGP

> YANG submodule | [bgp.yang](packages/topology/src/yang/bgp.yang) | Path |
> `/topologies/bgp` | Dependency (key) | [topology](#topology-model)

This service configures BGP neighbours based on their role. A topology device
can be added to one of the following role lists:

| Device Role       | Description |
| :---------------- | :---------- |
| `route‑reflector` | A neighbour will be configured with a VPNv4 (and optional VPNv6) address family for each `provider‑edge` router, and a link-state address family for each `link‑state` router.
| `provider‑edge`   | A VPNv4 (and optional VPNv6) neighbour will be configured to each `route‑reflector` |
| `link‑state`      | A link-state neighbour will be configured to each `route‑refector` |


### IGP

> YANG submodule | [igp.yang](packages/topology/src/yang/igp.yang) | Path |
> `/topologies/igp` | Dependency (key) | [topology](#topology-model)

This service will configure IS-IS on each topology device in the IGP `devices`
leaf-list. For each device, it will add each interface that is connected to
another device in same IGP to the IS-IS domain. It will set the metric on the
interface using the `igp‑metric` on the topology link.

For IOS devices, basic OSPF can be configured with a loopback network and
optionally the management network.

### MPLS

> YANG submodule | [mpls.yang](packages/topology/src/yang/mpls.yang) | Path |
> `/topologies/mpls` | Dependency (key) | [igp](#igp)

This service will configure MPLS on the devices in the IGP. It can configure
each device interface which is connected to another device in the IGP with:
- LDP
- RSVP
- MPLS Traffic engineering with the `affinity` set from the topology link.

For traffic engineering it will configure the PCE clients.


### Segment Routing

> YANG submodule |
> [segment-routing.yang](packages/topology/src/yang/segment-routing.yang) |
> Path | `/topologies/segment-routing` | Dependency (key) | [igp](#igp)

This service will enable segment routing on each device in the IGP, by
configuring the following on each device:

- A prefix sid on the primary loopback interface calculated as
  `{prefix‑sid‑start} + device‑id`.
- TI-LFA on each interface connected to another device in the IGP.
- The segment-routing global-block.
- For traffic engineering, the PCE client.
- flex-algo using the `affinity` from the toplogy link.
- SRv6 (when IPv6 is enabled).


## Libvirt

The topology is extended with a set of NSO actions that will define (and start)
corresponding domains, networks and volumes in libvirt. In order to do this,
some [extra information](packages/topology/src/yang/libvirt.yang)  has to be
provided in NSO - a list of [hypervisors](#hypervisors) and a list of [device
definitions](#device-definitions).

### Hypervisors

> YANG submodule |
> [libvirt.yang](packages/topology/src/yang/libvirt.yang) |
> Path | `/topologies/libvirt/hypervisor`

A `hypervisor` has the connection information for the libvirt API (local to the
NSO installation) to connect to the hypervisor (KVM). The `transport` and
`host` leaves are used to generate the libvirt connection URL.

A `username` and `password` can be specified for the hypervisor, but this is
not supported with `ssh` transport (which uses the system installed SSH
binary). To use password login over SSH, `libssh` transport can be chosen
(although this appears to be less reliable). The recommended way to connect is
using `ssh` transport with SSH keys configured on the NSO client and KVM server
for passwordless authentication. See the [libvirt
documentation](https://libvirt.org/uri.html) for more information.

The `hypervisor` also has the `management‑network` parameters. The `bridge`
must already exist on the host machine. The first interface of each device will
be attached to this bridge.

Devices are allocated their management IP address in the format
`{ip‑address‑start} + device‑id`, and the `ip‑address` attribute in the
device's [day0-file](#day-0-configuration) is substituted with this value.

The MAC addresses generated for all resources in the topology will start with
`mac‑address‑start` (the first three hexadectets).

The hypervisor also contains `get` actions to retrieve the domains, networks
and volumes currently configured on the host. See [Current Libvirt
Topology](#current-libvirt-topology)


### Device Definitions

> YANG submodule |
> [libvirt.yang](packages/topology/src/yang/libvirt.yang) |
> Path | `/topologies/libvirt/device-definition`

A `device‑definition` describes how to create the domain on libvirt. The
definition references an initial libvirt XML [template](#template) which is
used to build the final domain XML definition using the other leaves in the
`device‑definition`.


### Template

The `template` leaf in the `device‑definition` must be the name of an XML
file (without the `.xml` extension), which exists in the
[images](packages/topology/python/virt/images) directory. This file should
contain the initial libvirt XML domain definition without any disks or
interfaces (these are automatically added). Attributes in curly braces - i.e.
`{attribute‑name}` - are substituted as follows:

| Name          | Description                                     |
| :------------ | :---------------------------------------------- |
| `device‑name` | The name of the device                          |
| `vcpus`       | The number of CPUs from the `device‑definition` |
| `memory`      | The memory in MB from the `device‑definition`   |


### Base Image

A volume is created from the `base‑image` given in the `device‑definition`. The
image must already exist in the `storage‑pool` on the libvirt host. If the
image format is not `qcow2`, the `clone` option must be chosen for the
`base‑image‑type` leaf, which will create a full clone of the base
image (the default option is to use the base image as a `backing‑store`).

The volume is attached to the domain as the first disk.


### Day 0 Configuration

If the `device‑definition` has the `day0‑file` leaf populated, a day 0 volume
will be created, containing an image with the day 0 configuration.

The day 0 configuration is generated using the `day0‑file` as a template, this
file must exist in the [images](packages/topology/python/virt/images)
directory. Attributes in curly braces - i.e. `{attribute‑name}` - are
substituted as follows:

| Name              | Description                                                                          |
| :---------------- | :----------------------------------------------------------------------------------- |
| `ip‑address`      | The allocated management IP address                                                  |
| `gateway‑address` | The `gateway‑address` from the `hypervisor` configuration (useful for static routes) |
| `username`        | Username from the `device‑definition` `authgroup`                                    |
| `password`        | SHA-512 password hash (Cisco type 10 and Linux `/etc/shadow` ) from the `authgroup`  |
| `password‑md5`    | MD5 password hash with a salt size of 4 (Cisco type 5) from the `authgroup`          |

The format of the generated volume will depend on the [device
type](#device-type)

**IMPORTANT!** The day 0 template must contain configuration to ensure the
device is reachable from NSO once it has booted. This should include
credentials, management IP address and any required routes.


### Device Type

The `device‑type` leaf in the `device‑definition` identifies how to generate
the day 0 configuration for that kind of device, and if any additional logic is
required to fully configure the device. The following table describes what is
done for each supported type:

| Name     | Description |
| :------- | :---------- |
| XRv‑9000 | The day 0 configuration is written to a file called `iosxr_config.txt` inside an ISO image and attached to the domain as a `cdrom`.<br/>The second and third interfaces on the domain are assigned to two additional management networks (`ctrl` and `host`)
| IOSv     | The day 0 configuration is written to a file called `ios_config.txt` inside a RAW disk image with a single 1MB FAT12 partition and attached to the domain as the second disk.
| Linux    | The day 0 configuration uses [cloud-init](https://cloudinit.readthedocs.io/en/latest/index.html). `meta‑data` and `network‑config` files are included automatically. All interfaces are configured (including data interfaces - NSO can't manage Linux devices to configure them later). The `day0‑file` should be a valid YAML cloud-init user-data file whose first line is `#cloud-config`. These three files are written to an ISO image and attached to the domain as a `cdrom`. For more information see the [cloud-init NoCloud documentation](https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html). 

The following table contains a summary of the day 0 configuration for each
device type:

| Type     | Volume Format | Device Type | Day 0 Target File  | Additional Files             |
| :------- | :------------ | :---------- | :----------------- | :--------------------------- |
| XRv‑9000 | ISO 9660      | cdrom       | `iosxr_config.txt` |
| IOSv     | FAT12         | disk        | `ios_config.txt`   |
| Linux    | ISO 9660      | cdrom       | `user‑data`        | `meta‑data` `network‑config` |


### Managed Devices

If the `ned‑id` leaf is populated in the `device‑definition` then the device is
automatically added to NSO when it is defined.

When the topology is started, NSO will ping the device until it becomes
reachable and then run the `sync‑from` action.

The current status of each device can be seen in the `status` leaf of the
topology device.


### Topology Define Process

The define action converts the topology model from NSO into libvirt XML. At a
high level it will create a network for each link in the topology and a domain
for each device in the topology, with the interfaces attached to the
appropriate networks.

Interfaces are assigned automatically, and cannot be manually chosen. The
interface is chosen based on the destination device id, for example interface 6
will be connected to device 6.

The define action will perform the following tasks to define the topology in
libvirt:

- For each link in the topology, a network is created in libvirt, and in turn a
  bridge interface is created on the host machine. In the following table `x`
  is the lower device id in the link and `y` is the higher device id.

  | Resource        | Name                  |
  | :-------------- | :-------------------- |
  | Libvirt Network | `net‑{x}‑{y}`         |
  | Host Bridge     | `vbr‑{x}‑{y}`         |
  | MAC Address     | `02:c1:5c:00:{x}:{y}` |

- An additional isolated network is created for each device to connect any
  unused interfaces to.

  | Resource        | Name                         |
  | :-------------- | :--------------------------- |
  | Libvirt Network | `net‑{device‑id}‑null`       |
  | Host Bridge     | `vbr‑{device‑id}‑null`       |
  | MAC Address     | `02:c1:5c:00:{device‑id}:00` |

- For each device, a volume is created from the `base‑image` as described in
  the [Base Image](#base-image) section, and an optional day 0 volume is
  created from the `day0‑file` as described in the [Day 0
  Configuration](#day-0-configuration) section. These volumes are attached to
  the domain.

- For each device, an interface is created for each corresponding entry in the
  links and networks lists. The interface is attached to that network i.e. for
  a link, if the current device interface id matches the other device id, it is
  attached to the network created for that link. Where there are gaps in the
  interface ids, additional interfaces are created and attached to the device's
  null network. Each interface is created with a corresponding interface device
  on the
  host.

  | Resource    | Name                                     |
  | :---------- | :--------------------------------------- |
  | Host Device | `veth‑{device‑id}‑{interface‑id}`        |
  | MAC Address | `02:c1:5c:01:{device‑id}:{interface‑id}` |


### Current Libvirt Topology

The current libvirt topology for a hypervisor can be retrieved using the CLI
command `libvirt topology list`.

```
> libvirt topology list
Possible completions:
  domains      List domains
  hypervisor   The hypervisor to connect to. If omitted the first hypervisor in the list is used
  links        List link networks only
  networks     List all networks
  volumes      List volumes
```

This command script calls the appropriate [hypervisor](#hypervisors) `get`
actions, and will output what is currently configured on the libvirt host
regardless of any topologies configured in NSO. Networks with exactly two
interfaces are identified as link networks.


## Managed Topology

> YANG module |
> [topology.yang](packages/topology/src/yang/topology.yang) | Path |
> `/topologies/managed-topology` | Dependency (key) |
> [topology](#topology-model)</br>
> YANG nano plan |
> [managed-topology-nano-plan.yang](packages/topology/src/yang/managed-topology-nano-plan.yang) |
> Plan Path | `/topologies/managed-topology/plan`

The `managed‑topology` nano service will automatically define and start a
toplogy (if not already done) and once the topology `status` is `ready` it will
create the above services. The `managed‑topology` YANG model contains the same
nodes as the individual services.

This service automates the process to define, start and configure an entire
topology. The `plan` shows the status of each device and when each of the
services is deployed.
