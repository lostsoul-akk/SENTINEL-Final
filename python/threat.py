"""
Sentinel X — threat analysis (Phase 3)

Implements Section 10 of the docs: multiple sensor sources are combined
so a single ambiguous reading doesn't trigger a false alarm on its own.

    SAFE     — normal operation, no action beyond logging
    WARNING  — one ambiguous signal (e.g. sound spike, no PIR) — logged
               and flagged on the dashboard, no automatic lockdown
    THREAT   — corroborated signals (2+ distinct sensor sources within
               the correlation window), or arming is Active and a clear
               intrusion pattern is detected — door/window locked/closed,
               buzzer sounds, alert + latest capture pushed to dashboard

Arming state (Section 9) gates automatic response: if the system is
Inactive (disarmed), sensors keep reporting and events keep getting
logged, but Python will not raise alarms or trigger lockdown from them.
"""

import logging
import threading
import time
from collections import deque
from typing import Optional

from logger import EventLogger
from mqtt_client import SentinelMQTTClient
from state import SystemState

logger = logging.getLogger("sentinelx.threat")

# How long a signal stays "in play" for corroboration purposes.
CORRELATION_WINDOW_SECONDS = 8.0

# Event types/sensors that count as intrusion-relevant signals.
# Keyed loosely: we look at payload["sensor"] first, falling back to payload["type"].
RELEVANT_EVENT_TYPES = {
    "intrusion",
    "auth_fail",
    "sound_spike",
    "water_detected",
}


class ThreatAnalyzer:
    def __init__(
        self,
        state: SystemState,
        mqtt_client: SentinelMQTTClient,
        event_logger: EventLogger,
        window_seconds: float = CORRELATION_WINDOW_SECONDS,
    ):
        self._state = state
        self._mqtt = mqtt_client
        self._events = event_logger
        self._window = window_seconds
        self._lock = threading.Lock()
        # deque of (timestamp, signal_key)
        self._recent_signals: deque = deque()

    # ------------------------------------------------------------------ #
    # Public entry point — call this for every message on sentinelx/event
    # ------------------------------------------------------------------ #

    def handle_event(self, payload: dict):
        signal_key = payload.get("sensor") or payload.get("type") or "unknown"
        event_type = payload.get("type", "unknown")

        self._events.log_event("sensor_event", payload)

        if event_type not in RELEVANT_EVENT_TYPES and payload.get("sensor") is None:
            # Not something threat analysis cares about (e.g. routine status).
            return

        now = time.time()
        with self._lock:
            self._recent_signals.append((now, signal_key))
            self._prune(now)
            distinct_signals = {key for _, key in self._recent_signals}
            new_level = self._evaluate(distinct_signals)

        self._apply_level(new_level, distinct_signals, payload)

    def decay_check(self):
        """Call periodically (e.g. every few seconds from main loop) so the
        threat level relaxes back down once no new signals have arrived."""
        now = time.time()
        with self._lock:
            self._prune(now)
            distinct_signals = {key for _, key in self._recent_signals}
            new_level = self._evaluate(distinct_signals)
        self._apply_level(new_level, distinct_signals, reason={"source": "decay_check"})

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _prune(self, now: float):
        while self._recent_signals and now - self._recent_signals[0][0] > self._window:
            self._recent_signals.popleft()

    def _evaluate(self, distinct_signals: set) -> str:
        if self._state.system_state != "ARMED":
            # Disarmed: sensors still report, but no automatic escalation.
            return "SAFE"

        if len(distinct_signals) >= 2:
            return "THREAT"
        elif len(distinct_signals) == 1:
            return "WARNING"
        return "SAFE"

    def _apply_level(self, new_level: str, distinct_signals: set, reason: dict):
        if new_level == self._state.threat_level:
            return  # no change, nothing to do

        old_level = self._state.threat_level
        self._state.threat_level = new_level
        logger.warning("Threat level: %s -> %s (signals=%s)", old_level, new_level, distinct_signals)
        self._events.log_event(
            "threat_level_change",
            {"from": old_level, "to": new_level, "signals": list(distinct_signals), "reason": reason},
        )

        if new_level == "THREAT":
            self._respond_threat()

    def _respond_threat(self):
        """Section 10: THREAT -> lock door, close & lock window, sound buzzer,
        push alert (+ latest capture, once Phase 6 wires the camera in)."""
        self._mqtt.publish_command_esp32_2({"command": "LOCK_DOOR"})
        self._mqtt.publish_command_esp32_2({"command": "CLOSE_WINDOW"})
        self._mqtt.publish_command_esp32_2({"command": "SOUND_ALARM"})

        self._state.door = "LOCKED"
        self._state.window = "CLOSED"

        self._events.log_event("command_sent", {"commands": ["LOCK_DOOR", "CLOSE_WINDOW", "SOUND_ALARM"]})
        # TODO Phase 6: attach latest webcam capture path to this alert.
