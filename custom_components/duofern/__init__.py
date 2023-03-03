import logging
import os
import re
import time

# from homeassistant.const import 'serial_port', 'config_file', 'code'
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from pyduofern.duofern_stick import DuofernStickThreaded

# found advice in the homeassistant creating components manual
# https://home-assistant.io/developers/creating_components/
# Import the device class from the component that you want to support

# Home Assistant depends on 3rd party packages for API specific code.
REQUIREMENTS = ['pyduofern==0.34.1']

_LOGGER = logging.getLogger(__name__)

from .const import DOMAIN, DUOFERN_COMPONENTS, CONF_SERIAL_PORT, CONF_CODE

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({
    vol.Optional('serial_port',
                 default="/dev/serial/by-id/usb-Rademacher_DuoFern_USB-Stick_WR04ZFP4-if00-port0"): cv.string,
    vol.Optional('config_file', default=os.path.join(os.path.dirname(__file__), "../../duofern.json")): cv.string,
    # config file: default to homeassistant config directory (assuming this is a custom component)
    vol.Optional('code', default="0000"): cv.string,
}),
}, extra=vol.ALLOW_EXTRA)


def setup(hass: HomeAssistant, config: ConfigType):
    """Setup the Awesome Light platform."""

    # Assign configuration variables. The configuration check takes care they are
    # present.


    newstyle_config_entries = hass.config_entries.async_entries(DOMAIN)
    if len(newstyle_config_entries) > 0:
        newstyle_config = newstyle_config_entries[0]
        if newstyle_config:
            serial_port = newstyle_config.data['serial_port']
            code = newstyle_config.data['code']
            configfile = newstyle_config.data['config_file']

    elif config.get(DOMAIN) is not None:
        serial_port = config[DOMAIN].get(CONF_SERIAL_PORT)
        if serial_port is None:
            serial_port = "/dev/serial/by-id/usb-Rademacher_DuoFern_USB-Stick_WR04ZFP4-if00-port0"
        code = config[DOMAIN].get(CONF_CODE, None)
        if code is None:
            code = "affe"
        configfile = config[DOMAIN].get('config_file')

    hass.data[DOMAIN] = {
        'stick': DuofernStickThreaded(serial_port=serial_port, system_code=code, config_file_json=configfile,
                                      ephemeral=False),
        'devices': {}}

    # Setup connection with devices/cloud
    stick = hass.data[DOMAIN]['stick']

    _registerServices(hass, stick, config)
        
    def refresh(call):
        _LOGGER.warning(call)
        for _component in DUOFERN_COMPONENTS:
            discovery.load_platform(hass, _component, DOMAIN, {}, config)

    for _component in DUOFERN_COMPONENTS:
        discovery.load_platform(hass, _component, DOMAIN, {}, config)

    def update_callback(id, key, value):
        if id is not None:
            try:
                _LOGGER.info(f"Updatecallback for {id}")
                device = hass.data[DOMAIN]['devices'][id] # Get device by id
                if device.enabled:
                    try:
                        device.schedule_update_ha_state(True) # Trigger update on the updated entity
                    except AssertionError:
                        _LOGGER.info("Update callback called before HA is ready") # Trying to update before HA is ready
            except KeyError:
                _LOGGER.info("Update callback called on unknown device id") # Ignore invalid device ids

    stick.add_updates_callback(update_callback)

    def started_callback(event):
        stick.start() # Start the stick when ha is ready
    
    hass.bus.listen("homeassistant_started", started_callback)

    return True

def _registerServices(hass: HomeAssistant, stick: DuofernStickThreaded, config: ConfigType) -> None:
    def start_pairing(call: ServiceCall) -> None:
        _LOGGER.warning("start pairing")
        hass.data[DOMAIN]['stick'].pair(call.data.get('timeout', 60))

    def start_unpairing(call: ServiceCall) -> None:
        _LOGGER.warning("start pairing")
        hass.data[DOMAIN]['stick'].unpair(call.data.get('timeout', 60))

    def sync_devices(call: ServiceCall) -> None:
        stick.sync_devices()
        _LOGGER.warning(call)
        for _component in DUOFERN_COMPONENTS:
            discovery.load_platform(hass, _component, DOMAIN, {}, config)

    def dump_device_state(call: ServiceCall) -> None:
        _LOGGER.warning(hass.data[DOMAIN]['stick'].duofern_parser.modules)

    def clean_config(call: ServiceCall) -> None:
        stick.clean_config()
        stick.sync_devices()

    def ask_for_update(call: ServiceCall) -> None:
        try:
            hass_device_id = call.data.get('device_id', None)
            device_id = re.sub(r"[^\.]*.([0-9a-fA-F]+)", "\\1", hass_device_id) if hass_device_id is not None else None
        except Exception:
            _LOGGER.exception(f"exception while getting device id {call}, {call.data}")
            raise
        if device_id is None:
            _LOGGER.warning(f"device_id missing from call {call.data}")
            return
        if device_id not in hass.data[DOMAIN]['stick'].duofern_parser.modules['by_code']:
            _LOGGER.warning(f"{device_id} is not a valid duofern device, I only know {hass.data[DOMAIN]['stick'].duofern_parser.modules['by_code'].keys()}")
            return
        hass.data[DOMAIN]['stick'].command(device_id, 'getStatus')

    PAIRING_SCHEMA = vol.Schema({
        vol.Optional('timeout', default=30): cv.positive_int,
    })

    UPDATE_SCHEMA = vol.Schema({
        vol.Required('device_id', default=None): cv.string,
    })

    hass.services.register(DOMAIN, 'start_pairing', start_pairing, PAIRING_SCHEMA)
    hass.services.register(DOMAIN, 'start_unpairing', start_unpairing, PAIRING_SCHEMA)
    hass.services.register(DOMAIN, 'sync_devices', sync_devices)
    hass.services.register(DOMAIN, 'clean_config', clean_config)
    hass.services.register(DOMAIN, 'dump_device_state', dump_device_state)
    hass.services.register(DOMAIN, 'ask_for_update', ask_for_update, UPDATE_SCHEMA)


async def async_setup_entry(hass, entry):
    return True
