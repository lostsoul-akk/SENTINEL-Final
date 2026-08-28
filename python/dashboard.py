"""
Sentinel X — dashboard (Phase 5)

CustomTkinter GUI. Deliberately simple architecture: no cross-thread
widget mutation. The MQTT client runs on its own background thread and
only ever touches SystemState (which is lock-protected); this window
polls SystemState.snapshot() on a Tkinter `.after()` timer and updates
labels from the main/GUI thread only. That sidesteps Tkinter's
not-thread-safe rule without needing a queue.

Manual override buttons here are the dashboard's authority over
arm/disarm and Home/Away mode, per the docs ("System mode and
arming-state management" is owned by Python / the dashboard).
"""

import logging
from typing import Optional

import customtkinter as ctk
from PIL import Image

from environment import EnvironmentalController
from logger import EventLogger
from mqtt_client import SentinelMQTTClient
from state import SystemState
from threat import ThreatAnalyzer

logger = logging.getLogger("sentinelx.dashboard")

REFRESH_MS = 1000  # UI + threat decay_check tick
EVENT_LOG_ROWS = 12

THREAT_COLORS = {
    "SAFE": "#2fa84f",
    "WARNING": "#d9a441",
    "THREAT": "#d9432f",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SentinelDashboard(ctk.CTk):
    def __init__(
        self,
        state: SystemState,
        mqtt_client: SentinelMQTTClient,
        event_logger: EventLogger,
        threat_analyzer: ThreatAnalyzer,
        environmental_controller: EnvironmentalController,
        video_stream=None,
        auth_engine=None,
    ):
        super().__init__()

        self._state = state
        self._mqtt = mqtt_client
        self._events = event_logger
        self._threat = threat_analyzer
        self._environment = environmental_controller
        self._video = video_stream
        self._auth = auth_engine
        self._last_shown_auth_ts = None

        self.title("Sentinel X — Dashboard")
        self.geometry("900x680")
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_status_panel()
        self._build_sensor_panel()
        self._build_controls_panel()
        self._build_face_auth_panel()
        self._build_event_log_panel()

        self.after(REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def _build_status_panel(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        for i in range(5):
            frame.grid_columnconfigure(i, weight=1)

        self.lbl_connection = ctk.CTkLabel(frame, text="Broker: —", font=("", 14, "bold"))
        self.lbl_connection.grid(row=0, column=0, padx=8, pady=8)

        self.lbl_armed = ctk.CTkLabel(frame, text="ARMED: —", font=("", 14, "bold"))
        self.lbl_armed.grid(row=0, column=1, padx=8, pady=8)

        self.lbl_mode = ctk.CTkLabel(frame, text="Mode: —", font=("", 14, "bold"))
        self.lbl_mode.grid(row=0, column=2, padx=8, pady=8)

        self.lbl_door = ctk.CTkLabel(frame, text="Door: —", font=("", 14, "bold"))
        self.lbl_door.grid(row=0, column=3, padx=8, pady=8)

        self.lbl_threat = ctk.CTkLabel(frame, text="THREAT LEVEL: —", font=("", 16, "bold"))
        self.lbl_threat.grid(row=0, column=4, padx=8, pady=8)

    def _build_sensor_panel(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        ctk.CTkLabel(frame, text="Sensors", font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        self.sensor_labels = {}
        for key, display in [
            ("temperature", "Temperature (°C)"),
            ("humidity", "Humidity (%)"),
            ("water", "Water"),
            ("sound", "Sound"),
            ("pir", "PIR"),
            ("ultrasonic_cm", "Ultrasonic (cm)"),
            ("window", "Window"),
            ("rfid", "RFID"),
            ("keypad", "Keypad"),
            ("display", "Panel Display"),
        ]:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=display, width=140, anchor="w").pack(side="left")
            value_lbl = ctk.CTkLabel(row, text="—", anchor="w")
            value_lbl.pack(side="left")
            self.sensor_labels[key] = value_lbl

    def _build_controls_panel(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=6)
        ctk.CTkLabel(frame, text="Manual Controls", font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        self.btn_arm = ctk.CTkButton(frame, text="Toggle Arm/Disarm", command=self._toggle_arm)
        self.btn_arm.pack(fill="x", padx=10, pady=4)

        self.btn_mode = ctk.CTkButton(frame, text="Toggle Home/Away", command=self._toggle_mode)
        self.btn_mode.pack(fill="x", padx=10, pady=4)

        self.btn_lock = ctk.CTkButton(frame, text="Lock Door", command=self._lock_door)
        self.btn_lock.pack(fill="x", padx=10, pady=4)

        self.btn_unlock = ctk.CTkButton(frame, text="Unlock Door", command=self._unlock_door)
        self.btn_unlock.pack(fill="x", padx=10, pady=4)

    def _build_face_auth_panel(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Face Auth + Keypad", font=("", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4)
        )

        self.auth_thumbnail_label = ctk.CTkLabel(frame, text="No captures yet", width=160, height=120)
        self.auth_thumbnail_label.grid(row=1, column=0, padx=10, pady=(0, 10))

        self.auth_status_label = ctk.CTkLabel(
            frame, text="Continuous surveillance running...", anchor="w", justify="left", wraplength=600,
        )
        self.auth_status_label.grid(row=1, column=1, sticky="nw", padx=10, pady=(0, 10))

        pin_row = ctk.CTkFrame(frame, fg_color="transparent")
        pin_row.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        ctk.CTkLabel(pin_row, text="Manual PIN entry (demo/backup):").pack(side="left", padx=(0, 8))
        self.pin_entry = ctk.CTkEntry(pin_row, width=100, show="*")
        self.pin_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(pin_row, text="Submit", width=80, command=self._submit_pin).pack(side="left")
        self.pin_entry.bind("<Return>", lambda event: self._submit_pin())

    def _submit_pin(self):
        pin = self.pin_entry.get().strip()
        self.pin_entry.delete(0, "end")
        if not pin:
            return
        if self._auth is not None:
            self._auth.on_keypad_pin_entered(pin)
        else:
            logger.warning("PIN submitted but auth engine isn't available")

    def _build_event_log_panel(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=12, pady=(6, 12))
        self.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(frame, text="Event History", font=("", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 4))

        self.event_box = ctk.CTkTextbox(frame, height=150)
        self.event_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.event_box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Manual override handlers — dashboard is authoritative for these
    # ------------------------------------------------------------------ #

    def _toggle_arm(self):
        new_state = "DISARMED" if self._state.system_state == "ARMED" else "ARMED"
        self._state.system_state = new_state
        self._events.log_event("manual_override", {"action": "arm_toggle", "to": new_state})
        logger.info("Manual override: system_state -> %s", new_state)

    def _toggle_mode(self):
        new_mode = "AWAY" if self._state.mode == "HOME" else "HOME"
        self._state.mode = new_mode
        self._events.log_event("manual_override", {"action": "mode_toggle", "to": new_mode})
        logger.info("Manual override: mode -> %s", new_mode)

    def _lock_door(self):
        self._mqtt.publish_command_esp32_2({"command": "LOCK_DOOR"})
        self._state.door = "LOCKED"
        self._events.log_event("manual_override", {"action": "lock_door"})
        logger.info("Manual override: LOCK_DOOR sent")

    def _unlock_door(self):
        self._mqtt.publish_command_esp32_2({"command": "UNLOCK_DOOR"})
        self._state.door = "UNLOCKED"
        self._events.log_event("manual_override", {"action": "unlock_door"})
        logger.info("Manual override: UNLOCK_DOOR sent")

    # ------------------------------------------------------------------ #
    # Refresh loop
    # ------------------------------------------------------------------ #

    def _tick(self):
        snapshot = self._state.snapshot()
        self._render(snapshot)
        self._threat.decay_check()
        self._refresh_face_auth_panel()
        self.after(REFRESH_MS, self._tick)

    def _render(self, snapshot: dict):
        self.lbl_connection.configure(
            text=f"Broker: {'Connected' if snapshot['broker_connected'] else 'Disconnected'}"
        )
        self.lbl_armed.configure(text=f"ARMED: {snapshot['system_state']}")
        self.lbl_mode.configure(text=f"Mode: {snapshot['mode']}")
        self.lbl_door.configure(text=f"Door: {snapshot['door']}")

        threat = snapshot["threat_level"]
        self.lbl_threat.configure(
            text=f"THREAT LEVEL: {threat}",
            text_color=THREAT_COLORS.get(threat, "#ffffff"),
        )

        for key, label in self.sensor_labels.items():
            value = snapshot.get(key)
            label.configure(text="—" if value is None else str(value))

        self._refresh_event_log()

    def _refresh_event_log(self):
        recent = self._events.read_recent(limit=EVENT_LOG_ROWS)
        lines = []
        for entry in recent:
            ts = entry.get("timestamp", "")[11:19]  # HH:MM:SS
            lines.append(f"[{ts}] {entry.get('category')}: {entry.get('detail')}")
        text = "\n".join(lines) if lines else "(no events yet)"

        self.event_box.configure(state="normal")
        self.event_box.delete("1.0", "end")
        self.event_box.insert("end", text)
        self.event_box.configure(state="disabled")

    def _refresh_face_auth_panel(self):
        recent = self._events.read_recent(limit=30)
        auth_events = [e for e in recent if e.get("category") in ("auth_success", "auth_fail")]
        if not auth_events:
            return

        latest = auth_events[-1]
        ts = latest.get("timestamp")
        if ts == self._last_shown_auth_ts:
            return  # already showing this one, nothing new
        self._last_shown_auth_ts = ts

        detail = latest.get("detail", {})
        method = detail.get("method", "?")
        if latest["category"] == "auth_success":
            if method == "face":
                text = f"✅ Access granted — face match: {detail.get('name')} (distance {detail.get('distance')}) at {ts[11:19]}"
            else:
                text = f"✅ Access granted — correct PIN entered at {ts[11:19]}"
            self.auth_status_label.configure(text=text, text_color=THREAT_COLORS["SAFE"])
            self.auth_thumbnail_label.configure(image=None, text="(match, no capture needed)")
        else:
            if method == "face":
                reason = detail.get("reason", "unknown")
                text = f"⚠️ Face not recognized ({reason}) at {ts[11:19]} — try again or enter PIN"
            else:
                text = f"⚠️ Incorrect PIN entered at {ts[11:19]}"
            self.auth_status_label.configure(text=text, text_color=THREAT_COLORS["WARNING"])
            image_path = latest.get("image_path")
            if image_path:
                try:
                    pil_image = Image.open(image_path)
                    pil_image.thumbnail((160, 120))
                    ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=pil_image.size)
                    self.auth_thumbnail_label.configure(image=ctk_image, text="")
                except Exception:
                    logger.exception("Could not load auth_fail capture: %s", image_path)
