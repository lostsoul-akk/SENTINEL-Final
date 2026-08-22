# Sentinel X — Commit Log (Person 2 / PC-side)

Suggested commits, in order. Stage the matching files for each and commit
separately rather than one giant commit — keeps history readable and makes
it easy to bisect later if something in threat.py needs rolling back.

---

### 1. Project scaffolding
```
git add requirements.txt topics.py
git commit -m "chore: scaffold Python project and define MQTT topic contract

- requirements.txt with paho-mqtt, customtkinter, opencv-python,
  face_recognition, pillow
- topics.py as single source of truth for MQTT topic names, matching
  Revision 2 docs (dual-ESP32, esp32_1/esp32_2 status + event + command
  topics, consolidated system/status)"
```

### 2. MQTT client core
```
git add mqtt_client.py
git commit -m "feat: add SentinelMQTTClient wrapping paho-mqtt

- Runs network loop on its own thread (loop_start), never blocks caller
- Auto-subscribes to esp32_1/esp32_2 status + event topics on connect
- JSON parse with malformed-payload protection (logs and drops, doesn't crash)
- Publish helpers for esp32_1/esp32_2 commands and consolidated system status"
```

### 3. System state model
```
git add state.py
git commit -m "feat: add SystemState as shared app state

- Mirrors the sentinelx/system/status payload shape (system_state, mode,
  door, window, sensor readings, threat_level)
- Thread-safe via internal lock (mutated from MQTT thread, read from
  dashboard/main thread)
- to_status_payload() / snapshot() for publishing and debug output"
```

### 4. Fake ESP32 test rig
```
git add fake_esp32.py
git commit -m "test: add fake_esp32.py hardware simulator

- idle scenario: steady periodic sensor stream + occasional sound_spike
- intrusion scenario: scripted PIR -> sound -> failed RFID sequence
  matching Section 7 (unauthorized approach) of the docs
- Lets the whole PC-side pipeline be built and tested before real
  ESP32 firmware/hardware exists"
```

### 5. Phase 1 smoke test
```
git add main.py
git commit -m "feat: wire up main.py entry point, confirm MQTT round-trip

- Connects SentinelMQTTClient, routes messages into SystemState
- Verified end-to-end against fake_esp32.py on a local Mosquitto broker
  (idle stream + scripted intrusion scenario both received correctly)"
```

### 6. Event logger
```
git add logger.py .gitignore
git commit -m "feat: add EventLogger for JSON-lines event logging

- Appends timestamped entries to data/events.jsonl (sensor events,
  threat-level changes, commands sent)
- read_recent() for the dashboard's event history view
- .gitignore excludes venv/, __pycache__, and logged data (*.jsonl)"
```

### 7. Threat analysis
```
git add threat.py
git commit -m "feat: implement threat analysis per docs Section 10

- SAFE / WARNING / THREAT levels based on correlating distinct sensor
  signals within an 8s window (single signal -> WARNING, 2+ -> THREAT)
- Gated on arming state: no auto-escalation while DISARMED
- THREAT triggers LOCK_DOOR / CLOSE_WINDOW / SOUND_ALARM commands and
  updates door/window state
- decay_check() relaxes level back toward SAFE once signals age out
- Verified: PIR alone -> WARNING, PIR + sound -> THREAT, idle traffic
  stays SAFE (no false positives)"
```

### 8. Wire threat analysis into main.py
```
git add main.py
git commit -m "feat: integrate ThreatAnalyzer and EventLogger into main.py

- sentinelx/event messages now route through ThreatAnalyzer instead of
  just being logged
- Periodic decay_check() polled every 2s from the main loop
- system_state hardcoded to ARMED for now, pending Phase 5 dashboard
  arm/disarm control"
```

### 9. Environmental automation
```
git add environment.py main.py fake_esp32.py
git commit -m "feat: add environmental automation per docs Section 8

- EnvironmentalController: humidity > 70% AND mode=HOME -> OPEN_WINDOW
- Hysteresis (threshold - 5%) before auto-closing, to avoid rapid toggling
- AWAY mode never auto-opens regardless of humidity (security > comfort
  when unoccupied) — verified with a direct unit test
- Runs independently of threat/security flow, triggered only by DHT11
  humidity on esp32_2/status
- fake_esp32.py: added --scenario humidity for end-to-end testing
- main.py: hooks EnvironmentalController.evaluate() into esp32_2 status
  updates that include humidity; hardcodes mode=HOME alongside
  system_state=ARMED for tonight's testing"
```

### 10. CustomTkinter dashboard
```
git add dashboard.py main.py
git commit -m "feat: add CustomTkinter dashboard

- Status bar: broker connection, armed state, mode, door, color-coded
  threat level (green/amber/red)
- Sensor panel: live temperature/humidity/water/sound/PIR/ultrasonic/
  window/RFID/keypad/display readouts
- Manual controls: toggle arm/disarm, toggle Home/Away, lock/unlock door
  — dashboard is authoritative for these per the docs
- Event history panel reading from EventLogger.read_recent()
- Polling refresh via .after() every 1s (reads SystemState.snapshot()
  from the GUI thread only) instead of a cross-thread queue — safe
  since SystemState is lock-protected
- main.py: launches the dashboard by default, --headless flag keeps
  the old console-only mode
- Verified under Xvfb against live MQTT traffic: window renders
  correctly, threat level updates live (SAFE -> WARNING -> decay back
  to SAFE observed), no exceptions on launch/close. Manual override
  handler logic (arm toggle, unlock door) verified directly."
```

---

## Going forward

For every future working session, follow the same pattern: one commit per
feature/module, imperative mood subject line ("feat: add X" not "added X"),
a blank line, then bullet points on what changed and what was verified.
I'll draft the commit message alongside each piece of code from here on,
matching this format, so you can just copy-paste and commit as we go.
