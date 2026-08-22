"""
Sentinel X — MQTT client core (Phase 1)

Wraps paho-mqtt so the rest of the app never touches the broker directly.
Runs the network loop on its own background thread (loop_start), and hands
parsed JSON payloads to the app via a plain callback — never blocks the GUI.

Usage:
    from mqtt_client import SentinelMQTTClient

    def on_message(topic, payload: dict):
        print(topic, payload)

    client = SentinelMQTTClient(on_message=on_message)
    client.connect()
    ...
    client.publish_command_esp32_2({"command": "UNLOCK_DOOR"})
    ...
    client.disconnect()
"""

import json
import logging
import threading
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from topics import (
    SUBSCRIBE_TOPICS,
    TOPIC_COMMAND_ESP32_1,
    TOPIC_COMMAND_ESP32_2,
    TOPIC_SYSTEM_STATUS,
)

logger = logging.getLogger("sentinelx.mqtt")


class SentinelMQTTClient:
    def __init__(
        self,
        on_message: Callable[[str, dict], None],
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "sentinelx-python-brain",
        on_connect_change: Optional[Callable[[bool], None]] = None,
    ):
        """
        on_message: callback(topic: str, payload: dict) fired for every
                    message on a subscribed topic, once JSON-parsed.
        on_connect_change: optional callback(is_connected: bool), useful
                    for surfacing broker connection state on the dashboard.
        """
        self._on_message_cb = on_message
        self._on_connect_change_cb = on_connect_change
        self._lock = threading.Lock()
        self._connected = False

        self.client = mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.on_connect = self._handle_connect
        self.client.on_disconnect = self._handle_disconnect
        self.client.on_message = self._handle_message

        self._host = broker_host
        self._port = broker_port

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def connect(self):
        logger.info("Connecting to broker %s:%s", self._host, self._port)
        self.client.connect(self._host, self._port, keepalive=30)
        self.client.loop_start()  # background thread — never blocks caller

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    # ------------------------------------------------------------------ #
    # paho callbacks (run on the paho network thread)
    # ------------------------------------------------------------------ #

    def _handle_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("Connected to broker.")
            with self._lock:
                self._connected = True
            for topic in SUBSCRIBE_TOPICS:
                client.subscribe(topic, qos=1)
                logger.info("Subscribed: %s", topic)
        else:
            logger.error("Broker connection failed: %s", reason_code)
            with self._lock:
                self._connected = False

        if self._on_connect_change_cb:
            self._on_connect_change_cb(self._connected)

    def _handle_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.warning("Disconnected from broker: %s", reason_code)
        with self._lock:
            self._connected = False
        if self._on_connect_change_cb:
            self._on_connect_change_cb(False)
        # paho auto-reconnects by default when loop_start() is used with
        # a positive reconnect_delay; if not, reconnect() could be called
        # here on a timer instead.

    def _handle_message(self, client, userdata, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Malformed JSON on %s: %r", msg.topic, raw)
            return

        try:
            self._on_message_cb(msg.topic, payload)
        except Exception:
            # A bug in app-level handling should never kill the MQTT thread.
            logger.exception("Error in on_message handler for %s", msg.topic)

    # ------------------------------------------------------------------ #
    # Publish helpers — the only way the rest of the app talks to hardware
    # ------------------------------------------------------------------ #

    def _publish_json(self, topic: str, payload: dict, qos: int = 1):
        body = json.dumps(payload)
        result = self.client.publish(topic, body, qos=qos)
        logger.debug("Published %s -> %s (rc=%s)", topic, body, result.rc)
        return result

    def publish_command_esp32_1(self, payload: dict):
        """e.g. {"command": "SHOW_MESSAGE", "text": "Enter PIN"}"""
        return self._publish_json(TOPIC_COMMAND_ESP32_1, payload)

    def publish_command_esp32_2(self, payload: dict):
        """e.g. {"command": "UNLOCK_DOOR"} or {"command": "OPEN_WINDOW"}"""
        return self._publish_json(TOPIC_COMMAND_ESP32_2, payload)

    def publish_system_status(self, payload: dict):
        """Consolidated periodic report Python sends to the dashboard/log/listeners."""
        return self._publish_json(TOPIC_SYSTEM_STATUS, payload, qos=0)
