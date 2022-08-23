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


## Installation

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
admin@ncs# libvirt topology list
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

The `managed‑topology` nano service will automatically `define` and `start` a
toplogy (if not already done) and once the topology `status` is `ready` it will
create the above services. The `managed‑topology` YANG model contains the same
nodes as the individual services.

This service automates the process to define, start and configure an entire
topology. The `plan` shows the status of each device and when each of the
services is deployed.


## Getting Started - Example Topology

A sample [`topology`](#topology-xml) definition and
[`managed-topology`](#managed-topology-service-xml) called `simple-lab` are
included in the [examples](examples) directory.

### Topology Overview

The `simple-lab` topology contains five IOS XRv 9000 routers. Nodes 1 to 4 are
in an IS-IS IGP domain with MPLS configured. Nodes 3 and 4 are PE devices and
node 5 is the route relector.

The diagram below shows the topology connections with the interfaces and IP
addresses that NSO will allocate.
```

                                          ┌────────────┐
                                          │            │
                                          │   node-5   │
                                          │   -(RR)-   │
                                          │ 198.10.1.5 │
                                          │            │
                                          └────────────┘
                                   GigE 0/0/0/1 │ 10.1.5.5
                                                │
                                                │
················································│·················································
:                                               │                                                :
:                                  GigE 0/0/0/5 │ 10.1.5.1                                       :
:                                         ┌────────────┐                                         :
:                                         │            │                                         :
:                            GigE 0/0/0/3 │   node-1   │ GigE 0/0/0/4                            :
:               ┌─────────────────────────│   ------   │─────────────────────────┐               :
:               │                10.1.3.1 │ 198.10.1.1 │ 10.1.4.1                │               :
:               │                         │            │                         │               :
:               │                         └────────────┘                         │               :
:               │                   GigE 0/0/0/2 │ 10.1.2.1                      │               :
:               │                                │                               │               :
:               │                                │                               │               :
:  GigE 0/0/0/1 │ 10.1.3.3                       │                      10.1.4.4 │ GigE 0/0/0/1  :
:        ┌────────────┐                          │                         ┌────────────┐        :
:        │            │                          │                         │            │        :
:        │   node-3   │                          │                         │   node-4   │        :
:        │   -(PE)-   │                          │                         │   -(PE)-   │        :
:        │ 198.10.1.3 │                          │                         │ 198.10.1.4 │        :
:        │            │                          │                         │            │        :
:        └────────────┘                          │                         └────────────┘        :
:  GigE 0/0/0/2 │ 10.2.3.3                       │                      10.2.4.4 │ GigE 0/0/0/2  :
:               │                                │                               │               :
:               │                                │                               │               :
:               │                   GigE 0/0/0/1 │ 10.1.2.2                      │               :
:               │                         ┌────────────┐                         │               :
:               │                         │            │                         │               :
:               │                10.2.3.2 │   node-2   │ 10.2.4.2                │               :
:               └─────────────────────────│   ------   │─────────────────────────┘               :
:                            GigE 0/0/0/3 │ 198.10.1.2 │ GigE 0/0/0/4                            :
:                                         │            │                                         :
:                                         └────────────┘                                         :
:                                                                                                :
:                                         IGP -- IS-IS 1                                         :
:                                                                                                :
··································································································
```

### Topology XML

> XML file | [simple-lab-topology.xml](examples/simple-lab-topology.xml)

The `simple-lab-topology.xml` file contains the `topology`, `authgroup`,
`hypervisor` and `device-definition`. Update the `kvm` hypervisor with the
details for the KVM host, and update the `XRv-9000` device definition with the
`base-image`. Ensure the `day0-file` has the correct routes so that NSO can
connect to the device once it has booted.

The topology definition can be loaded into NSO using the CLI `load merge`
command.

```
admin@ncs# load merge simple-lab-topology.xml
Loading.
3.09 KiB parsed in 0.03 sec (101.48 KiB/sec)

admin@ncs# commit
Commit complete.
```

NSO will not define the topology on the hypervisor until the `define` action is
executed or a [`managed-topology`](#managed-topology-service-xml) service is
created which uses this topology.

When running NSO using the Docker build, this file can be copied to the
`/system/root` directory before building the docker image so it will be
available to load from the home directory.

Below is a snippet of the XML showing how the topology device and links are
defined.

```xml
<topology>
  <name>simple-lab</name>
  <devices>
    <device>
      <id>1</id>
      <prefix>node</prefix>
    </device>
    <device>
      <id>2</id>
      <prefix>node</prefix>
    </device>
    <device>
      <id>3</id>
      <prefix>node</prefix>
    </device>
    <device>
      <id>4</id>
      <prefix>node</prefix>
    </device>
    <device>
      <id>5</id>
      <prefix>node</prefix>
    </device>
  </devices>
  <links>
  <link>
    <a-end-device>node-1</a-end-device>
    <z-end-device>node-2</z-end-device>
  </link>
  <link>
    <a-end-device>node-3</a-end-device>
    <z-end-device>node-1</z-end-device>
    <affinity>top</affinity>
  </link>
  <link>
    <a-end-device>node-1</a-end-device>
    <z-end-device>node-4</z-end-device>
    <affinity>top</affinity>
  </link>
  <link>
    <a-end-device>node-4</a-end-device>
    <z-end-device>node-2</z-end-device>
    <affinity>bottom</affinity>
  </link>
  <link>
    <a-end-device>node-2</a-end-device>
    <z-end-device>node-3</z-end-device>
    <affinity>bottom</affinity>
  </link>
  <link>
    <a-end-device>node-1</a-end-device>
    <z-end-device>node-5</z-end-device>
  </link>
  </links>
</topology>
```

### Managed Topology Service XML

> XML file | [simple-lab-service.xml](examples/simple-lab-service.xml)

The `simple-lab-service.xml` file contains the `managed-topology` service which
defines the services to configure on the topology routers. This includes the
loopback interface, IS-IS, MPLS, BGP and a static route between node-1 and
node-5.

The `managed-topology` service can be loaded into NSO using the CLI `load
merge` command.

```
admin@ncs# load merge simple-lab-service.xml
Loading.
1.21 KiB parsed in 0.01 sec (63.40 KiB/sec)

admin@ncs# commit
Commit complete.
```

Once the transaction is committed, NSO will `define` and `start` the topology
on the KVM host defined above. After all the devices have booted, NSO will
configure them with the above services. The progress can be monitored using the
[service plan](#service-plan).

If running NSO using the Docker build, this file can be copied to the
`/system/root` directory before building the docker image so it will be
available to load from the home directory.

The content of the XML file is shown below.

```xml
<managed-topology>
  <topology>simple-lab</topology>
  <loopback-interfaces>
    <loopback>
      <id>0</id>
      <ipv4-subnet-start>198.10.1</ipv4-subnet-start>
      <primary/>
    </loopback>
  </loopback-interfaces>
  <login-banner>Hello World!</login-banner>
  <logging/>
  <ntp-server>198.18.128.1</ntp-server>
  <interface-bandwidth>10000</interface-bandwidth>
  <lldp/>
  <static-routes>
    <route>
      <source-device>node-1</source-device>
      <destination-device>node-5</destination-device>
      <loopback-id>0</loopback-id>
    </route>
  </static-routes>
  <igp>
    <name>1</name>
    <devices>node-1</devices>
    <devices>node-2</devices>
    <devices>node-3</devices>
    <devices>node-4</devices>
    <is-is/>
  </igp>
  <bgp>
    <as-number>65000</as-number>
    <route-reflector>
      <routers>node-5</routers>
    </route-reflector>
    <provider-edge>
      <routers>node-3</routers>
      <routers>node-4</routers>
    </provider-edge>
  </bgp>
  <mpls>
    <ldp/>
    <rsvp/>
  </mpls>
</managed-topology>
```

### Allocated Resources

The topology model is updated with the management IP addresses, MAC addresses
and host interfaces that have been allocated by the `define` action. It is
then updated with link and network interface IPv4 addresses allocated by the
`ip-connectivity` service.

These are stored as operational data and can be seen using the CLI show
command below.

```
admin@ncs# show topologies topology simple-lab
    DEVICE                                  HOST
ID  NAME    IP ADDRESS   MAC ADDRESS        INTERFACE    STATUS
-----------------------------------------------------------------
1   node-1  198.18.1.41  02:c1:5c:01:01:ff  veth-1-l3v1  ready
2   node-2  198.18.1.42  02:c1:5c:01:02:ff  veth-2-l3v1  ready
3   node-3  198.18.1.43  02:c1:5c:01:03:ff  veth-3-l3v1  ready
4   node-4  198.18.1.44  02:c1:5c:01:04:ff  veth-4-l3v1  ready
5   node-5  198.18.1.45  02:c1:5c:01:05:ff  veth-5-l3v1  ready

A END   Z END       HOST                          IP            HOST                          IP        HOST
DEVICE  DEVICE  ID  INTERFACE  MAC ADDRESS        ADDRESS   ID  INTERFACE  MAC ADDRESS        ADDRESS   BRIDGE   MAC ADDRESS
------------------------------------------------------------------------------------------------------------------------------------
node-1  node-2  2   veth-1-2   02:c1:5c:01:01:02  10.1.2.1  1   veth-2-1   02:c1:5c:01:02:01  10.1.2.2  vbr-1-2  02:c1:5c:00:01:02
node-1  node-4  4   veth-1-4   02:c1:5c:01:01:04  10.1.4.1  1   veth-4-1   02:c1:5c:01:04:01  10.1.4.4  vbr-1-4  02:c1:5c:00:01:04
node-1  node-5  5   veth-1-5   02:c1:5c:01:01:05  10.1.5.1  1   veth-5-1   02:c1:5c:01:05:01  10.1.5.5  vbr-1-5  02:c1:5c:00:01:05
node-2  node-3  3   veth-2-3   02:c1:5c:01:02:03  10.2.3.2  2   veth-3-2   02:c1:5c:01:03:02  10.2.3.3  vbr-2-3  02:c1:5c:00:02:03
node-3  node-1  1   veth-3-1   02:c1:5c:01:03:01  10.1.3.3  3   veth-1-3   02:c1:5c:01:01:03  10.1.3.1  vbr-1-3  02:c1:5c:00:01:03
node-4  node-2  2   veth-4-2   02:c1:5c:01:04:02  10.2.4.4  4   veth-2-4   02:c1:5c:01:02:04  10.2.4.2  vbr-2-4  02:c1:5c:00:02:04

               |------------ A End Interface -------------||------------ Z End Interface -------------||-------- Network ---------|
```

In addition, the `libvirt topology list` command can be used to see what is
currently defined and running on the libvirt host.

```
admin@ncs# libvirt topology list

Devices:
    node-3:  vCPUs [2]  Memory [12288 MB]  [ACTIVE]
    node-1:  vCPUs [2]  Memory [12288 MB]  [ACTIVE]
    node-4:  vCPUs [2]  Memory [12288 MB]  [ACTIVE]
    node-2:  vCPUs [2]  Memory [12288 MB]  [ACTIVE]
    node-5:  vCPUs [2]  Memory [12288 MB]  [ACTIVE]

Link Networks:
    net-1-5 [vbr-1-5]: node-1 veth-1-5 <--> node-5 veth-5-1
    net-1-3 [vbr-1-3]: node-3 veth-3-1 <--> node-1 veth-1-3
    net-1-4 [vbr-1-4]: node-1 veth-1-4 <--> node-4 veth-4-1
    net-1-2 [vbr-1-2]: node-1 veth-1-2 <--> node-2 veth-2-1
    net-2-4 [vbr-2-4]: node-4 veth-4-2 <--> node-2 veth-2-4
    net-2-3 [vbr-2-3]: node-3 veth-3-2 <--> node-2 veth-2-3

Other Networks:
    net-ctrl [vbr-ctrl]:
       node-3 veth-3-ctrl
       node-1 veth-1-ctrl
       node-4 veth-4-ctrl
       node-2 veth-2-ctrl
       node-5 veth-5-ctrl
    net-host [vbr-host]:
       node-3 veth-3-host
       node-1 veth-1-host
       node-4 veth-4-host
       node-2 veth-2-host
       node-5 veth-5-host
    net-1-null [vbr-1-null]:
       node-1 veth-1-0
       node-1 veth-1-1
    net-2-null [vbr-2-null]:
       node-2 veth-2-0
       node-2 veth-2-2
       node-2 veth-2-5
    net-3-null [vbr-3-null]:
       node-3 veth-3-0
       node-3 veth-3-3
       node-3 veth-3-4
       node-3 veth-3-5
    net-4-null [vbr-4-null]:
       node-4 veth-4-0
       node-4 veth-4-3
       node-4 veth-4-4
       node-4 veth-4-5
    net-5-null [vbr-5-null]:
       node-5 veth-5-0
       node-5 veth-5-2
       node-5 veth-5-3
       node-5 veth-5-4
       node-5 veth-5-5

External Bridges:
    l3v1:
       node-3 veth-3-l3v1
       node-1 veth-1-l3v1
       node-4 veth-4-l3v1
       node-2 veth-2-l3v1
       node-5 veth-5-l3v1

Unused Networks:
    default [virbr0]

Storage Pools:
    vms:
        xrv9k-fullk9-x-7.7.1.qcow2   Capacity [46080 MB]  Allocation [3453 MB]
        node-1.qcow2                 Capacity [46080 MB]  Allocation [477 MB]
        node-1-day0.img              Capacity [0 MB]      Allocation [0 MB]
        node-2.qcow2                 Capacity [46080 MB]  Allocation [471 MB]
        node-2-day0.img              Capacity [0 MB]      Allocation [0 MB]
        node-3.qcow2                 Capacity [46080 MB]  Allocation [480 MB]
        node-3-day0.img              Capacity [0 MB]      Allocation [0 MB]
        node-4.qcow2                 Capacity [46080 MB]  Allocation [479 MB]
        node-4-day0.img              Capacity [0 MB]      Allocation [0 MB]
        node-5.qcow2                 Capacity [46080 MB]  Allocation [465 MB]
        node-5-day0.img              Capacity [0 MB]      Allocation [0 MB]
```

### Service Plan

The `managed-topology` service plan has a component for each device in the
topology. Each component has states to show when the device is `reachable` and
`synced` in NSO. There are also components for each service to be configured on
the topology. The plan can be viewed graphically in the NSO Web UI where it is
automatically updated as the service progresses, or using the CLI as shown
below.

```
admin@ncs# show topologies managed-topology simple-lab plan component | \
> de-select back-track | de-select goal | de-select state service-reference
                                                                                 POST ACTION
TYPE              NAME            STATE            STATUS   WHEN                 STATUS
-------------------------------------------------------------------------------------------------
self              self            init             reached  2022-07-27T12:38:07  -
                                  ready            reached  2022-07-27T12:52:33  -
libvirt-topology  topology        init             reached  2022-07-27T12:38:07  create-reached
                                  defined          reached  2022-07-27T12:38:12  create-reached
                                  ready            reached  2022-07-27T12:52:33  -
libvirt-device    node-1          init             reached  2022-07-27T12:38:07  -
                                  defined          reached  2022-07-27T12:38:09  -
                                  started          reached  2022-07-27T12:38:16  -
                                  reachable        reached  2022-07-27T12:52:00  -
                                  synced           reached  2022-07-27T12:52:12  -
                                  ready            reached  2022-07-27T12:52:12  -
libvirt-device    node-2          init             reached  2022-07-27T12:38:07  -
                                  defined          reached  2022-07-27T12:38:10  -
                                  started          reached  2022-07-27T12:38:18  -
                                  reachable        reached  2022-07-27T12:52:00  -
                                  synced           reached  2022-07-27T12:52:18  -
                                  ready            reached  2022-07-27T12:52:18  -
libvirt-device    node-3          init             reached  2022-07-27T12:38:07  -
                                  defined          reached  2022-07-27T12:38:10  -
                                  started          reached  2022-07-27T12:38:20  -
                                  reachable        reached  2022-07-27T12:52:00  -
                                  synced           reached  2022-07-27T12:52:26  -
                                  ready            reached  2022-07-27T12:52:26  -
libvirt-device    node-4          init             reached  2022-07-27T12:38:07  -
                                  defined          reached  2022-07-27T12:38:11  -
                                  started          reached  2022-07-27T12:38:22  -
                                  reachable        reached  2022-07-27T12:50:31  -
                                  synced           reached  2022-07-27T12:50:50  -
                                  ready            reached  2022-07-27T12:50:50  -
libvirt-device    node-5          init             reached  2022-07-27T12:38:07  -
                                  defined          reached  2022-07-27T12:38:12  -
                                  started          reached  2022-07-27T12:38:23  -
                                  reachable        reached  2022-07-27T12:52:00  -
                                  synced           reached  2022-07-27T12:52:33  -
                                  ready            reached  2022-07-27T12:52:33  -
initial-config    initial-config  init             reached  2022-07-27T12:52:33  -
                                  ip-connectivity  reached  2022-07-27T12:52:33  -
                                  base-config      reached  2022-07-27T12:52:33  -
                                  ready            reached  2022-07-27T12:52:33  -
igp               igp             init             reached  2022-07-27T12:52:33  -
                                  config           reached  2022-07-27T12:52:33  -
                                  ready            reached  2022-07-27T12:52:33  -
mpls              mpls            init             reached  2022-07-27T12:52:33  -
                                  config           reached  2022-07-27T12:52:33  -
                                  ready            reached  2022-07-27T12:52:33  -
bgp               bgp             init             reached  2022-07-27T12:52:33  -
                                  config           reached  2022-07-27T12:52:33  -
                                  ready            reached  2022-07-27T12:52:33  -
```

**Note:** The `libvirt-topology` `init` and `defined` states use a
`post-action-node` to automatically run the libvirt `define` and `start`
actions.

### Topology Verification

Once the topology devices have been configured, connectivity can be verified
on the routers directly.

The following are examples of show commands that verify the configuration is
working as expected. These have been ran on node-3. This node is in the IS-IS
domain and has a BGP neighbour (node-5).

1. Verify the IS-IS topology has been learnt.

```
RP/0/RP0/CPU0:node-3#show isis topology
Wed Jul 27 12:58:40.953 UTC

IS-IS 1 paths to IPv4 Unicast (Level-1) routers
System Id          Metric    Next-Hop           Interface       SNPA
node-3             --

IS-IS 1 paths to IPv4 Unicast (Level-2) routers
System Id          Metric    Next-Hop           Interface       SNPA
node-1             10        node-1             Gi0/0/0/1       *PtoP*
node-2             10        node-2             Gi0/0/0/2       *PtoP*
node-3             --
node-4             20        node-1             Gi0/0/0/1       *PtoP*
node-4             20        node-2             Gi0/0/0/2       *PtoP*
```

2. Verify the MPLS interfaces are configured.

```
RP/0/RP0/CPU0:node-3#show mpls interfaces
Wed Jul 27 12:59:14.089 UTC
Interface                  LDP      Tunnel   Static   Enabled
-------------------------- -------- -------- -------- --------
GigabitEthernet0/0/0/2     Yes      No       No       Yes
GigabitEthernet0/0/0/1     Yes      No       No       Yes
```

3. Verify the BGP session has been established with the route reflector.

```
RP/0/RP0/CPU0:node-3#show bgp neighbors brief
Wed Jul 27 12:59:46.655 UTC

Neighbor        Spk    AS Description                          Up/Down  NBRState
198.10.1.5        0 65000                                      00:06:04 Established
```
