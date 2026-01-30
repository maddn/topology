from virt.domain import Domain
from virt.network import generate_bridge_name
from virt.topology_status import write_node_data, get_hypervisor_output_node
from virt.volume import generate_day0_volume_name


class VxrJsonBuilder():
    def __init__(self, device_id, device_name,
            resource_mgr=None, network_mgr=None, templates=None):
        self._templates = templates
        self._resource_mgr = resource_mgr
        self._network_mgr = network_mgr
        self._device_name = device_name
        self._device_id = int(device_id)
        self.vxr_json = {}

    def _generate_mac_address(self, last_octet):
        return self._resource_mgr.generate_mac_address(
                self._device_id, last_octet, True)

    def _generate_iface_dev_name(self, other_id):
        return f'vtap-{self._device_id}-{other_id}'

    def add_mgmt_iface(self, iface_name):
        bridge_name = self._resource_mgr.mgmt_bridge

        bridge = self.vxr_json['connections']['custom'][bridge_name] = {}
        bridge['ports'] = [ f'{self._device_name}.{iface_name}' ]
        bridge['linux_bridge'] = bridge_name
        bridge['connection_type'] = 'tap'

    def add_data_ifaces(self, iface_prefix, first_iface = 0, device_id = None):
        for iface_id in range(first_iface,
                self._network_mgr.get_num_device_ifaces()):
            bridge_name = self._network_mgr.get_iface_bridge_name(
                    device_id or self._device_id, iface_id)
            network_id = self._network_mgr.get_iface_network_id(
                    device_id or self._device_id, iface_id)

            if network_id:
                bridge_name = generate_bridge_name(network_id)

            if bridge_name:
                bridge = self.vxr_json['connections']['custom'][bridge_name] = {}
                bridge['ports'] = [ f'{self._device_name}.{iface_prefix}/{iface_id}' ]
                bridge['linux_bridge'] = bridge_name
                bridge['connection_type'] = 'hub'

            if network_id or bridge_name:
                self._network_mgr.write_iface_data(
                    device_id or self._device_id, iface_id, [
                            ('id', iface_id)])

    def create_base(self, host, host_username, template):
        self.vxr_json = self._templates.apply_json_template(
            f'{template}.json', {
                'id': f'{self._device_id:02d}',
                'device-name': self._device_name,
                'host': host,
                'host-username': host_username,
                'cvac': generate_day0_volume_name(self._device_name)
            })

        connections = self.vxr_json['connections'] = {}
        connections['custom'] = {}


class DomainVxr(Domain):

    IFACE_PREFIX = 'FourHundredGigE0/0/0'
    MGMT_IFACE = 'eth0'

    FIRST_IFACE_ID = 0
    SHUTDOWN_SUPPORTED = False  #VXR does a synchronous stop

    def add_extra_mgmt_interfaces(self, xml_builder, device):
        pass

    def _undefine(self, device):
        return self._action('undefine', device)

    def _define(self, device):
        device_name = device.device_name
        vxr = self._hypervisor_mgr.get_device_vxr(device.id)

        self._log.info(f'[{vxr.name}] Defining domain {device_name}')

        mgmt_ip_address = self._resource_mgr.generate_mgmt_ip_address(device.id)
        mac_address = self._resource_mgr.generate_mac_address(device.id, 0xff, True)

        write_node_data(device.management_interface._path, [
                ('ip-address', mgmt_ip_address),
                ('mac-address', mac_address)])

    def create_sim(self, vxr, device):
        dev_def = self._dev_defs[device.definition]
        self._templates.load_template('images', f'{dev_def.template}.json')

        json_builder = VxrJsonBuilder(
                int(device.id),
                device.device_name,
                self._resource_mgr,
                self._network_mgr,
                self._templates)

        json_builder.create_base(
                vxr.get_host(),
                vxr.get_username(),
                dev_def.template)

        json_builder.add_mgmt_iface(self.MGMT_IFACE)

        json_builder.add_data_ifaces(
                self.IFACE_PREFIX,
                self.FIRST_IFACE_ID,
                device.control_plane_id)

        vxr.start(device.device_name, json_builder.vxr_json, device._path)

        for (iface_id, host_tap) in vxr.get_interfaces(device.device_name):
            self._network_mgr.write_iface_data(int(device.id), int(iface_id), [
                    ('id', iface_id),
                    ('host-interface', host_tap)])

    def shutdown_sim(self, vxr, device):
        vxr.stop(device.device_name, device._path)

    def undefine_sim(self, vxr, device):
        return True

    def reboot_sim(self, vxr, device):
        vxr.restart(device.device_name)

    def is_active(self, device):
        vxr = self._hypervisor_mgr.get_device_vxr(device.id)
        return vxr.is_active(device.device_name)

    def shutdown_supported(self):
        return self.SHUTDOWN_SUPPORTED

    def _action(self, action, *args):
        device, = args
        device_name = device.device_name
        vxr = self._hypervisor_mgr.get_device_vxr(device.id)

        # VXR status is messy. Define and create (start) is one action,
        # but stop and undefine (clean) are separate.
        # Just allow everything except starting an already started device
        if action != 'create' or not vxr.is_active(device_name):
            action_name = f'{action}_sim'
            if hasattr(self, action_name):
                self._log.info(f'[{vxr.name}] '
                               f'Running {action} on simulation {device_name}')
                action_method = getattr(self, action_name)
                result = action_method(vxr, *args)

                get_hypervisor_output_node(
                        self._output, vxr.name).domains.create(device_name)
                return result
        self._log.info(f'[{vxr.name}] Skipping {action} on simulation {device_name}')
        return False
