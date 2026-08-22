"""
Sentinel X — central system state (Phase 2 groundwork)

One object every other module reads/writes. Shape mirrors the
sentinelx/system/status payload described in the docs, so publishing
that report later is just: json.dumps(state.to_status_payload()).

Kept deliberately minimal tonight — just enough for the Phase 1 MQTT
test to have somewhere real to put incoming sensor data. Threat rules,
mode logic, etc. land in Phase 3/4.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SystemState:
    # Arming / occupancy (Section 9 of the docs)
    system_state: str = "DISARMED"     # "ARMED" | "DISARMED"
    mode: str = "AWAY"                 # "HOME" | "AWAY"

    # Physical state
    door: str = "LOCKED"               # "LOCKED" | "UNLOCKED"
    window: str = "CLOSED"             # "CLOSED" | "OPEN"

    # Latest sensor readings (from esp32_2/status)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    water: Optional[int] = None
    sound: Optional[int] = None
    pir: Optional[int] = None
    ultrasonic_cm: Optional[float] = None

    # Latest interaction state (from esp32_1/status)
    rfid: str = "idle"
    keypad: str = "idle"
    display: str = "Ready"

    # Threat analysis (Phase 3)
    threat_level: str = "SAFE"         # "SAFE" | "WARNING" | "THREAT"

    # Connectivity
    broker_connected: bool = False

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def update_from_esp32_2(self, payload: dict):
        with self._lock:
            for key in ("temperature", "humidity", "water", "sound", "pir", "ultrasonic_cm"):
                if key in payload:
                    setattr(self, key, payload[key])

    def update_from_esp32_1(self, payload: dict):
        with self._lock:
            for key in ("rfid", "keypad", "display"):
                if key in payload:
                    setattr(self, key, payload[key])

    def to_status_payload(self) -> dict:
        with self._lock:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_state": self.system_state,
                "mode": self.mode,
                "temperature": self.temperature,
                "humidity": self.humidity,
                "door": self.door,
                "window": self.window,
                "threat_level": self.threat_level,
            }

    def snapshot(self) -> dict:
        """Full state as a plain dict, e.g. for the dashboard or debug printing."""
        with self._lock:
            return {
                "system_state": self.system_state,
                "mode": self.mode,
                "door": self.door,
                "window": self.window,
                "temperature": self.temperature,
                "humidity": self.humidity,
                "water": self.water,
                "sound": self.sound,
                "pir": self.pir,
                "ultrasonic_cm": self.ultrasonic_cm,
                "rfid": self.rfid,
                "keypad": self.keypad,
                "display": self.display,
                "threat_level": self.threat_level,
                "broker_connected": self.broker_connected,
            }
