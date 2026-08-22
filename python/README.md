# Sentinel X — Person 2 PC-Side Code

Tested and working against a local Mosquitto broker.

## Files
- `topics.py` — single source of truth for MQTT topic names/contract
- `mqtt_client.py` — `SentinelMQTTClient`, runs on its own thread, connects/subscribes/publishes
- `state.py` — `SystemState`, the shared object the rest of the app reads/writes
- `logger.py` — `EventLogger`, appends JSON-lines events to `data/events.jsonl`
- `threat.py` — `ThreatAnalyzer`, SAFE/WARNING/THREAT correlation logic (docs Section 10)
- `environment.py` — `EnvironmentalController`, humidity/Home-mode auto-window rule (docs Section 8)
- `fake_esp32.py` — stand-in for both real ESP32 boards, so you can build everything before hardware exists
- `main.py` — entry point tying it all together

## Setup

```bash
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You also need a local MQTT broker. On Arch:

```bash
sudo pacman -S mosquitto
sudo systemctl start mosquitto
# or run it in the foreground for dev:
mosquitto -v
```

## Run it

Terminal 1 — start the fake hardware:
```bash
python fake_esp32.py --scenario idle
```

Terminal 2 — start the Python brain:
```bash
python main.py
```

You should see `main.py` log incoming sensor updates every ~3s and an
occasional `sound_spike` event.

To test the scripted "unauthorized approach" sequence from the docs instead:
```bash
python fake_esp32.py --scenario intrusion
```
This fires PIR -> sound -> failed RFID in sequence, matching Section 7 of
the Revision 2 documentation. Watch the threat level escalate SAFE -> WARNING -> THREAT.

To test environmental automation:
```bash
python fake_esp32.py --scenario humidity
```
Sends one high-humidity reading then a return to normal. With `mode=HOME`,
watch the window state flip OPEN then back to CLOSED.

## What's confirmed working
- Broker connect/subscribe/reconnect handling
- JSON parsing with malformed-payload protection
- `SystemState` updates from both esp32_1 and esp32_2 status topics
- Command publish helpers (`publish_command_esp32_1/2`, `publish_system_status`)
- **Threat analysis (Section 10):** single ambiguous signal → WARNING;
  2+ distinct sensor signals within an 8s correlation window → THREAT;
  THREAT triggers `LOCK_DOOR` / `CLOSE_WINDOW` / `SOUND_ALARM` commands
  and updates `door`/`window` state. Verified against `fake_esp32.py --scenario intrusion`
  (PIR alone → WARNING, PIR + sound → THREAT) and against the idle stream
  (routine traffic stays SAFE, no false escalation).
- Threat level decays back toward SAFE once no new signals arrive within
  the window (`ThreatAnalyzer.decay_check()`, polled every 2s from `main.py`).
- **Event logging:** every sensor event, threat-level change, and command
  sent gets appended to `data/events.jsonl` (JSON-lines, one entry per line).
- **Environmental automation (Section 8):** `humidity > 70%` AND `mode == HOME`
  → `OPEN_WINDOW`; humidity dropping back below `threshold - 5%` → `CLOSE_WINDOW`
  (hysteresis avoids rapid toggling at the threshold). `mode == AWAY` never
  auto-opens regardless of humidity — verified with a direct unit test.
  Runs independently of the security/threat flow, triggered only by DHT11
  humidity readings on `esp32_2/status`.
- Note: `main.py` currently hardcodes `state.system_state = "ARMED"` and
  `state.mode = "HOME"` for testing — real arm/disarm and mode control
  lands on the dashboard in Phase 5.

## Next (Phase 5 onward)
- CustomTkinter dashboard wired to `SystemState` + `EventLogger.read_recent()`
- Camera + face recognition module
- Attach latest webcam capture to THREAT-level alerts (see TODO in `threat.py`)
