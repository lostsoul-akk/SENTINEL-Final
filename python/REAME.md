# Sentinel X — Person 2 PC-Side Code

Tested and working against a local Mosquitto broker.

## Files
- `topics.py` — single source of truth for MQTT topic names/contract
- `mqtt_client.py` — `SentinelMQTTClient`, runs on its own thread, connects/subscribes/publishes
- `state.py` — `SystemState`, the shared object the rest of the app reads/writes
- `logger.py` — `EventLogger`, appends JSON-lines events to `data/events.jsonl`
- `threat.py` — `ThreatAnalyzer`, SAFE/WARNING/THREAT correlation logic (docs Section 10)
- `environment.py` — `EnvironmentalController`, humidity/Home-mode auto-window rule (docs Section 8)
- `camera.py` — `VideoStream`, real webcam or fake test-image cycling
- `face_engine.py` — `FaceEngine`, enrollment + recognition (wraps OpenCV Haar Cascade + `cv2.face.LBPHFaceRecognizer`)
- `auth_engine.py` — `AuthEngine`, continuous-surveillance face auth + keypad PIN as the manual alternative (PIR/RFID removed — see `STATUS_AND_PIVOT.md`)
- `enroll_faces.py` — interactive CLI for enrolling a person via webcam
- `dashboard.py` — the CustomTkinter GUI, including manual PIN entry for demoing without a physical keypad
- `fake_esp32.py` — stand-in for both real ESP32 boards, so you can build everything before hardware exists
- `main.py` — entry point tying it all together

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

### Face recognition dependency note

Face recognition uses **`opencv-contrib-python`**, not plain `opencv-python`
— the base package doesn't include `cv2.face`, which the LBPH recognizer
needs. If you see `AttributeError: module 'cv2' has no attribute
'CascadeClassifier'`, you almost certainly have both `opencv-python` and a
headless/contrib variant installed at once, corrupting the `cv2` namespace.
Fix:

```bash
pip uninstall opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless -y
pip install opencv-contrib-python
```

This is a normal, fast prebuilt-wheel install — no C++ compile involved,
unlike `dlib` (which this version no longer uses at all).

### Enrollment is required before recognition works

`face_engine.py` treats a missing `people.txt` as "nobody enrolled yet,"
even if a `face_model.yml` happens to exist on disk — an inherited model
with no label mapping is unusable. Run `enroll_faces.py` (see below)
before expecting any face to be recognized.

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

## Enrolling people

```bash
python enroll_faces.py --name yourname --samples 12
```

Walks you through a batch of shots (different expressions/angles/lighting,
per Section 7's guidance) via your webcam — SPACE to capture each prompt,
ESC to stop early. Saves `face_model.yml` + `people.txt` in `python/`,
which `main.py` loads automatically on startup. Re-running this for
someone new adds them via incremental training — it doesn't wipe out
people already enrolled.

## Manual PIN (backup / demo without a keypad)

If ESP32 #1's physical keypad isn't wired up yet, the dashboard's "Face
Auth + Keypad" panel has a manual PIN entry field that goes through the
exact same `AuthEngine.on_keypad_pin_entered()` path a real keypad event
would. Placeholder PIN is set in `auth_engine.py` (`CORRECT_PIN`) — change
it to whatever you want to demo with.

## Testing without a camera

```bash
python main.py --fake-camera-dir test_fixtures/fake_camera
```

Cycles through the bundled test images instead of opening a real webcam —
useful for testing continuous surveillance and the keypad path without a
face in frame or any camera hardware attached at all.

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
  override buttons (arm/disarm, Home/Away, lock/unlock door), a Face Auth
  panel, and a scrolling event history pulled from `EventLogger.read_recent()`.
  Uses a simple polling refresh (`.after()` every 1s) rather than a
  cross-thread queue — safe because `SystemState` is lock-protected and
  the dashboard only ever reads a snapshot from the GUI thread.
  Verified visually under Xvfb against live MQTT traffic (see
  `dashboard_preview.png`) and the manual-override handler logic was
  verified directly (arm toggle, unlock door → command published +
  state updated + event logged).
- **Camera + face recognition (Section 7, primary path):**
  - `camera.py`: `VideoStream` wraps a real webcam OR a directory of test
    images cycled on a timer (`--fake-camera-dir`), same "fake hardware"
    pattern as `fake_esp32.py`, so the whole pipeline is testable without
    physical hardware.
  - `face_engine.py`: `FaceEngine` wraps the `face_recognition` library —
    enrollment (`enroll_from_images`) stores one or more encodings per
    person in `data/faces/encodings.pkl`; `recognize()` returns the best
    match within tolerance, or `None` if nobody matches or no face was
    detected.
  - `auth_engine.py`: `AuthEngine.on_pir_triggered()` — triggered on a PIR
    rising edge from `esp32_2/status` — grabs the current frame and runs
    recognition. Match → `UNLOCK_DOOR` published, `auth_success` logged.
    No match → photo captured to `data/captures/`, `auth_fail` logged with
    the image path (shown on the dashboard's Face Auth panel). A 5s
    cooldown prevents re-triggering while someone lingers in frame.
  - `enroll_faces.py`: interactive CLI for enrolling a real person against
    a real webcam — walks through a batch of prompts (different
    expressions/poses/angles per Section 7's guidance) rather than just
    one photo.
  - **Verified:** `VideoStream`'s fake-camera frame cycling (distinct
    frames correctly rotated); `AuthEngine`'s full flow end-to-end with a
    mocked recognizer — successful match → door unlocked + command
    published + logged; cooldown correctly suppresses PIR spam; failed
    match → door stays locked, a real photo gets saved to disk, and it's
    logged with a valid `image_path`. Full stack (dashboard + camera +
    auth engine + threat + environment, all wired together, driven by
    live MQTT traffic) confirmed working end-to-end under Xvfb — see
    `dashboard_preview_phase6.png`, which shows a real captured "failed
    match" photo rendered in the dashboard's Face Auth panel.
  - **Note:** `face_recognition`/`dlib` weren't buildable in the sandbox
    used to develop this (no prebuilt wheel, and compiling from source
    exceeded the sandbox's time limits) — but your `pip install -r
    requirements.txt` already confirmed `dlib==20.0.1` built successfully
    on your machine, so the real (non-mocked) recognizer just needs
    testing there. Only `FaceEngine.recognize()`'s *return value* was
    mocked in these tests; everything calling it is real, unmocked code.

## Next (Phase 7 onward)
- Full auth engine: wire the RFID + PIN manual override (the other half
  of Section 7) using ESP32 #1's raw RFID/keypad events — see the TODO
  at the bottom of `auth_engine.py`
- Attach latest webcam capture to THREAT-level alerts too, not just
  failed face matches (see TODO in `threat.py`)
