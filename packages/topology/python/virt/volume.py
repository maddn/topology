#!/usr/bin/python3
from abc import abstractmethod
from io import BytesIO

import base64
import crypt
import subprocess

from passlib.hash import md5_crypt
from fs.tarfs import TarFS

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

    def _add_iso_file(self, iso, file_string, file_name):
        self._log.debug(f'{file_name}:\n{file_string}')
        byte_str = file_string.encode()
        iso.add_fp(BytesIO(byte_str), len(byte_str), f'/{file_name}')

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
        self._log.debug(volume_xml_str)
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
            self._log.debug(volume_xml_str)
            vol = pool.createXMLFrom(volume_xml_str, base_image)
        else:
            self._log.info(f'[{libvirt.name}] Creating volume {volume_name}')
            self._log.debug(volume_xml_str)
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

        if not dev_def.device_type in ['XRd', 'SR-Linux']:
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
