#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <Preferences.h>

// =====================================================
// WIFI / MQTT
// =====================================================
// SSID, password, and broker IP are NOT hardcoded — they're entered over
// Serial on first boot and saved to flash (Preferences), so switching
// networks (home tonight -> venue tomorrow) never requires a reflash.
// Type 'reset' within 3 seconds of a fresh boot to re-enter them.

String wifiSSID;
String wifiPassword;
String mqttServerIP;

const int MQTT_PORT = 1883;

const char* DEVICE_ID = "sentinelx_esp32_2";

const char* STATUS_TOPIC = "sentinelx/esp32_2/status";
const char* EVENT_TOPIC = "sentinelx/event";
const char* COMMAND_TOPIC = "sentinelx/command/esp32_2";

WiFiClient espClient;
PubSubClient mqtt(espClient);
Preferences prefs;

// =====================================================
// DHT11
// =====================================================

#define DHT_PIN 4
#define DHT_TYPE DHT11

DHT dht(DHT_PIN, DHT_TYPE);

// =====================================================
// ULTRASONIC
// =====================================================

const int TRIG_PIN = 13;
const int ECHO_PIN = 34;

const float PROXIMITY_THRESHOLD_CM = 25.0;

// =====================================================
// WATER SENSOR
// =====================================================

const int WATER_PIN = 32;

// IMPORTANT:
// Calibrate this value using your actual dry/wet readings.
const int WATER_THRESHOLD = 1500;

// =====================================================
// SERVOS
// =====================================================

const int DOOR_SERVO_PIN = 14;
const int WINDOW_SERVO_PIN = 25;

Servo doorServo;
Servo windowServo;

// Door:
// 90 = unlocked / straight up
// 180 = locked
const int DOOR_UNLOCKED = 90;
const int DOOR_LOCKED = 180;

// Window:
// 90 = origin
// 0 = 90-degree opening
const int WINDOW_CLOSED = 90;
const int WINDOW_OPEN = 0;

// =====================================================
// RELAY
// =====================================================

const int RELAY_PIN = 23;

// Change to false if your relay is active LOW.
const bool RELAY_ACTIVE_HIGH = true;

// =====================================================
// MAIN ACTUATOR
// =====================================================

const int MAIN_ACTUATOR_PIN = 26;

// =====================================================
// STATUS
// =====================================================

unsigned long lastStatusPublish = 0;
const unsigned long STATUS_INTERVAL = 2000;

unsigned long lastProximityEvent = 0;
const unsigned long PROXIMITY_COOLDOWN = 3000;

bool proximityActive = false;

bool waterActive = false;

// =====================================================
// WIFI
// =====================================================

void connectWiFi() {

  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(wifiSSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP2 WIFI CONNECTED");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  Serial.println("==============================");
}

// =====================================================
// MQTT
// =====================================================

void connectMQTT() {

  while (!mqtt.connected()) {

    Serial.print("Connecting to MQTT... ");

    if (mqtt.connect(DEVICE_ID)) {

      Serial.println("CONNECTED");

      mqtt.subscribe(COMMAND_TOPIC);

      publishStatus();

    } else {

      Serial.print("FAILED state=");
      Serial.println(mqtt.state());

      delay(2000);
    }
  }
}

// =====================================================
// EVENT PUBLISH
// =====================================================

void publishEvent(
  const char* type,
  const char* sensor
) {

  if (!mqtt.connected()) return;

  JsonDocument doc;

  doc["type"] = type;
  doc["sensor"] = sensor;
  doc["device"] = "esp32_2";

  char buffer[512];

  serializeJson(doc, buffer);

  mqtt.publish(EVENT_TOPIC, buffer);
}

// =====================================================
// PROXIMITY EVENT
// =====================================================

void publishProximityEvent(float distance) {

  if (!mqtt.connected()) return;

  JsonDocument doc;

  doc["type"] = "proximity";
  doc["sensor"] = "ultrasonic";
  doc["device"] = "esp32_2";
  doc["distance_cm"] = distance;
  doc["threshold_cm"] = PROXIMITY_THRESHOLD_CM;

  char buffer[512];

  serializeJson(doc, buffer);

  mqtt.publish(EVENT_TOPIC, buffer);
}

// =====================================================
// STATUS
// =====================================================

void publishStatus() {

  if (!mqtt.connected()) return;

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  float distance = readDistance();

  int water = analogRead(WATER_PIN);

  JsonDocument doc;

  doc["device"] = "esp32_2";

  doc["wifi_connected"] =
    WiFi.status() == WL_CONNECTED;

  doc["mqtt_connected"] =
    mqtt.connected();

  doc["ip"] =
    WiFi.localIP().toString();

  // -----------------------------
  // DHT
  // -----------------------------

  if (!isnan(temperature)) {
    doc["temperature"] = temperature;
  } else {
    doc["temperature"] = nullptr;
  }

  if (!isnan(humidity)) {
    doc["humidity"] = humidity;
  } else {
    doc["humidity"] = nullptr;
  }

  // -----------------------------
  // ULTRASONIC
  // -----------------------------

  if (distance >= 0) {
    doc["ultrasonic_cm"] = distance;
  } else {
    doc["ultrasonic_cm"] = nullptr;
  }

  // -----------------------------
  // WATER
  // -----------------------------

  doc["water"] = water;

  // -----------------------------
  // ACTUATOR STATE
  // -----------------------------

  doc["door"] =
    doorServo.read() >= 135 ? "LOCKED" : "UNLOCKED";

  doc["window"] =
    windowServo.read() <= 45 ? "OPEN" : "CLOSED";

  char buffer[768];

  serializeJson(doc, buffer);

  mqtt.publish(STATUS_TOPIC, buffer);
}

// =====================================================
// ULTRASONIC
// =====================================================

float readDistance() {

  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  long duration =
    pulseIn(ECHO_PIN, HIGH, 30000);

  if (duration == 0) {

    return -1;
  }

  float distance =
    duration * 0.0343 / 2.0;

  if (distance <= 0) {
    return -1;
  }

  return distance;
}

// =====================================================
// SENSOR EVENT CHECKING
// =====================================================

void checkEvents() {

  // -----------------------------
  // PROXIMITY
  // -----------------------------

  float distance = readDistance();

  bool nowClose =
    distance > 0 &&
    distance <= PROXIMITY_THRESHOLD_CM;

  if (nowClose &&
      !proximityActive &&
      millis() - lastProximityEvent > PROXIMITY_COOLDOWN) {

    proximityActive = true;

    lastProximityEvent = millis();

    publishProximityEvent(distance);

    Serial.print("EVENT: OBJECT WITHIN ");
    Serial.print(distance);
    Serial.println(" cm");
  }

  if (!nowClose) {

    proximityActive = false;
  }

  // -----------------------------
  // WATER
  // -----------------------------

  int water = analogRead(WATER_PIN);

  bool nowWet =
    water >= WATER_THRESHOLD;

  if (nowWet && !waterActive) {

    waterActive = true;

    publishEvent(
      "water_detected",
      "water_sensor"
    );

    Serial.println("EVENT: WATER DETECTED");
  }

  if (!nowWet) {

    waterActive = false;
  }
}

// =====================================================
// SERVO COMMANDS
// =====================================================

void unlockDoor() {

  doorServo.write(DOOR_UNLOCKED);

  Serial.println("DOOR → UNLOCKED");
}

void lockDoor() {

  doorServo.write(DOOR_LOCKED);

  Serial.println("DOOR → LOCKED");
}

void openWindow() {

  windowServo.write(WINDOW_OPEN);

  Serial.println("WINDOW → OPEN");
}

void closeWindow() {

  windowServo.write(WINDOW_CLOSED);

  Serial.println("WINDOW → CLOSED");
}

// =====================================================
// RELAY
// =====================================================

void setRelay(bool state) {

  if (RELAY_ACTIVE_HIGH) {

    digitalWrite(
      RELAY_PIN,
      state ? HIGH : LOW
    );

  } else {

    digitalWrite(
      RELAY_PIN,
      state ? LOW : HIGH
    );
  }
}

// =====================================================
// MQTT COMMAND HANDLER
// =====================================================

void mqttCallback(
  char* topic,
  byte* payload,
  unsigned int length
) {

  String message;

  for (unsigned int i = 0; i < length; i++) {

    message += (char)payload[i];
  }

  Serial.print("ESP2 COMMAND: ");
  Serial.println(message);

  JsonDocument doc;

  DeserializationError error =
    deserializeJson(doc, message);

  if (error) {

    Serial.println("Invalid JSON command");
    return;
  }

  const char* command =
    doc["command"];

  if (!command) return;

  // -----------------------------
  // DOOR
  // -----------------------------

  if (strcmp(command, "UNLOCK_DOOR") == 0) {

    unlockDoor();
  }

  else if (strcmp(command, "LOCK_DOOR") == 0) {

    lockDoor();
  }

  // -----------------------------
  // WINDOW
  // -----------------------------

  else if (strcmp(command, "OPEN_WINDOW") == 0) {

    openWindow();
  }

  else if (strcmp(command, "CLOSE_WINDOW") == 0) {

    closeWindow();
  }

  // -----------------------------
  // RELAY
  // -----------------------------

  else if (strcmp(command, "AC_ON") == 0) {

    setRelay(true);
  }

  else if (strcmp(command, "AC_OFF") == 0) {

    setRelay(false);
  }

  // -----------------------------
  // MAIN ACTUATOR
  // -----------------------------

  else if (strcmp(command, "MAIN_ACTUATOR_ON") == 0) {

    digitalWrite(MAIN_ACTUATOR_PIN, HIGH);
  }

  else if (strcmp(command, "MAIN_ACTUATOR_OFF") == 0) {

    digitalWrite(MAIN_ACTUATOR_PIN, LOW);
  }

  publishStatus();
}

// =====================================================
// NETWORK CONFIG (Serial + Preferences, no hardcoded creds)
// =====================================================

// Reads one line typed into Serial, blocking until Enter is pressed.
// Echoes it back since some Serial Monitor configs don't echo input.
String promptSerialLine(const char* label) {

  Serial.print(label);

  while (!Serial.available()) {
    delay(10);
  }

  String line = Serial.readStringUntil('\n');
  line.trim();

  Serial.println(line);

  return line;
}

// Gives a 3-second window right after boot to type 'reset' and force
// re-entry of WiFi/MQTT settings, even if valid ones are already saved.
bool checkForResetRequest() {

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP2 BOOTING");
  Serial.println("Type 'reset' within 3 seconds to re-enter WiFi/MQTT settings...");
  Serial.println("==============================");

  unsigned long waitStart = millis();

  while (millis() - waitStart < 3000) {

    if (Serial.available()) {

      String input = Serial.readStringUntil('\n');
      input.trim();

      if (input.equalsIgnoreCase("reset")) {
        return true;
      }
    }
  }

  return false;
}

// Loads saved WiFi/MQTT settings from flash, or prompts for them over
// Serial (first boot, or after a 'reset' request) and saves what's typed.
void loadOrPromptConfig(bool forceReset) {

  prefs.begin("sentinelx2", false);

  if (forceReset) {
    Serial.println("Reconfiguring — clearing saved WiFi/MQTT settings.");
    prefs.clear();
  }

  wifiSSID = prefs.getString("ssid", "");
  wifiPassword = prefs.getString("pass", "");
  mqttServerIP = prefs.getString("broker", "");

  if (wifiSSID == "" || wifiPassword == "" || mqttServerIP == "") {

    Serial.println();
    Serial.println("==============================");
    Serial.println("Enter network settings:");
    Serial.println("==============================");

    wifiSSID = promptSerialLine("Wi-Fi SSID: ");
    wifiPassword = promptSerialLine("Wi-Fi Password: ");
    mqttServerIP = promptSerialLine("MQTT Broker IP (LAN IP of the PC running Mosquitto): ");

    prefs.putString("ssid", wifiSSID);
    prefs.putString("pass", wifiPassword);
    prefs.putString("broker", mqttServerIP);

    Serial.println("Saved — these will be reused automatically on every future boot.");

  } else {

    Serial.println("Loaded saved WiFi/MQTT settings from flash:");
    Serial.print("  SSID: ");
    Serial.println(wifiSSID);
    Serial.print("  Broker IP: ");
    Serial.println(mqttServerIP);
    Serial.println("(Type 'reset' within 3s of boot next time to change these.)");
  }

  prefs.end();
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);
  delay(100);  // let Serial settle before the reset-window prompt prints

  bool forceReset = checkForResetRequest();
  loadOrPromptConfig(forceReset);

  // Sensors
  dht.begin();

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);

  // Relay
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);

  // Main actuator
  pinMode(MAIN_ACTUATOR_PIN, OUTPUT);
  digitalWrite(MAIN_ACTUATOR_PIN, LOW);

  // Servos
  doorServo.setPeriodHertz(50);
  windowServo.setPeriodHertz(50);

  doorServo.attach(
    DOOR_SERVO_PIN,
    500,
    2400
  );

  windowServo.attach(
    WINDOW_SERVO_PIN,
    500,
    2400
  );

  // Initial positions
  doorServo.write(DOOR_LOCKED);
  windowServo.write(WINDOW_CLOSED);

  connectWiFi();

  mqtt.setServer(
    mqttServerIP.c_str(),
    MQTT_PORT
  );

  mqtt.setCallback(mqttCallback);

  connectMQTT();

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP2 ONLINE");
  Serial.println("Sensors + actuators ready");
  Serial.println("==============================");
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  if (WiFi.status() != WL_CONNECTED) {

    connectWiFi();
  }

  if (!mqtt.connected()) {

    connectMQTT();
  }

  mqtt.loop();

  checkEvents();

  if (millis() - lastStatusPublish >= STATUS_INTERVAL) {

    lastStatusPublish = millis();

    publishStatus();
  }

  delay(50);
}
