"""
Sentinel X — authentication engine (revised: continuous surveillance, no PIR/RFID)

Per tonight's pivot: PIR and RFID are removed from this version. The camera
runs continuous surveillance instead of waking on a motion sensor, and the
manual override is keypad PIN entry instead of RFID+PIN.

    Continuous camera loop -> face recognition attempted every few seconds
        match     -> access granted
        no match  -> capture photo, log for review; door stays locked until
                     either a later face match succeeds, or someone enters
                     the correct PIN on the keypad (on_keypad_pin_entered)

Runs recognition on a background thread so a slow face-recognition pass
never blocks the MQTT thread or the dashboard's UI thread.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone

from camera import VideoStream
from face_engine import FaceEngine
from logger import EventLogger
from mqtt_client import SentinelMQTTClient
from state import SystemState

logger = logging.getLogger("sentinelx.auth")

CAPTURES_DIR = os.path.join(os.path.dirname(__file__), "data", "captures")

# How often continuous surveillance attempts a fresh recognition pass.
SURVEILLANCE_INTERVAL_SECONDS = 4.0

# Don't log/act on a fresh failed-match capture more often than this, so a
# person standing in frame doesn't spam the event log every interval.
FAILED_MATCH_LOG_COOLDOWN_SECONDS = 15.0

# Placeholder until Person 1 confirms ESP32 #1's real keypad message
# contract. For now: correct PIN is configured here directly.
CORRECT_PIN = "1234"


class AuthEngine:
    def __init__(
        self,
        state: SystemState,
        mqtt_client: SentinelMQTTClient,
        event_logger: EventLogger,
        video_stream: VideoStream,
        face_engine: FaceEngine,
    ):
        self._state = state
        self._mqtt = mqtt_client
        self._events = event_logger
        self._video = video_stream
        self._face = face_engine
        self._last_failed_log_time = 0.0
        self._busy = threading.Lock()
        self._running = False
        self._thread = None

    # ------------------------------------------------------------------ #
    # Continuous surveillance (replaces PIR-triggered recognition)
    # ------------------------------------------------------------------ #

    def start_surveillance(self):
        """Begin continuous face-recognition surveillance on a background
        thread. Call once, at app startup."""
        self._running = True
        self._thread = threading.Thread(target=self._surveillance_loop, daemon=True)
        self._thread.start()
        logger.info("Continuous surveillance started (interval=%.1fs)", SURVEILLANCE_INTERVAL_SECONDS)

    def stop_surveillance(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _surveillance_loop(self):
        while self._running:
            if not self._busy.locked():
                self._run_recognition_attempt()
            time.sleep(SURVEILLANCE_INTERVAL_SECONDS)

    def _run_recognition_attempt(self):
        with self._busy:
            frame = self._video.get_frame()
            if frame is None:
                return  # no camera feed yet, nothing to do this pass

            name, distance = self._face.recognize(frame)

            if name is not None:
                self._grant_access(name, distance)
            else:
                self._handle_failed_match(frame, distance)

    # ------------------------------------------------------------------ #
    # Keypad PIN entry (manual alternative to face recognition)
    # ------------------------------------------------------------------ #

    def on_keypad_pin_entered(self, pin: str):
        """Call this when ESP32 #1 reports a completed PIN entry (or, for
        tonight's demo, when the dashboard's manual PIN field is submitted)."""
        if pin == CORRECT_PIN:
            logger.info("Correct PIN entered — granting access")
            self._mqtt.publish_command_esp32_2({"command": "UNLOCK_DOOR"})
            self._state.door = "UNLOCKED"
            self._events.log_event("auth_success", {"method": "keypad"})
        else:
            logger.warning("Incorrect PIN entered — access denied")
            self._events.log_event("auth_fail", {"method": "keypad", "reason": "incorrect_pin"})

    # ------------------------------------------------------------------ #
    # Shared grant/deny handling
    # ------------------------------------------------------------------ #

    def _grant_access(self, name: str, distance: float):
        logger.info("Face match: %s (distance=%.3f) — granting access", name, distance)
        self._mqtt.publish_command_esp32_2({"command": "UNLOCK_DOOR"})
        self._state.door = "UNLOCKED"
        self._events.log_event(
            "auth_success",
            {"method": "face", "name": name, "distance": round(distance, 4)},
        )

    def _handle_failed_match(self, frame, distance):
        now = time.time()
        if now - self._last_failed_log_time < FAILED_MATCH_LOG_COOLDOWN_SECONDS:
            return  # someone's still standing in frame, don't spam the log
        self._last_failed_log_time = now

        reason = "no_face_detected" if distance is None else "no_match_within_tolerance"
        logger.warning("Face recognition failed (%s) — capturing photo for review", reason)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        image_path = os.path.join(CAPTURES_DIR, f"auth_fail_{timestamp}.jpg")
        os.makedirs(CAPTURES_DIR, exist_ok=True)

        import cv2
        cv2.imwrite(image_path, frame)

        self._events.log_event(
            "auth_fail",
            {
                "method": "face",
                "reason": reason,
                "distance": None if distance is None else round(distance, 4),
            },
            image_path=image_path,
        )
