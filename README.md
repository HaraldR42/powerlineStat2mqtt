# powerlineStat2mqtt
Small python app which detects powerline devices on the network and publishes the results via MQTT.<br>

It is intended as a building block in heterogeneous smart home environments where an MQTT message broker is used as the centralized message bus.<br>
**Special support is provided for Home Assistant (HASS).**

Written and (c) 2026 by Harald Roelle</br>
Provided under the terms of the GPL 3.0 license.

## Installation
Requirements:
- python3, version 3.14 or newer
- [Eclipse Paho for Python](http://www.eclipse.org/paho/clients/python/)
- [pyyaml](https://pyyaml.org/)
- [jsons](https://github.com/ramonhagenaars/jsons)
- [open-plc-utils](https://github.com/qca/open-plc-utils)

### Installation of requirements:
1. Install python3 and python3-pip and open-plc-utils<br>
  On a Debian based system, something like `sudo apt install python3 python3-pip plc-utils plc-utils-extra` will likely get you there.
1. run `pip3 install paho-mqtt`
1. run `pip3 install pyyaml`
1. run `pip3 install jsons`

## Configuration and usage

*powerlineStat2mqtt* supports two basic variants of configuration and launching:

1. Command line<br>
   `python3 powerlineStat2mqtt.py ... (lots of command line options)`<br>
   See `python3 powerlineStat2mqtt.py --help` for all options
2. YAML configuration file<br>
   `python3 powerlineStat2mqtt.py --config path-to-file.yaml`
   The yaml option nee to be placed in a section name `Daemon`.
   The options itself are the same as the command line options without the leading dashes.

## Docker
*powerlineStat2mqtt* can be run as a docker container, using the included Dockerfile. It allows all usual configuration options, with the expectation that it's configuration is at `/app/conf/powerlineStat2mqtt.conf.yaml`. For example:

To build the image:

`docker build -t powerlineStat2mqtt .`

To run the image:

`docker run -v $(pwd)/config/wago-352-530-430.yaml:/app/conf/modbus2mqtt_2.yaml --name powerlineStat2mqtt --hostname docker-plc2m -e TZ=Europe/Berlin powerlineStat2mqtt`


## MQTT

### Value publishing
Values are published as strings to topic:

*`mqtt-topic`* **/** *`device-name`* **/** ...<br>
- The prefix of all MQTT topics can be specified by option `mqtt-topic`
- `device-name` is derived from the MAC address of the found devices.

The published value messages do not have the MQTT retain flag set, but it can be turned on by the option `retain-values`.

### Availability / liveness publishing

To indicate if *powerlineStat2mqtt* is alive, the following topic is maintained:<br>
*`mqtt-topic`* **/** *`mqtt-client-name`* **/ connected**<br>
*`mqtt-client-name`* is derived from the hostname or set by `mqtt-clientid`. Publishing is done as MQTT last-will-and-testament (LWT). Therefore, the status shall be correct even if *powerlineStat2mqtt* dies unexpectedly.

To indicate the liveness of certain device, the following topic is set accordingly:<br>
*`mqtt-topic`* **/** *`device-name`* **/ connected**<br>
As this value is handled by *powerlineStat2mqtt* alone, this value might be wrong when *powerlineStat2mqtt* died unexpectedly.

## Home Assistant MQTT device discovery

To enable fully automated discovery via MQTT in Home Assistant, just set `add-to-homeassistant` to true and set XXX