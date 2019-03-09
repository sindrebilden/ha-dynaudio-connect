"""
Support for Dynaudio Connect

Based on the API documentation found here:
https://github.com/therealmuffin/Dynaudio-connect-api
"""

import logging
import math
import socket

import voluptuous as vol

from homeassistant.components.media_player import (
  MediaPlayerDevice, PLATFORM_SCHEMA)
from homeassistant.components.media_player.const import (
  SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_SELECT_SOURCE,
  SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET)
from homeassistant.const import (
  CONF_HOST, CONF_NAME, CONF_PORT, STATE_OFF, STATE_ON)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Dynaudio"
DEFAULT_PORT = 1901

SUPPORT_DYNAUDIO = SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
  SUPPORT_TURN_ON | SUPPORT_TURN_OFF | SUPPORT_SELECT_SOURCE

MAX_VOLUME = 31

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
  """Set up the Dynaudio platform."""
  dynaudio = DynaudioDevice(
    config.get(CONF_NAME), config.get(CONF_HOST), config.get(CONF_PORT))

  if dynaudio.update():
    add_entities([dynaudio])

class DynaudioDevice(MediaPlayerDevice):
  """Representation of a Dynaudio device."""

  def __init__(self, name, host, port):
    """Initialize the Dynaudio device."""
    self._name = name
    self._host = host
    self._port = port
    self._zone = "1"
    self._pwstate = False
    self._volume = 0
    self._muted = False
    self._selected_source = ""
    self._source_name_to_number = {"Minijack": 1, "Line": 2, "Optical": 3, "Coax": 4, "USB": 5, "Bluetooth": 6, "Stream": 7}
    self._source_number_to_name = {1: "Minijack", 2: "Line", 3: "Optical", 4: "Coax", 5: "USB", 6: "Bluetooth", 7: "Stream"}

  def calculate_checksum(self, payload):
    """Calculate the checksum for the complete command"""
    hexarray = payload.split(" ")
    sum = 0
    for num in hexarray:
        sum += int(num, 16)
    x = math.ceil(sum / 255)
    checksum = x * 255 - sum - (len(hexarray) - x)
    return hex(checksum & 255)[2:]

  def construct_command(self, payload):
    """Construct full command"""
    prefix = "FF 55"
    payload_size = str(len(payload.split(" "))).zfill(2)
    checksum = self.calculate_checksum(payload)
    return prefix + " " + payload_size + " " + payload + " " + checksum

  def socket_command(self, payload):
    """Establish a socket connection and sends command"""
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((self._host, self._port))
        hex_data = bytes.fromhex(self.construct_command(payload))
        s.send(hex_data)
    except (ConnectionRefusedError, OSError):
      _LOGGER.warning("Dynaudio %s refused connection", self._name)
      return

  def update(self):
    """Update device status"""
    # TODO 1: refactor code to reuse functions
    # TODO 2: find proper feedback command to avoid hacky code
    """Hacky: send command to green zone, to receive feedback."""
    """Assuming green zone is not in use"""
    command = "FF 55 05 2F A0 12 00 72 A8"
    received = ""
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        s.connect((self._host, self._port))
        hex_data = bytes.fromhex(command)
        s.send(hex_data)
        received = s.recv(1024)
    except (ConnectionRefusedError, OSError):
      _LOGGER.warning("Dynaudio %s refused connection", self._name)
    _LOGGER.warning("Received "+repr(received))
    if received == "":
      """If we receive nothing, the Connect is turned off"""
      self._pwstate=False
    else:
      self._pwstate=received[6] #hypothesis, cannot test at this moment
      self._volume=received[7]
      self._selected_source=self._source_number_to_name[received[8]]
      self._zone=received[9] #hypothesis, cannot test at this moment
      self._mute=received[10]
    return True

  @property
  def name(self):
    """Return the name of the device."""
    return self._name

  @property
  def state(self):
    """Return the state of the device."""
    if self._pwstate:
      return STATE_ON
    else:
      return STATE_OFF

  @property
  def volume_level(self):
    """Volume level of the media player (0..1)."""
    return self._volume

  @property
  def is_volume_muted(self):
    """Boolean if volume is currently muted."""
    return self._muted

  @property
  def supported_features(self):
    """Flag media player features that are supported."""
    return SUPPORT_DYNAUDIO

  @property
  def source(self):
    """Return the current input source."""
    return self._selected_source

  @property
  def source_list(self):
    """List of available input sources."""
    return list(self._source_name_to_number.keys())

  def turn_off(self):
    """Turn off media player."""
    self.socket_command("2F A0 02 01 F" + str(self._zone))

  def turn_on(self):
    """Turn the media player on."""
    self.socket_command("2F A0 01 00 F" + str(self._zone))

  def set_volume_level(self, volume):
    """Set volume level, range 0..1."""
    # 60dB max
    self.socket_command(
      "2F A0 13 " + 
      str(hex(round(volume * MAX_VOLUME))[2:]).zfill(2) + 
      " 5" + self._zone)

  def mute_volume(self, mute):
    """Mute (true) or unmute (false) media player."""
    self.socket_command("2F A0 12 01 5" + str(self._zone))

  def select_source(self, source):
    """Select input source."""
    self.socket_command(
      "2F A0 15 " +
      self._source_name_to_number.get(source) +
      " 5" + self._zone)
