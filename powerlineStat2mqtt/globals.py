import logging
import socket

__version__ = "2.0.1"
__myname__ = "powerlineStat2mqtt"
__myname_short__ = "plc2m"
__min_version__ = (3,14)

logging.basicConfig()
logger = logging.getLogger('main-logger')


###################################################################################################################
#
# Following dicts serve three purposes:
#   - Definition of yaml configuration options
#   - Provide default value for each option
#   - Store the actual values of options after parsing the config files
#
# For additional Home Assistant specific options see home_assistant.py
#

# Configuration options for daemon section with default values
deamon_opts = {
    'config':                   None,

    # Powerline status check options
    'interface':                'eth0',             # Network interface to look for powerline devices.
    'cycle-time':               60,                 # Check and publish status every n seconds.

    # MQTT broker options: All options for connecting to an MQTT broker
    'mqtt-host':                'localhost',        # MQTT server address. Defaults to "localhost"
    'mqtt-port':                None,               # Defaults to 8883 for TLS or 1883 for non-TLS
    'mqtt-clientid':            f'plc2mqtt-{socket.gethostname().split(".")[0]}',
    'mqtt-user':                None,               # Username for authentication (optional)
    'mqtt-pass':                "",                 # Password for authentication (optional)
    'mqtt-use-tls':             False,              # Use TLS
    'mqtt-insecure':            False,              # Use TLS without providing certificates
    'mqtt-cacerts':             None,               # Path to keychain
    'mqtt-tls-version':         None,               # TLS protocol version, can be one of tlsv1.2 tlsv1.1 or tlsv1

    # MQTT publish options: All options influencing the MQTT related behaviour
    'mqtt-topic':               'powerline/',          # Topic prefix to be used for subscribing/publishing. Defaults to "modbus/"
    'mqtt-value-qos':           0,                  # QoS value for publishing values. Defaults to 0
    'retain-values':            False,              # Set retain flag for published modbus values.

    # Misc options
    'add-to-homeassistant':     False,              # Add devices to Home Assistant using Home Assistant\'s MQTT-Discovery
    'hass-discovery-prefix':    'homeassistant',    # Add devices to Home Assistant using Home Assistant\'s MQTT-Discovery
    'verbosity':                'info',             # Verbosity level ('debug', 'info', 'warning', 'error', 'critical')
}
