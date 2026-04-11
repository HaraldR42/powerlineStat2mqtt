#!/usr/bin/env python
#
# powerlineStat2mqtt - Powerline status monitor with MQTT output
# https://github.com/HaraldR42/powerlineStat2mqtt
#
# Written in 2026 by Harald Roelle
# Provided under the terms of the GPL 3.0 License
#


import argparse
import time
import sys
import asyncio

import powerlineStat2mqtt.globals as globs

from .config_reader import ConfigYaml
from .globals import logger, deamon_opts
from .powerline_objects import PowerlineStatus
from .mqtt_client import MqttClient



def status_loop(mqttc:MqttClient) -> None:
    logger.debug("Starting status loop.")     
    old_plc_status = None
    current_plc_status = None
    try:
        while True:
            old_plc_status = current_plc_status
            current_plc_status = PowerlineStatus()
            if deamon_opts['add-to-homeassistant']:
                current_plc_status.send_hass_autodiscovery(mqttc, old_plc_status)
                time.sleep(2)
            current_plc_status.send_mqtt(mqttc, old_plc_status)
            time.sleep(deamon_opts['cycle-time'])
    except Exception as e:
        logger.critical( f'Fatal error in main loop: {e}')
    except (asyncio.exceptions.CancelledError, KeyboardInterrupt) as e:
        pass
    
    if current_plc_status:
        for dev in current_plc_status.allDevices.values():
            dev.send_mqtt_dead(mqttc)



def main() -> None:
    if sys.version_info < globs.__min_version__:
        logger.fatal(f'{globs.__myname__} requires at least python {globs.__min_version__}. Exiting.')
        sys.exit(1)

    parser = argparse.ArgumentParser(prog=globs.__myname__,description='Powerline monitor with MQTT output.')
    parser.add_argument('--config', type=argparse.FileType('r'), help='Configuration file.')

    plcStatGroup = parser.add_argument_group( 'Powerline status check options', 'All options influencing the powerline status check and publish behaviour.')
    plcStatGroup.add_argument('--interface', type=int, help=f'Network interface to look for powerline devices. Default: {deamon_opts["interface"]}')
    plcStatGroup.add_argument('--cycle-time', type=str, help=f'Check and publish status every n seconds. Default: {deamon_opts["cycle-time"]}')

    mqttBrokerGroup = parser.add_argument_group( 'MQTT broker options', 'All options for connecting to an MQTT broker')
    mqttBrokerGroup.add_argument('--mqtt-host', help=f'MQTT server address. Default: "{deamon_opts["mqtt-host"]}"')
    mqttBrokerGroup.add_argument('--mqtt-port', type=int, help='Defaults to 8883 for TLS or 1883 for non-TLS')
    mqttBrokerGroup.add_argument('--mqtt-clientid', type=str, help=f'ID of our MQTT client. Default: "{deamon_opts["mqtt-clientid"]}"')
    mqttBrokerGroup.add_argument('--mqtt-user', help='Username for authentication (optional)')
    mqttBrokerGroup.add_argument('--mqtt-pass', help='Password for authentication (optional)')
    mqttBrokerGroup.add_argument('--mqtt-use-tls', type=bool, help=f'Use TLS. Default: "{deamon_opts["mqtt-use-tls"]}"')
    mqttBrokerGroup.add_argument('--mqtt-insecure', type=bool, help=f'Use TLS without providing certificates. Default: "{deamon_opts["mqtt-insecure"]}"')
    mqttBrokerGroup.add_argument('--mqtt-cacerts', help="Path to keychain")
    mqttBrokerGroup.add_argument('--mqtt-tls-version', choices=['tlsv1.2', 'tlsv1.1', 'tlsv1'], help=f'TLS protocol version, can be one of tlsv1.2 tlsv1.1 or tlsv1.')

    mqttPubGroup = parser.add_argument_group( 'MQTT publish options', 'All options influencing the MQTT related behaviour')
    mqttPubGroup.add_argument('--mqtt-topic', help=f'Topic prefix to be used for subscribing/publishing. Default: "{deamon_opts["mqtt-topic"]}"')
    mqttPubGroup.add_argument('--mqtt-value-qos', type=int, choices=[0,1,2], help=f'QoS value for publishing values. Default: "{deamon_opts["mqtt-value-qos"]}"')
    mqttPubGroup.add_argument('--retain-values', type=bool, help=f'Set retain flag for published modbus values. Default: "{deamon_opts["retain-values"]}"')

    miscGroup = parser.add_argument_group('Misc options', '')
    miscGroup.add_argument('--add-to-homeassistant', type=bool, help=f'Add devices to Home Assistant using Home Assistant\'s MQTT-Discovery. Default: "{deamon_opts["add-to-homeassistant"]}"')
    miscGroup.add_argument('--verbosity', choices=['debug', 'info', 'warning', 'error', 'critical'], help=f'Verbosity level. Default: "{deamon_opts["verbosity"]}"')

    args = parser.parse_args()

    if args.config:
        logger.info(f'Reading config file {args.config.name}.')
        # First parse daemon config from yaml
        if args.config.name.endswith('.yaml'):
            cfgReader = ConfigYaml(args.config)
            if cfgReader.config_error_count > 0:
                logger.critical("Configuration error. Exiting.")
                sys.exit(1)

    # As commandline args take precedence, overwrite values with ones from commandline
    args_dict = vars(args)
    for key in args_dict:
        opts_key = key.replace('_','-')
        if opts_key not in deamon_opts:
            logger.error( f'Unknown commandline option "{opts_key}"')
            sys.exit(1)
        if args_dict[key] != None:
            deamon_opts[opts_key] = args_dict[key]

    logger.setLevel(deamon_opts['verbosity'].upper())

    if deamon_opts['mqtt-port'] is None:
        deamon_opts['mqtt-port'] = 8883 if deamon_opts['mqtt-use-tls'] else 1883


    logger.info( f'Starting {globs.__myname__} V{globs.__version__}')

    mqtt_client = MqttClient(
                        mqtt_host=deamon_opts['mqtt-host'], 
                        mqtt_port=deamon_opts['mqtt-port'], 
                        mqtt_clientid=deamon_opts['mqtt-clientid'], 
                        mqtt_user=deamon_opts['mqtt-user'], 
                        mqtt_pass=deamon_opts['mqtt-pass'],
                        mqtt_cacerts=deamon_opts['mqtt-cacerts'], 
                        mqtt_insecure=deamon_opts['mqtt-insecure'], 
                        mqtt_tls_version=deamon_opts['mqtt-tls-version'], 
                        topic_base=deamon_opts['mqtt-topic'],
                        topic_hass_autodisco_base=deamon_opts['hass-discovery-prefix'],
                        retain_values=deamon_opts['retain-values'],
                        mqtt_value_qos=deamon_opts['mqtt-value-qos'])

    # Loop until initial connection to mqtt server is made. Reconnect is handled by mqtt client internally.
    try:
        while not mqtt_client.make_initial_connection():
            time.sleep(0.5)
    except (KeyboardInterrupt, SystemExit) as e:
        logger.critical(f'Stopped before initial MQTT connect. Exiting.')
        sys.exit(1)

    # Now comes the real main loop
    status_loop(mqtt_client)

    logger.critical(f'{globs.__myname__} stopped. Exiting.')
