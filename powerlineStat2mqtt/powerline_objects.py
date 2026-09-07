#
# powerlineStat2mqtt - Abstract powerline device/status model
# https://github.com/HaraldR42/powerlineStat2mqtt
#
# Written in 2026 by Harald Roelle
# Provided under the terms of the GPL 3.0 License
#

from abc import ABC, abstractmethod
from asyncio import CancelledError
from dataclasses import dataclass, field, fields
import json
import re
from types import MappingProxyType
from typing import Any

import jsons

from .mqtt_client import MqttClient
from .globals import logger, deamon_opts, __version__


###################################################################################################################
#
# Abstract powerline device
#
# Different kinds of powerline devices are reachable via different command line tools (open-plc-utils,
# pla_util, ...) and, more importantly, expose a *different* set of measured/monitored attributes.
#
# A concrete subclass is a ``@dataclass`` that:
#   * adds whatever measured/monitored attributes its backing tool provides, each declared as a
#     dataclass field carrying at least ``topic_part`` metadata (and optionally ``hass_*`` metadata
#     for Home Assistant auto discovery),
#   * implements ``_read_device_data()`` to populate those attributes.
#
# Everything below (MQTT publishing, Home Assistant auto discovery) is generic: it simply walks the
# dataclass fields and publishes every one that carries ``topic_part`` metadata and currently holds a
# non-None value. Subclasses therefore never need to touch the MQTT plumbing.
#

@dataclass
class PowerlineDevice(ABC):

    # ---------------------------------------------------------------------------------------------
    # Shared MQTT topic parts and field metadata.
    #
    # The measured/monitored attributes differ per backend, but several of them are semantically
    # "the same thing" (a chipset name, a firmware/hardware version, an HFID, a PHY rate list, ...).
    # For those, a subclass should reuse the topic part / metadata defined here so that, e.g., the
    # PHY tx rate of an open-plc-utils device and of a pla-util device land on the same MQTT topic
    # (``.../<mac>/tx/<peer>``) and produce the same kind of Home Assistant entity. Backend specific
    # attributes just declare their own ``topic_part``.

    TOPIC_MAC     = 'mac'
    TOPIC_CHIPSET = 'chipset'
    TOPIC_VERSION = 'version'
    TOPIC_MFG     = 'mfg'
    TOPIC_USR     = 'usr'
    TOPIC_NID     = 'nid'
    TOPIC_NET     = 'net'
    TOPIC_LINK    = 'link'
    TOPIC_TX      = 'tx'
    TOPIC_RX      = 'rx'

    META_MAC     = MappingProxyType({'topic_part': TOPIC_MAC})
    META_CHIPSET = MappingProxyType({'topic_part': TOPIC_CHIPSET})
    META_VERSION = MappingProxyType({'topic_part': TOPIC_VERSION})
    META_MFG     = MappingProxyType({'topic_part': TOPIC_MFG})
    META_USR     = MappingProxyType({'topic_part': TOPIC_USR})
    META_NET     = MappingProxyType({'topic_part': TOPIC_NET})
    META_NID     = MappingProxyType({'topic_part': TOPIC_NID,
                                     'hass_platform': 'sensor'})
    META_TX      = MappingProxyType({'topic_part': TOPIC_TX,
                                     'hass_platform': 'sensor',
                                     'hass_state_class': 'measurement',
                                     'hass_unit_of_measurement': 'Mbps'})
    META_RX      = MappingProxyType({'topic_part': TOPIC_RX,
                                     'hass_platform': 'sensor',
                                     'hass_state_class': 'measurement',
                                     'hass_unit_of_measurement': 'Mbps'})

    # The only attribute every kind of powerline device shares is its MAC (and the ha_id derived
    # from it). Everything a device measures/reports - including "identity" fields like chipset,
    # firmware or manufacturer strings - is tool specific and declared on the subclass.
    mac:str        = field(metadata=META_MAC)
    ha_id:str|None = field(default=None)

    #------------------------------------------------------------------------------------------------------------------
    # Construction
    #

    def _ha_id_from_str(self, val:str) -> str :
        out = val.strip()
        out = out.strip( '/')
        out = re.sub( r"[^a-zA-Z0-9_-]", "_", out)
        return out

    def __post_init__(self) -> None:
        self.mac = self.mac.lower()
        self.ha_id = self._ha_id_from_str('plc_'+self.mac.replace(':', ''))
        self._read_device_data()

    @abstractmethod
    def _read_device_data(self) -> None:
        """Populate the measured/monitored attributes of this device.

        Called from ``__post_init__`` with ``self.mac`` / ``self.ha_id`` already set. Must raise on
        any unrecoverable read error.
        """
        raise NotImplementedError

    #------------------------------------------------------------------------------------------------------------------
    # Home Assistant device metadata - override in a subclass to expose what the backing tool reports
    #

    def hass_device_manufacturer(self) -> str|None:
        return None

    def hass_device_sw_version(self) -> str|None:
        return None

    def hass_device_hw_version(self) -> str|None:
        return None

    #------------------------------------------------------------------------------------------------------------------
    # Generic MQTT publishing
    #

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
            'serial_number': f'{self.mac}',
            'name': f'{self.ha_id}',
        }
        for key, val in (('manufacturer', self.hass_device_manufacturer()),
                         ('sw_version', self.hass_device_sw_version()),
                         ('hw_version', self.hass_device_hw_version())):
            if val is not None:
                discovery_spec['device'][key] = f'{val}'
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


###################################################################################################################
#
# Abstract powerline status
#
# Discovering which powerline devices exist is also tool specific. A concrete subclass implements
# ``_discover_devices()`` (populating ``localPlcDevMac`` / ``allPlcDevMacSet``, then calling
# ``_build_devices()``) and ``_create_device()`` (the concrete PowerlineDevice factory).
#

@dataclass
class PowerlineStatus(ABC):
    localPlcDevMac:str|None  = None
    allPlcDevMacSet:set[str] = field(default_factory=set)
    allDevices:dict[str, PowerlineDevice] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._discover_devices()

    @abstractmethod
    def _discover_devices(self) -> None:
        """Populate ``localPlcDevMac``, ``allPlcDevMacSet`` and ``allDevices``.

        Typically ends with a call to ``_build_devices()``.
        """
        raise NotImplementedError

    @abstractmethod
    def _create_device(self, mac:str) -> PowerlineDevice:
        """Create the concrete PowerlineDevice for ``mac``."""
        raise NotImplementedError

    def _build_devices(self) -> None:
        for mac in self.allPlcDevMacSet:
            try:
                self.allDevices[mac] = self._create_device(mac)
            except Exception as e:
                logger.error(f'Error creating powerline device for MAC {mac}: {e}')
            except (CancelledError, KeyboardInterrupt):
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


###################################################################################################################
#
# Merged status
#
# When more than one backend is selected, each is discovered independently and the per-backend
# results are presented as a single combined view. The backends address different chipsets, so their
# device sets are expected to be disjoint; should the same MAC show up twice, the first backend wins.
#

class MergedPowerlineStatus(PowerlineStatus):

    def __init__(self, parts:list[PowerlineStatus]) -> None:
        self.parts = parts
        self.localPlcDevMac = None
        self.allPlcDevMacSet = set()
        self.allDevices = {}
        for part in parts:
            self.allPlcDevMacSet |= part.allPlcDevMacSet
            for mac, dev in part.allDevices.items():
                if mac in self.allDevices:
                    logger.warning(f'Powerline device {mac} reported by more than one backend; keeping the first.')
                    continue
                self.allDevices[mac] = dev

    def _discover_devices(self) -> None:
        pass  # each part discovered itself at construction time

    def _create_device(self, mac:str) -> PowerlineDevice:
        raise NotImplementedError('MergedPowerlineStatus aggregates already-built backends.')


###################################################################################################################
#
# Factory
#

def _create_powerline_status_for_tool(tool:str) -> PowerlineStatus:
    if tool == 'open-plc-utils':
        from .openplc_objects import OpenplcStatus
        return OpenplcStatus()
    if tool == 'pla-util':
        from .plautil_objects import PlaUtilStatus
        return PlaUtilStatus()
    raise Exception(f'Unsupported powerline tool "{tool}".')


def create_powerline_status() -> PowerlineStatus:
    """Instantiate the PowerlineStatus implementation(s) selected by ``deamon_opts['powerline-tool']``.

    The option accepts a single tool name, a YAML list, or a comma/space separated string. With more
    than one tool the per-backend results are merged into a single status view.
    """
    raw = deamon_opts['powerline-tool']
    tools = re.split(r'[,\s]+', raw.strip()) if isinstance(raw, str) else list(raw)
    tools = list(dict.fromkeys(t for t in tools if t))  # de-duplicate, keep order
    if not tools:
        raise Exception('No powerline tool selected (deamon_opts["powerline-tool"] is empty).')

    statuses = [_create_powerline_status_for_tool(t) for t in tools]
    return statuses[0] if len(statuses) == 1 else MergedPowerlineStatus(statuses)
