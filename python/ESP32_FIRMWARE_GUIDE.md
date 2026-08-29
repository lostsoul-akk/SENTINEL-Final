# ESP32 Firmware — Build & Flash Guide

Two boards, two sketches. Both have been **compiled successfully against
the real ESP32 toolchain** (arduino-cli, `esp32:esp32:esp32` target,
esp32 core 2.0.9) — this isn't just written-and-hoped code. What hasn't
been verified is behavior on actual hardware — no physical ESP32 was
available to flash and test against. Follow the staged testing steps
below rather than flashing both boards fully wired and hoping.

| Board | File | Job |
|---|---|---|
| ESP32 #1 (Auth & UI) | `esp32_1_auth/esp32_1_auth.ino` | Reads the keypad, sends PIN entries, shows granted/denied feedback |
| ESP32 #2 (Sensors & Actuators) | `esp32_2_actuators/esp32_2_actuators.ino` | Drives the door lock servo on command |

Both implement `PIN_ENTRY_CONTRACT.md` and `topics.py` exactly — message
shapes are not guesses.

---

## 1. Arduino IDE Setup (one-time)

1. Install the [Arduino IDE](https://www.arduino.cc/en/software) (2.x recommended).
2. File → Preferences → Additional Board Manager URLs, add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Tools → Board → Boards Manager, search "esp32", install the **esp32 by
   Espressif Systems** package (this guide was built/tested against
   version 2.0.9).
4. Tools → Board, select your actual board (commonly "ESP32 Dev Module"
   if using a generic dev board).

## 2. Install Required Libraries

Sketch → Include Library → Manage Libraries, install:

| Library | Author | Needed by |
|---|---|---|
| PubSubClient | Nick O'Leary | both |
| ArduinoJson | Benoit Blanchon (v6 or v7) | both |
| Keypad | Mark Stanley / Alexander Brevig | ESP32 #1 |
| ESP32Servo | Kevin Harrington / madhephaestus | ESP32 #2 |
| DHT sensor library | Adafruit | ESP32 #2, **only if** you enable `HAS_DHT11` |
| Adafruit Unified Sensor | Adafruit | same, dependency of the DHT library |

`WiFi` and `Preferences` are bundled with the ESP32 board package — no
separate install needed.

## 3. Wiring — Adjust Pin Numbers to Match Reality

The pin numbers in both sketches (`KEYPAD_ROW_PINS`, `KEYPAD_COL_PINS`,
`SERVO_PIN`, etc.) are placeholders based on commonly-free ESP32 GPIOs.
**Check them against your actual wiring before flashing** — if your
keypad or servo is already wired per the original hardware docs' pin
map, use those pin numbers instead of the ones in the sketch.

- 4x4 keypad: 8 GPIOs total (4 rows + 4 columns), wired directly — no
  MCP23017 I/O expander in this simplified version, to keep wiring easy
  under time pressure. If you already have the expander wired, that's a
  bigger change to the sketch — flag it and we can adjust.
- Door lock servo: one PWM-capable GPIO, plus its own power supply (see
  the original docs' Section 12 power precautions — **never power a
  servo from the ESP32's own 3.3V/5V rail**, use the external supply).

## 4. First Boot — Network Configuration

Neither sketch has a hardcoded Wi-Fi SSID or broker IP. On first boot
(or after typing `reset` at the Serial prompt), each board asks for:

```
Wi-Fi SSID:
Wi-Fi Password:
MQTT Broker IP (LAN IP of the PC running Mosquitto):
```

Answers are saved to flash (ESP32 `Preferences`) and reused on every
future boot — no reflashing needed to switch networks (home tonight →
venue tomorrow). To reconfigure: reset the board, and within 3 seconds
of the reset, type `reset` in Serial Monitor and press Enter.

**Find the broker PC's LAN IP** (not `localhost` — the ESP32 is a
different device on the network):
```bash
hostname -I        # Linux
ipconfig            # Windows, look for IPv4 Address
ifconfig            # macOS
```

**Make sure Mosquitto is actually reachable from other devices first** —
follow `mosquitto-network-setup.md` completely, including the
`mosquitto_sub`/`mosquitto_pub` test from a second device, before
assuming the ESP32 will be able to connect. If that test doesn't pass,
no firmware fix will make the ESP32 connect either.

## 5. Flashing

1. Connect the ESP32 via USB.
2. Tools → Port, select the ESP32's serial port.
3. Open the correct `.ino` file for the board you're flashing — Arduino
   IDE requires the sketch folder name to match the `.ino` filename
   (already set up correctly in this delivery: `esp32_1_auth/esp32_1_auth.ino`,
   `esp32_2_actuators/esp32_2_actuators.ino`).
4. Click Upload.
5. Open Serial Monitor at **115200 baud** immediately after — you'll
   need it for the first-boot config prompts.

## 6. Staged Testing — Don't Flash-and-Hope

Verify each layer before trusting the next one:

1. **Wi-Fi connects** — Serial Monitor prints the board's IP address.
2. **MQTT connects** — Serial Monitor prints "connected" and the
   subscribed topic.
3. **Keypad input reaches the broker** (ESP32 #1) — from the PC:
   ```bash
   mosquitto_sub -h <broker-ip> -t 'sentinelx/#' -v
   ```
   Press digits + `#` on the keypad, confirm the `keypad_pin` message
   appears with the right digits.
4. **Manually trigger the door lock** (ESP32 #2), *before* wiring up the
   full auth flow — from the PC:
   ```bash
   mosquitto_pub -h <broker-ip> -t sentinelx/command/esp32_2 -m '{"command":"UNLOCK_DOOR"}'
   ```
   Confirm the servo physically moves to the unlocked position. If the
   angle is wrong (locks instead of unlocking, or doesn't move far
   enough), adjust `SERVO_LOCKED_ANGLE`/`SERVO_UNLOCKED_ANGLE` in the
   sketch and reflash before moving on.
5. **Manually trigger an auth result display** (ESP32 #1):
   ```bash
   mosquitto_pub -h <broker-ip> -t sentinelx/command/esp32_1 -m '{"command":"auth_result","method":"pin","result":"granted","display":"TEST"}'
   ```
   Confirm Serial (and LEDs, if `HAS_STATUS_LEDS` is enabled) show it correctly.
6. **Full round trip** — with `main.py` running on the PC and both ESP32s
   flashed and connected, enter the real PIN (`3234`) on the physical
   keypad and confirm the door actually unlocks, end to end.

## 7. Optional Hardware

Both sketches work with zero optional hardware — keypad + door lock only.
To enable extras, uncomment the relevant `#define` near the top of the
file and reflash:

| Flag | Board | Adds |
|---|---|---|
| `HAS_STATUS_LEDS` | ESP32 #1 | Granted/denied LED feedback alongside Serial |
| `HAS_BUZZER` | ESP32 #2 | Buzzer sounds on `SOUND_ALARM` command |
| `HAS_DHT11` | ESP32 #2 | Publishes temperature/humidity every 10s, feeding `environment.py`'s automation |

Each combination (including both ESP32 #2 flags together) has been
compiled successfully — not just written.

## 8. What's Deliberately Not Handled

- **RFID and PIR**: removed from this version's scope entirely — no code
  paths reference them.
- **Window motor**: `CLOSE_WINDOW` commands are received and logged but
  ignored — no window hardware in this version.
- **LCD/OLED display**: original hardware docs specced one, but it's not
  wired into either sketch — Serial (and optional LEDs) carry all
  feedback for now. Straightforward to add later using the same
  `I2C` bus described in the original docs, following the pattern
  already used for `HAS_STATUS_LEDS`.
- **Auth lockout** (`auth_lockout` command): implemented on the ESP32 #1
  receiving side, but nothing on the PC side currently sends it —
  `auth_engine.py` would need a failed-attempt counter added to trigger
  it. Marked optional/not-required-for-demo in the contract doc.

## 9. If Something Doesn't Compile

Both sketches were verified against these exact library versions:

```
PubSubClient        2.8
ArduinoJson          7.4.2
Keypad               3.1.1
ESP32Servo           3.2.1
DHT sensor library   1.4.7   (only if HAS_DHT11 enabled)
Adafruit Unified Sensor  1.1.15  (same)
esp32 board package  2.0.9
```

If Library Manager installs a newer major version and something breaks,
try pinning to these versions first before debugging further — API
changes between major versions are the most common cause of sketches
that used to compile suddenly not doing so.
