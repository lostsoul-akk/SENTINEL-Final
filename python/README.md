# Sentinel X — Person 2 PC-Side Code (Phase 0 + Phase 1)

Tested and working tonight against a local Mosquitto broker.

## Files
- `topics.py` — single source of truth for MQTT topic names/contract
- `mqtt_client.py` — `SentinelMQTTClient`, runs on its own thread, connects/subscribes/publishes
- `state.py` — `SystemState`, the shared object the rest of the app reads/writes
- `fake_esp32.py` — stand-in for both real ESP32 boards, so you can build everything before hardware exists
- `main.py` — Phase 1 smoke test tying it all together

## Setup

```bash
python3 -m venv venv --system-site-packages
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Note the `--system-site-packages` flag** — `customtkinter` needs Tkinter,
which ships with your system Python (`python3-tk` on Debian/Ubuntu/Arch's
`python` package) but is *not* installable via pip into an isolated venv.
Without that flag you'll get `ModuleNotFoundError: No module named 'tkinter'`
even though `pip install customtkinter` succeeds. On Arch, tkinter comes
with the base `python` package, so this should already be available — but
recreate your venv with the flag above if you hit that error.

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

Terminal 2 — start the Python brain (launches the dashboard by default):
```bash
python main.py
# or, console-only, no GUI:
python main.py --headless
```

You should see the dashboard window open with live sensor values, an
armed/mode/door/threat status bar, manual override buttons, and a
scrolling event history.

To test the scripted "unauthorized approach" sequence from the docs instead:
```bash
python fake_esp32.py --scenario intrusion
```
This fires PIR -> sound -> failed RFID in sequence, matching Section 7 of
the Revision 2 documentation. Watch the dashboard's threat level go
SAFE -> WARNING -> THREAT and the door/window lock/close automatically.

To test environmental automation:
```bash
python fake_esp32.py --scenario humidity
```
Sends one high-humidity reading then a return to normal. With the
dashboard in Home mode (the default on startup), watch the window state
flip OPEN then back to CLOSED.

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
- **Dashboard (CustomTkinter):** status bar (broker connection, armed state,
  mode, door, color-coded threat level), live sensor readouts, manual
  override buttons (arm/disarm, Home/Away, lock/unlock door), and a
  scrolling event history pulled from `EventLogger.read_recent()`.
  Uses a simple polling refresh (`.after()` every 1s) rather than a
  cross-thread queue — safe because `SystemState` is lock-protected and
  the dashboard only ever reads a snapshot from the GUI thread.
  Verified visually under Xvfb against live MQTT traffic (see
  `dashboard_preview.png`) and the manual-override handler logic was
  verified directly (arm toggle, unlock door → command published +
  state updated + event logged).
- `main.py` now launches the dashboard by default; `--headless` keeps the
  old console-only Phase 1-4 mode for quick debugging without a GUI.

## Next (Phase 6 onward)
- Camera + face recognition module
- Attach latest webcam capture to THREAT-level alerts (see TODO in `threat.py`)
- Wire the auth engine (PIR → face check → RFID+PIN override) per Section 7
