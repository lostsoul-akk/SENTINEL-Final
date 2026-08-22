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
the Revision 2 documentation. `main.py` should log all three events.

## What's confirmed working
- Broker connect/subscribe/reconnect handling
- JSON parsing with malformed-payload protection
- `SystemState` updates from both esp32_1 and esp32_2 status topics
- Event topic logging
- Command publish helpers (`publish_command_esp32_1/2`, `publish_system_status`)

## Next (Phase 2 onward)
- Flesh out threat analysis rules in a new `threat.py` (SAFE/WARNING/THREAT per Section 10)
- Event logger to JSON-lines/SQLite
- Environmental automation rule (humidity + Home mode -> OPEN_WINDOW)
- CustomTkinter dashboard wired to `SystemState`
- Camera + face recognition module
