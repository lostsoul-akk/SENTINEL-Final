"""
Sentinel X — MQTT topic contract (Revision 2, dual-ESP32 architecture)

This is the single source of truth for topic names on the PC side.
Keep this in sync with whatever Person 1 documents for the ESP32 firmware.
"""

# ESP32 -> Python
TOPIC_ESP32_1_STATUS = "sentinelx/esp32_1/status"   # Auth & UI board (RFID/keypad/display), on interaction
TOPIC_ESP32_2_STATUS = "sentinelx/esp32_2/status"   # Sensor & actuator board, periodic
TOPIC_EVENT = "sentinelx/event"                     # Either board, on a triggered event

# Python -> ESP32
TOPIC_COMMAND_ESP32_1 = "sentinelx/command/esp32_1"
TOPIC_COMMAND_ESP32_2 = "sentinelx/command/esp32_2"

# Python -> Dashboard / log / any listener
TOPIC_SYSTEM_STATUS = "sentinelx/system/status"

# All topics Python needs to subscribe to on startup
SUBSCRIBE_TOPICS = [
    TOPIC_ESP32_1_STATUS,
    TOPIC_ESP32_2_STATUS,
    TOPIC_EVENT,
]
