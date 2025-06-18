#!/usr/bin/python3
from abc import abstractmethod
from io import BytesIO

import base64
import crypt
import os
import subprocess

from passlib.hash import md5_crypt
from fs.tarfs import TarFS

import fs
import pycdlib

from virt.network import generate_ip_address
from virt.topology_status import get_hypervisor_output_node
from virt.virt_base import VirtBase

_ncs = __import__('_ncs')


def generate_volume_name(device_name):
    return f'{device_name}.qcow2'

def generate_day0_volume_name(device_name):
    return f'{device_name}-day0.img'


class Volume(VirtBase):
    def _load_templates(self):
        self._templates.load_template('templates', 'volume.xml')

    def load_day0_templates(self, devices):
        day0_templates = filter(None, set(self._dev_defs[
            device.definition].day0_file for device in devices))
        for template in day0_templates:
            self._templates.load_template('images', template)

    def _create_raw_disk_image(self, file_name, create_partition_table=True):
        size = 1024 * 1024 #1048576
        bytes_per_sector = 512
        sectors_per_track = 63
        heads = 2

        sectors = size / bytes_per_sector #2048
        actual_sectors = int(sectors // sectors_per_track * sectors_per_track) #32*63 = 2016
        actual_size = actual_sectors * bytes_per_sector #1032192
        cylinders = int(actual_sectors / sectors_per_track / heads) #16
        first_sector = sectors_per_track * int(create_partition_table) #63

        #dd if=/dev/zero of=test.img count=2016
        self._log.info(f'Creating empty disk image using temporary disk file '
                       f'{file_name}')
        with open(file_name, 'wb') as binary_file:
            binary_file.write(b'\x00' * actual_size)

        if first_sector > 0:
            #fdisk --cylinders 16 --heads 2 --sectors 63 test.img
            self._log.info('Creating partition table using fdisk')
            with subprocess.Popen(['fdisk',
                        '--cylinders', str(cylinders),
                        '--heads', str(heads),
                        '--sectors', str(sectors_per_track),
                        file_name],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    text=True) as fdisk:
                fdisk.communicate(
                        f'n\n' #Add partition
                        f'p\n' #Partition type (primary)
                        f'1\n' #Partition number
                        f'{first_sector}\n' #First sector
                        f'{actual_sectors-1}\n' #Last sector
                        f't\n' #Change partition type
                        f'01\n' #01 FAT12
                        f'a\n' #Toggle boot flag
                        f'w\n' #Write table and exit
                    )

        #mkfs.fat -F 12 -g 16/63 -h 1 -R 8 -s 8 -v --offset 63 ./test.img
        self._log.info('Formatting partition using mkfs.fat')
        subprocess.run(['mkfs.fat',
                '-F', '12', #FAT size
                '-g', f'{heads}/{sectors_per_track}', #Geometry
                '-h', '1', #Hiddens sectors
                '-R', '8', #Reserved sectors
                '-s', '8', #Sectors per cluster
                '--offset', f'{first_sector}',
                file_name],
            stdout=subprocess.DEVNULL, check=True)

        return first_sector*bytes_per_sector

    def _create_ios_day0_disk_image(self, file_name, variables):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file)

        self._log.info('Writing day0 file to partition')
        self._log.info(f'ios_config.txt:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            flash_drive.writetext('/ios_config.txt', day0_str)

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str

    def _create_junos_day0_disk_image(self, file_name, variables, vmx=True):
        day0_str = self._templates.apply_template(file_name, variables)
        tmp_disk_file = \
                f'tmp-{generate_day0_volume_name(variables["device-name"])}'

        offset = self._create_raw_disk_image(tmp_disk_file, not vmx)

        self._log.info('Writing day0 file to partition')
        self._log.info(f'/config/juniper.conf:\n{day0_str}')
        with fs.open_fs(f'fat://{tmp_disk_file}?'
                        f'offset={offset}') as flash_drive:
            with TarFS(flash_drive.openbin('/vmm-config.tgz', 'wb'),
                                write=True, compression='gz') as tarfile:
                tarfile.makedir('/config')
                tarfile.writetext('/config/juniper.conf', day0_str)
                if vmx:
                    tarfile.makedir('/boot')
                    tarfile.writetext('/boot/loader.conf',
                            self._templates.apply_template(
                                'junos-vmx-loader.conf', {}))

        with open(tmp_disk_file, 'rb') as binary_file:
            disk_byte_str = binary_file.read()

        self._log.info(f'Deleting temporary disk file {tmp_disk_file}')
        os.remove(tmp_disk_file)

        return disk_byte_str

    def _add_iso_file(self, iso, file_string, file_name):
        self._log.info(f'{file_name}:\n{file_string}')
        byte_str = file_string.encode()
        iso.add_fp(BytesIO(byte_str), len(byte_str), f'/{file_name}')

    def _create_iosxr_day0_iso_image(self, file_name, variables):
        day0_str = self._templates.apply_template(file_name, variables)
        self._log.info('Writing day0 file to iso stream')

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='config-1')
        self._add_iso_file(iso, day0_str, 'iosxr_config.txt')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()

    def _get_cloud_init_ethernets(self, device_id):
        network_config = ''
        for iface_id in range(self._network_mgr.get_num_device_ifaces()):
            network = self._network_mgr.get_iface_network_id(device_id,
                    iface_id) or self._network_mgr.get_iface_bridge_name(
                    device_id, iface_id)

            if network is None:
                continue

            ip_address_start = self._network_mgr.get_network(network)
            if ip_address_start is None:
                continue

            ip_address = generate_ip_address(ip_address_start, device_id)
            network_config += self._templates.apply_template(
                'ethernet.yaml', {
                    'iface-id': iface_id,
                    'ip-address': ip_address,
                    'mac-address': self._resource_mgr.\
                            generate_mac_address(device_id, iface_id, True)
                    })
            self._network_mgr.write_iface_data(device_id, iface_id, [
                ('ip-address', ip_address)])
        return network_config

    def _create_cloud_init_iso_image(self, device_id, file_name, variables):
        meta_data = self._templates.apply_template('meta-data.yaml', variables)
        network_config = self._templates.apply_template(
                'network-config.yaml',variables)
        network_config += self._get_cloud_init_ethernets(device_id)
        user_data = self._templates.apply_template(file_name, variables)

        self._log.info('Writing cloud-init files to iso stream')
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, vol_ident='cidata')

        self._add_iso_file(iso, meta_data, 'meta-data')
        self._add_iso_file(iso, network_config, 'network-config')
        self._add_iso_file(iso, user_data, 'user-data')

        iso_stream = BytesIO()
        iso.write_fp(iso_stream)

        iso.close()
        return iso_stream.getvalue()

    @abstractmethod
    def _create_day0_image(self, file_name, variables, device_id):
        image_byte_str = self._templates.apply_template(
                file_name, variables).encode()

        return image_byte_str

    def _create_day0_volume(self, libvirt, device_id, device_name, dev_def):
        volume_name = generate_day0_volume_name(device_name)
        mapping = self._resource_mgr.get_authgroup_mapping(dev_def.authgroup)

        variables = {
            'device-name': device_name,
            'ip-address': self._resource_mgr.generate_mgmt_ip_address(device_id),
            'mac-address': self._resource_mgr.generate_mac_address(
                device_id, 0xff, True),
            'username': mapping.remote_name,
            'password': crypt.crypt(_ncs.decrypt(mapping.remote_password),
                crypt.mksalt(crypt.METHOD_SHA512)),
            'password-md5': md5_crypt.using(salt_size=4).hash(
                _ncs.decrypt(mapping.remote_password)),
            **self._resource_mgr.mgmt_network_variables}

        if dev_def.day0_upload_file:
            with open(dev_def.day0_upload_file, 'rb') as binary_file:
                byte_array = binary_file.read()
            variables['file-content'] = base64.b64encode(byte_array).decode()

        self._templates.load_template('images', dev_def.day0_file)
        image_byte_str = self._create_day0_image(
                dev_def.day0_file, variables, device_id)

        pool = libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': len(image_byte_str),
            'format-type': 'raw'})

        self._log.info(
                f'[{libvirt.name}] Creating day0 volume {volume_name}')
        self._log.info(volume_xml_str)
        volume = pool.createXML(volume_xml_str)

        self._log.info(
                f'[{libvirt.name}] Uploading day0 image to volume {volume_name}')
        stream = libvirt.conn.newStream()
        volume.upload(stream, 0, len(image_byte_str))
        stream.send(image_byte_str)
        stream.finish()
        get_hypervisor_output_node(
                self._output, libvirt.name).volumes.create(volume_name)

    def _create_volume(self, libvirt, volume_name, pool_name,
            base_image_name, clone, new_size):
        pool = libvirt.conn.storagePoolLookupByName(pool_name)
        base_image = pool.storageVolLookupByName(base_image_name)
        volume_size = base_image.info()[1] if not clone else ''
        volume_xml_str = self._templates.apply_template('volume.xml', {
            'name': volume_name,
            'capacity': volume_size,
            'format-type': 'qcow2'})

        if clone:
            self._log.info(
                    f'[{libvirt.name}] '
                    f'Creating volume {volume_name} from {base_image_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXMLFrom(volume_xml_str, base_image)
        else:
            self._log.info(f'[{libvirt.name}] Creating volume {volume_name}')
            self._log.info(volume_xml_str)
            vol = pool.createXML(volume_xml_str)

        if new_size is not None:
            vol.resize(new_size*1024*1024*1024)
        get_hypervisor_output_node(
                self._output, libvirt.name).volumes.create(volume_name)

    def _delete_volume(self, libvirt, pool, volume_name, volume_type='volume'):
        if volume_name and volume_name in libvirt.volumes[pool.name()]:
            volume = pool.storageVolLookupByName(volume_name)
            self._log.info(f'[{libvirt.name}] '
                           f'Running delete on {volume_type} {volume_name}')
            volume.delete()
            get_hypervisor_output_node(
                    self._output, libvirt.name).volumes.create(volume_name)

    def define(self, device):
        dev_def = self._dev_defs[device.definition]

        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)

        if dev_def.device_type != 'XRd':
            self._create_volume(libvirt, generate_volume_name(device_name),
                    dev_def.storage_pool, dev_def.base_image,
                    dev_def.base_image_type == 'clone', dev_def.disk_size)

        if dev_def.day0_file is not None:
            self._create_day0_volume(
                    libvirt, int(device.id), device_name, dev_def)

    def undefine(self, device):
        dev_def = self._dev_defs[device.definition]
        device_name = device.device_name
        libvirt = self._hypervisor_mgr.get_device_libvirt(device.id)
        if dev_def.storage_pool in libvirt.volumes:
            pool = libvirt.conn.storagePoolLookupByName(dev_def.storage_pool)
            self._delete_volume(
                    libvirt, pool, generate_volume_name(device_name))

            if dev_def.day0_file is not None:
                day0_volume_name = generate_day0_volume_name(device_name)
                self._delete_volume(
                        libvirt, pool, day0_volume_name, 'day0 volume')

    def _action(self, action, *args):
        pass # only define and undefine supported
