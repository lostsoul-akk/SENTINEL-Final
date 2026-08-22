"""
Sentinel X — Phase 1 entry point / smoke test

Tonight's goal: prove the MQTT client connects, subscribes, receives
JSON from fake_esp32.py, and updates SystemState correctly.

Run:
    Terminal 1: python fake_esp32.py
    Terminal 2: python main.py
"""

import logging
import time

from logger import EventLogger
from mqtt_client import SentinelMQTTClient
from state import SystemState
from threat import ThreatAnalyzer
from topics import TOPIC_ESP32_1_STATUS, TOPIC_ESP32_2_STATUS, TOPIC_EVENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinelx.main")

state = SystemState()
event_logger = EventLogger()

# For tonight's manual testing: start ARMED so the intrusion scenario
# actually exercises the THREAT path. Real arm/disarm control lands
# on the dashboard in Phase 5.
state.system_state = "ARMED"

mqtt_client: SentinelMQTTClient  # assigned in main(), referenced by on_message
threat_analyzer: ThreatAnalyzer


def on_message(topic: str, payload: dict):
    if topic == TOPIC_ESP32_2_STATUS:
        state.update_from_esp32_2(payload)
        logger.info("esp32_2 status update: %s", payload)
    elif topic == TOPIC_ESP32_1_STATUS:
        state.update_from_esp32_1(payload)
        logger.info("esp32_1 status update: %s", payload)
    elif topic == TOPIC_EVENT:
        logger.warning("EVENT: %s", payload)
        threat_analyzer.handle_event(payload)
    else:
        logger.debug("Unhandled topic %s: %s", topic, payload)


def on_connect_change(connected: bool):
    state.broker_connected = connected
    logger.info("Broker connection state: %s", connected)


def main():
    global mqtt_client, threat_analyzer

    mqtt_client = SentinelMQTTClient(
        on_message=on_message,
        on_connect_change=on_connect_change,
    )
    threat_analyzer = ThreatAnalyzer(state, mqtt_client, event_logger)

    mqtt_client.connect()

    logger.info("Listening for MQTT traffic (system_state=%s). Ctrl+C to stop.", state.system_state)
    try:
        elapsed = 0
        while True:
            time.sleep(2)
            elapsed += 2
            threat_analyzer.decay_check()
            if elapsed % 10 == 0:
                logger.info("Current state snapshot: %s", state.snapshot())
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
