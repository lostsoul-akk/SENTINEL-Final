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

from mqtt_client import SentinelMQTTClient
from state import SystemState
from topics import TOPIC_ESP32_1_STATUS, TOPIC_ESP32_2_STATUS, TOPIC_EVENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinelx.main")

state = SystemState()


def on_message(topic: str, payload: dict):
    if topic == TOPIC_ESP32_2_STATUS:
        state.update_from_esp32_2(payload)
        logger.info("esp32_2 status update: %s", payload)
    elif topic == TOPIC_ESP32_1_STATUS:
        state.update_from_esp32_1(payload)
        logger.info("esp32_1 status update: %s", payload)
    elif topic == TOPIC_EVENT:
        logger.warning("EVENT: %s", payload)
        # Phase 3 will route this into threat analysis; tonight we just log it.
    else:
        logger.debug("Unhandled topic %s: %s", topic, payload)


def on_connect_change(connected: bool):
    state.broker_connected = connected
    logger.info("Broker connection state: %s", connected)


def main():
    client = SentinelMQTTClient(
        on_message=on_message,
        on_connect_change=on_connect_change,
    )
    client.connect()

    logger.info("Listening for MQTT traffic. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(10)
            logger.info("Current state snapshot: %s", state.snapshot())
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
