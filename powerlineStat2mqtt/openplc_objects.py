#
# powerlineStat2mqtt - Powerline devices handled via open-plc-utils (plctool / plcrate)
# https://github.com/HaraldR42/powerlineStat2mqtt
#
# Written in 2026 by Harald Roelle
# Provided under the terms of the GPL 3.0 License
#

from dataclasses import dataclass, field
import re
import subprocess

from .globals import deamon_opts, logger
from .powerline_objects import PowerlineDevice, PowerlineStatus


###################################################################################################################
#
# A single powerline device addressed through open-plc-utils
#

@dataclass
class OpenplcDevice(PowerlineDevice):

    # Measured/monitored attributes of an open-plc-utils device. The ones with a shared meaning
    # reuse the topic part / metadata from PowerlineDevice; 'link' additionally pins down its own
    # binary_sensor payloads.
    chipset:str|None         = field(default=None, metadata=PowerlineDevice.META_CHIPSET)
    version:str|None         = field(default=None, metadata=PowerlineDevice.META_VERSION)
    mfg:str|None             = field(default=None, metadata=PowerlineDevice.META_MFG)
    usr:str|None             = field(default=None, metadata=PowerlineDevice.META_USR)
    nid:str|None             = field(default=None, metadata=PowerlineDevice.META_NID)
    net:str|None             = field(default=None, metadata=PowerlineDevice.META_NET)
    link:str|None            = field(default=None, metadata={'topic_part': PowerlineDevice.TOPIC_LINK,
                                                             'hass_platform': 'binary_sensor',
                                                             'hass_payload_on': '1',
                                                             'hass_payload_off': '0'})
    txList:dict[str,int]|None = field(default=None, metadata=PowerlineDevice.META_TX)
    rxList:dict[str,int]|None = field(default=None, metadata=PowerlineDevice.META_RX)

    def hass_device_manufacturer(self) -> str|None:
        return f'{self.usr}/{self.mfg}'

    def hass_device_sw_version(self) -> str|None:
        return self.version

    def hass_device_hw_version(self) -> str|None:
        return self.chipset

    def _read_device_data(self) -> None:
        iface = deamon_opts['interface']

        tmpStdout = subprocess.run(['plctool', '-i', iface, '-qr', self.mac],
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        self.chipset = tmpStdout.split()[2]
        self.version = tmpStdout.split()[3]

        tmpStdout = subprocess.run(['plctool', '-i', iface, '-qI', self.mac],
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        plcInfo = {}
        for line in tmpStdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Split on first whitespace into key and value
            parts = line.split()
            # Special handling for "Security level"
            if parts[0] == 'Security':
                key = f'{parts[0]}_{parts[1]}'
                value = ' '.join(parts[2:])
            else:
                key = parts[0]
                value = ' '.join(parts[1:])
            plcInfo[key] = value
        self.nid = plcInfo.get("NID", "")
        self.net = plcInfo.get("NET", "")
        self.mfg = plcInfo.get("MFG", "")
        self.usr = plcInfo.get("USR", "")

        tmpStdout = subprocess.run(['plctool', '-i', iface, '-qL', self.mac],
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        self.link = tmpStdout.split()[2]

        tmpStdout = subprocess.run(['plcrate', '-i', iface, self.mac],
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        self.txList = {}
        self.rxList = {}
        for line in tmpStdout.strip().splitlines():
            parts = line.split()
            dst_mac   = parts[2].lower()
            direction = parts[3].lower()
            rate      = int(parts[4], 10)
            if direction == 'rx':
                self.rxList[dst_mac] = rate
            else:
                self.txList[dst_mac] = rate


###################################################################################################################
#
# Discovery of all powerline devices reachable via open-plc-utils
#

@dataclass
class OpenplcStatus(PowerlineStatus):

    def _create_device(self, mac:str) -> PowerlineDevice:
        return OpenplcDevice(mac)

    def _discover_devices(self) -> None:
        iface = deamon_opts['interface']

        tmpStdout = subprocess.run(['plctool', '-i', iface, '-qr'],
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            logger.debug(f'No local powerline device found on interface {iface} (plctool -qr returned nothing).')
            self.localPlcDevMac = ''
            self.allPlcDevMacSet = set()
            self._build_devices()
            return
        self.localPlcDevMac = tmpStdout.split()[1].lower()

        tmpStdout = subprocess.run(['plctool', '-i', iface, '-qm', self.localPlcDevMac],
                                        capture_output=True, text=True, check=True).stdout
        if not tmpStdout:
            logger.warning(f'No remote powerline devices reported by plctool -qm on interface {iface}.')
        self.allPlcDevMacSet = {m.lower() for m in re.findall(r'station->MAC\s*=\s*(\S+)', tmpStdout)}
        self.allPlcDevMacSet.add(self.localPlcDevMac)

        self._build_devices()
