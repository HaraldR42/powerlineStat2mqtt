#
# powerlineStat2mqtt - Powerline devices handled via pla-util (Broadcom chipsets)
# https://github.com/HaraldR42/powerlineStat2mqtt
#
# Written in 2026 by Harald Roelle
# Provided under the terms of the GPL 3.0 License
#
# pla-util command model (see pla-util.txt for sample output):
#   * "pla-util -i <iface> discover"  ......  lists every adapter on the subnet, no target needed
#   * every other command takes "-p <mac>"  and must be issued once per device
#
# Commands used here, all run once per device per poll cycle:
#   get-capabilities   -> AV Version, OUI, Backup CCo, Proxy
#   get-station-info   -> Chip Version, Hardware Version
#   get-id-info        -> HomePlug AV Version, MCS
#   get-hfid           -> user HFID (single bare line)
#   get-hfid manufacturer -> manufacturer HFID (single bare line)
#   get-network-info   -> NID, SNID, TEI, Station Role, Network Kind, Status, CCo MAC
#   get-network-stats  -> per-peer average PHY data rates (to/from = tx/rx)
#   get-discover-list  -> per-neighbour signal level
#

from dataclasses import dataclass, field
import re
import subprocess

from .globals import deamon_opts
from .powerline_objects import PowerlineDevice, PowerlineStatus


#---------------------------------------------------------------------------------------------------
# pla-util invocation + output parsing helpers
#

def _pla_util(*args:str) -> str:
    return subprocess.run(['pla-util', '-i', deamon_opts['interface'], *args],
                          capture_output=True, text=True, check=True).stdout


def _parse_kv(text:str) -> dict[str,str]:
    """Parse flat 'Key: value' output (get-capabilities, get-station-info, get-id-info)."""
    out:dict[str,str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, value = line.partition(':')
        out[key.strip()] = value.strip()
    return out


def _parse_sections(text:str, header_re:str) -> list[dict[str,str]]:
    """Parse the repeated-block output (get-network-info / -stats / -discover-list).

    ``header_re`` matches the block header line ('Station 1:', 'Network 1:'); the indented
    'Key: value' lines that follow are collected into one dict per block.
    """
    sections:list[dict[str,str]] = []
    current:dict[str,str]|None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(header_re, stripped):
            current = {}
            sections.append(current)
            continue
        if current is not None and line[:1].isspace() and ':' in stripped:
            key, _, value = stripped.partition(':')
            current[key.strip()] = value.strip()
    return sections


def _mbps(value:str) -> int:
    """'118 Mbps' -> 118"""
    return int(value.split()[0], 10)


###################################################################################################
#
# A single powerline device addressed through pla-util
#

@dataclass
class PlaUtilDevice(PowerlineDevice):

    # Attributes with a meaning shared with other backends reuse the topic part / metadata from
    # PowerlineDevice so they publish to the same MQTT topics.
    chipset:str|None         = field(default=None, metadata=PowerlineDevice.META_CHIPSET)   # Chip Version
    version:str|None         = field(default=None, metadata=PowerlineDevice.META_VERSION)   # Hardware Version
    mfg:str|None             = field(default=None, metadata=PowerlineDevice.META_MFG)       # manufacturer HFID
    usr:str|None             = field(default=None, metadata=PowerlineDevice.META_USR)       # user HFID
    nid:str|None             = field(default=None, metadata=PowerlineDevice.META_NID)
    link:str|None            = field(default=None, metadata={'topic_part': PowerlineDevice.TOPIC_LINK,
                                                             'hass_platform': 'binary_sensor',
                                                             'hass_payload_on': 'JOINED',
                                                             'hass_payload_off': 'NOT_JOINED'})
    txList:dict[str,int]|None = field(default=None, metadata=PowerlineDevice.META_TX)
    rxList:dict[str,int]|None = field(default=None, metadata=PowerlineDevice.META_RX)

    # Attributes only pla-util reports.
    oui:str|None             = field(default=None, metadata={'topic_part': 'oui'})
    av_version:str|None      = field(default=None, metadata={'topic_part': 'av_version'})
    backup_cco:str|None      = field(default=None, metadata={'topic_part': 'backup_cco'})
    proxy:str|None           = field(default=None, metadata={'topic_part': 'proxy'})
    mcs:str|None             = field(default=None, metadata={'topic_part': 'mcs'})
    snid:str|None            = field(default=None, metadata={'topic_part': 'snid'})
    tei:str|None             = field(default=None, metadata={'topic_part': 'tei'})
    station_role:str|None    = field(default=None, metadata={'topic_part': 'role'})
    network_kind:str|None    = field(default=None, metadata={'topic_part': 'network_kind'})
    cco_mac:str|None         = field(default=None, metadata={'topic_part': 'cco_mac'})
    signalList:dict[str,str]|None = field(default=None, metadata={'topic_part': 'signal',
                                                                 'hass_platform': 'sensor'})

    def hass_device_manufacturer(self) -> str|None:
        return self.mfg

    def hass_device_hw_version(self) -> str|None:
        return self.version

    def _read_device_data(self) -> None:
        caps = _parse_kv(_pla_util('-p', self.mac, 'get-capabilities'))
        self.av_version = caps.get('AV Version')
        self.oui = caps.get('OUI')
        self.backup_cco = caps.get('Backup CCo')
        self.proxy = caps.get('Proxy')

        station = _parse_kv(_pla_util('-p', self.mac, 'get-station-info'))
        self.chipset = station.get('Chip Version')
        self.version = station.get('Hardware Version')

        id_info = _parse_kv(_pla_util('-p', self.mac, 'get-id-info'))
        self.mcs = id_info.get('MCS')

        self.usr = _pla_util('-p', self.mac, 'get-hfid').strip() or None
        self.mfg = _pla_util('-p', self.mac, 'get-hfid', 'manufacturer').strip() or None

        networks = _parse_sections(_pla_util('-p', self.mac, 'get-network-info'), r'^Network\s+\d+:$')
        if networks:
            net = networks[0]
            self.nid = net.get('NID')
            self.snid = net.get('SNID')
            self.tei = net.get('TEI')
            self.cco_mac = net.get('CCo MAC Address')
            self.station_role = net.get('Station Role')
            self.network_kind = net.get('Network Kind')
            self.link = net.get('Status')

        self.txList = {}
        self.rxList = {}
        for sta in _parse_sections(_pla_util('-p', self.mac, 'get-network-stats'), r'^Station\s+\d+:$'):
            da = sta.get('Destination Address (DA)')
            if not da:
                continue
            da = da.lower()
            if 'Avg PHY Data Rate to DA' in sta:
                self.txList[da] = _mbps(sta['Avg PHY Data Rate to DA'])
            if 'Avg PHY Data Rate from DA' in sta:
                self.rxList[da] = _mbps(sta['Avg PHY Data Rate from DA'])

        self.signalList = {}
        for sta in _parse_sections(_pla_util('-p', self.mac, 'get-discover-list'), r'^Station\s+\d+:$'):
            peer = sta.get('MAC Address')
            level = sta.get('Signal Level')
            if peer and level:
                self.signalList[peer.lower()] = level


###################################################################################################
#
# Discovery of all powerline devices reachable via pla-util
#

@dataclass
class PlaUtilStatus(PowerlineStatus):

    _DISCOVER_RE = re.compile(r'^([0-9a-fA-F:]{17})\s+via\s+(\S+)\s+interface,\s+HFID:\s*(.*)$')

    def _create_device(self, mac:str) -> PowerlineDevice:
        return PlaUtilDevice(mac)

    def _discover_devices(self) -> None:
        stdout = _pla_util('discover')
        if not stdout.strip():
            raise Exception('Error discovering powerline devices using pla-util.')
        for line in stdout.splitlines():
            m = PlaUtilStatus._DISCOVER_RE.match(line.strip())
            if not m:
                continue
            mac = m.group(1).lower()
            via = m.group(2)
            self.allPlcDevMacSet.add(mac)
            # 'via PLC interface' == reached across the powerline; anything else (MII*) is the
            # adapter directly attached to this host.
            if via.upper() != 'PLC':
                self.localPlcDevMac = mac
        if not self.allPlcDevMacSet:
            raise Exception('pla-util discover returned no usable devices.')

        self._build_devices()
