"""
Sentinel X — entry point (Phase 5: dashboard)

Run:
    Terminal 1: python fake_esp32.py
    Terminal 2: python main.py            # launches the dashboard
    Terminal 2: python main.py --headless # old Phase 1-4 console-only mode
"""

import argparse
import logging
import threading
import time

from auth_engine import AuthEngine
from camera import VideoStream
from environment import EnvironmentalController
from face_engine import FaceEngine
from logger import EventLogger
from mqtt_client import SentinelMQTTClient
from state import SystemState
from threat import ThreatAnalyzer
from topics import TOPIC_ESP32_1_STATUS, TOPIC_ESP32_2_STATUS, TOPIC_EVENT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinelx.main")

state = SystemState()
event_logger = EventLogger()

# For tonight's manual testing: start ARMED + HOME so both the threat path
# and the environmental automation path are exercisable. Real mode/arming
# control lands on the dashboard in Phase 5.
state.system_state = "ARMED"
state.mode = "HOME"

mqtt_client: SentinelMQTTClient  # assigned in main(), referenced by on_message
threat_analyzer: ThreatAnalyzer
environmental_controller: EnvironmentalController
auth_engine: AuthEngine = None  # may stay None if no camera is available

# How often to publish a full system-status snapshot (sentinelx/system/status)
# so the dashboard and any other listener see fresh values even between
# esp32 status updates or triggered events.
STATUS_PUBLISH_INTERVAL_SECONDS = 5.0
_status_publish_running = False
_status_publish_thread: threading.Thread = None


def on_message(topic: str, payload: dict):
    if topic == TOPIC_ESP32_2_STATUS:
        state.update_from_esp32_2(payload)
        logger.info("esp32_2 status update: %s", payload)
        if "humidity" in payload:
            environmental_controller.evaluate()
    elif topic == TOPIC_ESP32_1_STATUS:
        state.update_from_esp32_1(payload)
        logger.info("esp32_1 status update: %s", payload)
        # Keypad PIN entry contract (see PIN_ENTRY_CONTRACT.md): ESP32 #1
        # publishes {"type": "keypad_pin", "pin": "..."} once, after Enter
        # is pressed — this is a discrete submission, not a live-typing
        # field, so no need to compare against a previous value.
        if payload.get("type") == "keypad_pin" and auth_engine is not None:
            auth_engine.on_keypad_pin_entered(payload.get("pin", ""))
    elif topic == TOPIC_EVENT:
        logger.warning("EVENT: %s", payload)
        threat_analyzer.handle_event(payload)
    else:
        logger.debug("Unhandled topic %s: %s", topic, payload)


def on_connect_change(connected: bool):
    state.broker_connected = connected
    logger.info("Broker connection state: %s", connected)


def _status_publish_loop():
    while _status_publish_running:
        if mqtt_client.is_connected:
            mqtt_client.publish_system_status(state.to_status_payload())
        time.sleep(STATUS_PUBLISH_INTERVAL_SECONDS)


def main():
    global mqtt_client, threat_analyzer, environmental_controller, auth_engine
    global _status_publish_running, _status_publish_thread

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without the CustomTkinter dashboard (console-only, Phase 1-4 style)",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Webcam index to use for face recognition (default 0)",
    )
    parser.add_argument(
        "--fake-camera-dir",
        default=None,
        help="Directory of test images to cycle through instead of a real webcam (for testing without hardware)",
    )
    args = parser.parse_args()

    mqtt_client = SentinelMQTTClient(
        on_message=on_message,
        on_connect_change=on_connect_change,
    )
    threat_analyzer = ThreatAnalyzer(state, mqtt_client, event_logger)
    environmental_controller = EnvironmentalController(state, mqtt_client)

    video_stream = None
    face_engine = None
    try:
        source = args.fake_camera_dir if args.fake_camera_dir else args.camera_index
        video_stream = VideoStream(source=source)
        video_stream.start()
        face_engine = FaceEngine()
        logger.info("Camera/face recognition ready (source=%s)", source)
    except Exception:
        logger.exception("Could not start camera/face recognition — continuing without it (PIN entry still works)")
        video_stream = None
        face_engine = None

    # Always construct AuthEngine, even without a camera: PIN entry doesn't
    # depend on it, and start_surveillance() no-ops safely when video_stream
    # or face_engine is None.
    auth_engine = AuthEngine(state, mqtt_client, event_logger, video_stream, face_engine)
    auth_engine.start_surveillance()

    mqtt_client.connect()

    _status_publish_running = True
    _status_publish_thread = threading.Thread(target=_status_publish_loop, daemon=True)
    _status_publish_thread.start()
    logger.info("Status heartbeat started (interval=%.1fs)", STATUS_PUBLISH_INTERVAL_SECONDS)

    try:
        if args.headless:
            _run_headless()
        else:
            _run_dashboard(video_stream)
    finally:
        _status_publish_running = False
        if _status_publish_thread:
            _status_publish_thread.join(timeout=2)
        if auth_engine is not None:
            auth_engine.stop_surveillance()
        if video_stream is not None:
            video_stream.stop()


def _run_headless():
    logger.info("Listening for MQTT traffic (system_state=%s). Ctrl+C to stop.", state.system_state)
    try:
        elapsed = 0
        while True:
            time.sleep(2)
            elapsed += 2
            threat_analyzer.decay_check()
            if elapsed % 10 == 0:
                logger.info("Current state snapshot: %s", state.snapshot())
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()


def _run_dashboard(video_stream):
    from dashboard import SentinelDashboard  # deferred: keeps --headless free of the ctk dependency at import time

    app = SentinelDashboard(
        state, mqtt_client, event_logger, threat_analyzer, environmental_controller,
        video_stream=video_stream, auth_engine=auth_engine,
    )
    try:
        app.mainloop()
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
