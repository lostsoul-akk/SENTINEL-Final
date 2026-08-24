"""
Sentinel X — fake ESP32 publisher (Phase 0 test rig)

Stands in for both real ESP32 boards so the rest of the pipeline can be
built and tested before hardware/firmware exists. Publishes plausible
JSON on the same topics the real boards will use.

Run this in one terminal, run main.py in another, and you should see
main.py print live "sensor" data and occasional events.

    python fake_esp32.py
    python fake_esp32.py --scenario intrusion   # scripted THREAT sequence
"""

import argparse
import json
import random
import time

import paho.mqtt.client as mqtt

from topics import (
    TOPIC_ESP32_1_STATUS,
    TOPIC_ESP32_2_STATUS,
    TOPIC_EVENT,
)

BROKER_HOST = "localhost"
BROKER_PORT = 1883


def publish(client, topic, payload):
    body = json.dumps(payload)
    client.publish(topic, body, qos=1)
    print(f"[fake_esp32] -> {topic}  {body}")


def run_idle_loop(client):
    """Steady stream of plausible periodic readings, occasional random events."""
    while True:
        esp32_2_payload = {
            "temperature": round(22 + random.uniform(-1.5, 3.5), 1),
            "humidity": round(50 + random.uniform(-8, 20), 1),
            "water": 0,
            "sound": random.randint(5, 20),
            "pir": 0,
            "ultrasonic_cm": round(random.uniform(80, 200), 1),
        }
        publish(client, TOPIC_ESP32_2_STATUS, esp32_2_payload)

        esp32_1_payload = {"rfid": "idle", "keypad": "idle", "display": "Ready"}
        publish(client, TOPIC_ESP32_1_STATUS, esp32_1_payload)

        # Occasionally fire a harmless single-sensor blip (should -> WARNING later)
        if random.random() < 0.15:
            publish(client, TOPIC_EVENT, {"type": "sound_spike", "sensor": "sound"})

        time.sleep(3)


def run_intrusion_scenario(client):
    """Scripted sequence matching the docs' 'unauthorized approach' example."""
    print("[fake_esp32] Running scripted intrusion scenario in 3s...")
    time.sleep(3)

    publish(client, TOPIC_ESP32_2_STATUS, {"pir": 1, "ultrasonic_cm": 45.0})
    publish(client, TOPIC_EVENT, {"type": "intrusion", "sensor": "PIR"})
    time.sleep(1)

    publish(client, TOPIC_ESP32_2_STATUS, {"sound": 78})
    publish(client, TOPIC_EVENT, {"type": "intrusion", "sensor": "sound"})
    time.sleep(1)

    publish(client, TOPIC_ESP32_1_STATUS, {"rfid": "unknown_card", "keypad": "idle", "display": "Access Denied"})
    publish(client, TOPIC_EVENT, {"type": "auth_fail", "method": "rfid"})

    print("[fake_esp32] Scenario complete. Expect THREAT-level response from Python.")


def run_humidity_scenario(client):
    """One high-humidity reading, then a return to normal, to exercise
    the environmental automation OPEN_WINDOW/CLOSE_WINDOW rule."""
    print("[fake_esp32] Running humidity scenario in 3s...")
    time.sleep(3)

    publish(client, TOPIC_ESP32_2_STATUS, {"humidity": 82.0, "temperature": 23.0})
    print("[fake_esp32] High humidity sent. Expect OPEN_WINDOW if mode=HOME.")
    time.sleep(4)

    publish(client, TOPIC_ESP32_2_STATUS, {"humidity": 55.0, "temperature": 22.5})
    print("[fake_esp32] Humidity back to normal. Expect CLOSE_WINDOW if window was OPEN.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=["idle", "intrusion", "humidity"],
        default="idle",
        help="idle = steady background stream; intrusion = one scripted THREAT sequence; "
             "humidity = one high-humidity reading then a return to normal",
    )
    args = parser.parse_args()

    client = mqtt.Client(
        client_id="fake-esp32-rig",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    client.loop_start()

    try:
        if args.scenario == "intrusion":
            run_intrusion_scenario(client)
            time.sleep(2)
        elif args.scenario == "humidity":
            run_humidity_scenario(client)
            time.sleep(2)
        else:
            run_idle_loop(client)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
