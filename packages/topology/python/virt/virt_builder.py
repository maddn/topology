from virt.domain_libvirt import DomainLibvirt
from virt.volume import Volume
from virt.network import DomainNetworks, LinkNetwork, ExtraNetwork


class ConcreteDomainNetworks(DomainNetworks):

    def extra_mgmt_networks(self, action, output, device):
        super().extra_mgmt_networks(action, output, device)


class ConcreteDomain(DomainLibvirt):

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        super().add_extra_mgmt_interfaces(xml_builder, device)

    def add_day0_device(self, xml_builder, storage_pool):
        super().add_day0_device(xml_builder, storage_pool)


class ConcreteVolume(Volume):

    def _create_day0_image(self, file_name, variables, device_id):
        return super()._create_day0_image(file_name, variables, device_id)


class VirtBuilder():
    def __init__(self, factory):
        self._extra_network = factory.create(ExtraNetwork)
        self._link_network = factory.create(LinkNetwork)

        self._get_device_type = factory.get_device_type

        self._domain_builders = {}
        self._volume_builders = {}
        self._domain_networks_builders = {}

        self._factory = factory

    def domain(self, action, output, device):
        device_type = self._get_device_type(device)
        if device_type not in self._domain_builders:
            self._domain_builders[device_type] = self._factory.create(
                    self._factory.domain_registry.get(
                        device_type, ConcreteDomain))
        return self._domain_builders[device_type](action, output, device)

    def domain_networks(self, action, output, device):
        device_type = self._get_device_type(device)
        if device_type not in self._domain_networks_builders:
            self._domain_networks_builders[device_type] = \
                    self._factory.domain_networks_registry.get(
                            device_type, ConcreteDomainNetworks)(self._factory)
        return self._domain_networks_builders[device_type](action, output, device)

    def topology_networks(self, action, output, devices):
        for device_type, topology_networks_class in \
                self._factory.topology_networks_registry.items():
            topology_networks_class(self._factory)(action, output, [
                device.id for device in devices
                if self._get_device_type(device) == device_type ])

    def volume(self, action, output, device):
        device_type = self._get_device_type(device)
        if device_type not in self._volume_builders:
            self._volume_builders[device_type] = self._factory.create(
                    self._factory.volume_registry.get(
                            device_type, ConcreteVolume))
        return self._volume_builders[device_type](action, output, device)

    def link_network(self, *args):
        return self._link_network(*args)

    def extra_network(self, *args):
        return self._extra_network(*args)

    def is_domain_active(self, device):
        return self._domain_builders[
                self._get_device_type(device)].is_active(device)

    def domain_supports_shutdown(self, device):
        return self._domain_builders[
                self._get_device_type(device)].shutdown_supported()
