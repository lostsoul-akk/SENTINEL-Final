"""
Sentinel X — environmental automation (Phase 4)

Implements Section 8 of the docs:

    If humidity exceeds the configured threshold AND the system is in
    Home mode (someone is present), Python automatically commands
    ESP32 #2 to open the window.

    If nobody is home (Away mode), the window is never opened
    automatically for environmental reasons, regardless of humidity —
    security takes priority over comfort when the property is unoccupied.

This runs independently of the security/authentication flow — it is not
triggered by motion, only by continuous DHT11 readings.
"""

import logging

from mqtt_client import SentinelMQTTClient
from state import SystemState

logger = logging.getLogger("sentinelx.environment")

DEFAULT_HUMIDITY_THRESHOLD = 70.0  # percent — tune once real sensor behaviour is known
# Hysteresis gap so we don't rapidly toggle OPEN/CLOSE around the threshold.
CLOSE_HYSTERESIS = 5.0


class EnvironmentalController:
    def __init__(
        self,
        state: SystemState,
        mqtt_client: SentinelMQTTClient,
        humidity_threshold: float = DEFAULT_HUMIDITY_THRESHOLD,
    ):
        self._state = state
        self._mqtt = mqtt_client
        self._threshold = humidity_threshold

    def evaluate(self):
        """Call this after every esp32_2 status update that includes humidity."""
        humidity = self._state.humidity
        if humidity is None:
            return

        if self._state.mode != "HOME":
            # Away mode: never auto-open, regardless of humidity.
            # If the window happens to already be open when mode flips to
            # Away, leave that to the security/threat logic, not this rule.
            return

        if humidity > self._threshold and self._state.window == "CLOSED":
            logger.info(
                "Humidity %.1f%% > threshold %.1f%% in HOME mode — opening window",
                humidity, self._threshold,
            )
            self._mqtt.publish_command_esp32_2({"command": "OPEN_WINDOW"})
            self._state.window = "OPEN"

        elif humidity < (self._threshold - CLOSE_HYSTERESIS) and self._state.window == "OPEN":
            logger.info(
                "Humidity %.1f%% back below threshold — closing window",
                humidity,
            )
            self._mqtt.publish_command_esp32_2({"command": "CLOSE_WINDOW"})
            self._state.window = "CLOSED"
