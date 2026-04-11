from asyncio import CancelledError
from dataclasses import dataclass, field, fields
import json
import re
import subprocess
from types import MappingProxyType
from typing import Any

import jsons

from .mqtt_client import MqttClient
from .globals import logger, deamon_opts, __version__


@dataclass
class PowerlineDevice:
    mac:str                      = field(metadata={'topic_part': 'mac'})
    chipset:str|None             = field(default=None, metadata={'topic_part': 'chipset'})
    version:str|None             = field(default=None, metadata={'topic_part': 'version'})
    nid:str|None                 = field(default=None, metadata={'topic_part': 'nid', 
                                                                 'hass_platform': 'sensor'})
    net:str|None                 = field(default=None, metadata={'topic_part': 'net'})
    mfg:str|None                 = field(default=None, metadata={'topic_part': 'mfg'})
    usr:str|None                 = field(default=None, metadata={'topic_part': 'usr'})
    link:str|None                = field(default=None, metadata={'topic_part': 'link', 
                                                                 'hass_platform': 'binary_sensor',
                                                                 'hass_payload_on': '1',
                                                                 'hass_payload_off': '0'})
    txList:dict[str,int]|None    = field(default=None, metadata={'topic_part': 'tx', 
                                                                 'hass_platform': 'sensor',
                                                                 'hass_state_class': 'measurement',
                                                                 'hass_unit_of_measurement': 'Mbps'})
    rxList:dict[str,int]|None    = field(default=None, metadata={'topic_part': 'rx', 
                                                                 'hass_platform': 'sensor',
                                                                 'hass_state_class': 'measurement',
                                                                 'hass_unit_of_measurement': 'Mbps'})
    ha_id:str|None               = field(default=None)

    def _ha_id_from_str(self, val:str) -> str :
        out = val.strip()
        out = out.strip( '/')
        out = re.sub( r"[^a-zA-Z0-9_-]", "_", out)
        return out

    def __post_init__(self) -> None:
        self.mac = self.mac.lower()
        self.ha_id = self._ha_id_from_str('plc_'+self.mac.replace(':', ''))

        tmpStdout = subprocess.run(['plctool', '-i', deamon_opts['interface'], '-qr', self.mac], 
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        self.chipset = tmpStdout.split()[2]
        self.version = tmpStdout.split()[3]

        tmpStdout = subprocess.run(['plctool', '-i', deamon_opts['interface'], '-qI', self.mac], 
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

        tmpStdout = subprocess.run(['plctool', '-i', deamon_opts['interface'], '-qL', self.mac], 
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading powerline device information for MAC {self.mac} using plctool.')
        self.link = tmpStdout.split()[2]

        tmpStdout = subprocess.run(['plcrate', '-i', deamon_opts['interface'], self.mac], 
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
    
    def send_mqtt_active(self, mqttc:MqttClient) -> None:
        mqttc.publish_device_availability(self.mac, True)
        for f in fields(self):
            value = getattr(self, f.name)
            topic_part = f.metadata.get('topic_part', None)
            if value==None or topic_part==None:
                continue
            if isinstance(value, dict):
                for topic_subpart, sub_value in value.items():
                    mqttc.publish_value(self.mac, f'{topic_part}/{topic_subpart}', sub_value)
            else:
                mqttc.publish_value(self.mac, topic_part, value)

    def send_mqtt_dead(self, mqttc:MqttClient) -> None:
        mqttc.publish_device_availability(self.mac, False)
        if mqttc.retain_values:
            for f in fields( self):
                value = getattr(self, f.name)
                topic_part = f.metadata.get('topic_part', None)
                if value==None or topic_part==None:
                    continue
                if isinstance(value, dict):
                    for topic_subpart in value.keys():
                        mqttc.publish_value(self.mac, f'{topic_part}/{topic_subpart}', '')
                else:
                    mqttc.publish_value(self.mac, topic_part, '')

    def send_hass_autodiscovery_active(self, mqttc:MqttClient) -> None:
        def get_component_spec(metadata:MappingProxyType[Any, Any], compontent_id:str, mqtt_topic:str) -> dict[str, Any]:
            component_spec = {
                'platform': metadata.get('hass_platform', None),
                'availability': [
                    {
                        "payload_available": f'{mqttc.get_avail_message(True)}',
                        "payload_not_available": f'{mqttc.get_avail_message(False)}',
                        "topic": f'{mqttc.get_topic_daemon_avail()}'
                    },
                    {
                        "payload_available": f'{mqttc.get_avail_message(True)}',
                        "payload_not_available": f'{mqttc.get_avail_message(False)}',
                        "topic": f'{mqttc.get_topic_device_availability(self.mac)}'
                    },
                ],
                'availability_mode': 'all',
                'expire_after': deamon_opts['cycle-time']*3,
                'name': f'{compontent_id}',
                'unique_id': f'{compontent_id}',
                'default_entity_id': f'{compontent_id}',
                'state_topic': mqtt_topic,
            }
            for key in metadata.keys():
                if key.startswith('hass_') and key not in ['hass_platform']:
                    component_spec[key[5:]] = metadata[key]
            return component_spec

        discovery_spec = {}
        discovery_spec['device'] = {
            'identifiers': [ f'{self.ha_id}' ],
            'manufacturer': f'{self.usr}/{self.mfg}', 
            'sw_version': f'{self.version}', 
            'hw_version': f'{self.chipset}',
            'serial_number': f'{self.mac}', 
            'name': f'{self.ha_id}', 
        }
        discovery_spec['origin'] = { 
            'name': 'powerlineStat2mqtt', 
            'sw_version': f'{__version__}', 
            # 'support_url': ""
        }

        components = {}
        for f in fields(self):
            value = getattr(self, f.name)
            topic_part = f.metadata.get('topic_part', None)
            hass_platform = f.metadata.get('hass_platform', None)
            if value==None or topic_part==None or hass_platform==None:
                continue
            if isinstance(value, dict):
                for topic_subpart in value.keys():
                    compontent_id = f'{self.ha_id}_{self._ha_id_from_str(topic_part)}_{self._ha_id_from_str(topic_subpart)}'
                    mqtt_topic = mqttc.get_topic_value(self.mac, f'{topic_part}/{topic_subpart}')
                    components[compontent_id] = get_component_spec(f.metadata, compontent_id, mqtt_topic)
            else:
                compontent_id = f'{self.ha_id}_{self._ha_id_from_str(topic_part)}'
                mqtt_topic = mqttc.get_topic_value(self.mac, topic_part)
                components[compontent_id] = get_component_spec(f.metadata, compontent_id, mqtt_topic)
        discovery_spec['components'] = components

        disco_dump = jsons.dump(discovery_spec, strip_nulls=False, strip_privates=True)
        discovery_spec_str = json.JSONEncoder( skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, sort_keys=False, indent=2, separators=None, default=None).encode(disco_dump)
        mqttc.publish_hass_autodiscovery_entity(f'device/{self.ha_id}/config', discovery_spec_str)


@dataclass
class PowerlineStatus:
    localPlcDevMac:str|None  = None
    allPlcDevMacSet:set[str] = field(default_factory=set)
    allDevices:dict[str, PowerlineDevice] = field(default_factory=dict)

    def __post_init__(self):
        tmpStdout = subprocess.run(['plctool', '-i', deamon_opts['interface'], '-qr'], 
                                        capture_output=True, text=True, check=True).stdout.strip()
        if not tmpStdout:
            raise Exception(f'Error reading MAC of local powerline using plctool.')
        self.localPlcDevMac = tmpStdout.split()[1].lower()
        
        tmpStdout = subprocess.run(['plctool', '-i', deamon_opts['interface'], '-qm', self.localPlcDevMac], 
                                        capture_output=True, text=True, check=True).stdout
        if not tmpStdout:
            raise Exception(f'Error reading MACs of remote powerlines using plctool.')
        self.allPlcDevMacSet = {m.lower() for m in re.findall(r'station->MAC\s*=\s*(\S+)', tmpStdout)}
        self.allPlcDevMacSet.add(self.localPlcDevMac)

        for mac in self.allPlcDevMacSet:
            try:
                self.allDevices[mac] = PowerlineDevice(mac)
            except Exception as e:
                print(f"Error creating PowerlineDevice for MAC {mac}: {e}")
            except (CancelledError, KeyboardInterrupt) as e:
                pass

    def compare_status(self, other:'PowerlineStatus') -> bool:
        if not other:
            return False
        return self.allPlcDevMacSet == other.allPlcDevMacSet

    def send_mqtt(self, mqttc:MqttClient, old:'PowerlineStatus|None') -> None:
        if old:
            for old_mac in old.allPlcDevMacSet-self.allPlcDevMacSet:
                old.allDevices[old_mac].send_mqtt_dead(mqttc)
        for dev in self.allDevices.values():
            dev.send_mqtt_active(mqttc)

    def send_hass_autodiscovery(self, mqttc:MqttClient, old:'PowerlineStatus|None') -> None:
        if not old or self.allPlcDevMacSet != old.allPlcDevMacSet:
            for dev in self.allDevices.values():
                dev.send_hass_autodiscovery_active(mqttc)


