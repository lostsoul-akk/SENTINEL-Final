#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>
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

const char* DEVICE_ID = "sentinelx_esp32_1";

const char* STATUS_TOPIC = "sentinelx/esp32_1/status";
const char* EVENT_TOPIC = "sentinelx/event";
const char* COMMAND_TOPIC = "sentinelx/command/esp32_1";

WiFiClient espClient;
PubSubClient mqtt(espClient);
Preferences prefs;

// =====================================================
// LCD
// =====================================================

LiquidCrystal_I2C lcd(0x27, 16, 2);

// =====================================================
// KEYPAD
// =====================================================

const byte ROWS = 4;
const byte COLS = 4;

char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};

byte rowPins[ROWS] = {13, 14, 16, 17};
byte colPins[COLS] = {25, 26, 27, 32};

Keypad keypad = Keypad(
  makeKeymap(keys),
  rowPins,
  colPins,
  ROWS,
  COLS
);

// =====================================================
// LEDs / BUZZER
// =====================================================

const int GREEN_LED = 4;
const int YELLOW_LED = 12;
const int RED_LED = 15;
const int BUZZER = 2;

// =====================================================
// STATUS
// =====================================================

String displayState = "Ready";
String lastKey = "idle";

// PIN entry (per PIN_ENTRY_CONTRACT.md): digits accumulate here as they're
// pressed, and are only published as a completed PIN when '#' is pressed.
String pinBuffer = "";
uint32_t keypadSeq = 0;

unsigned long lastStatusPublish = 0;
const unsigned long STATUS_INTERVAL = 2000;

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
  Serial.println("================================");
  Serial.println("ESP1 WIFI CONNECTED");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  Serial.println("================================");
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

      Serial.print("FAILED, state=");
      Serial.println(mqtt.state());

      delay(2000);
    }
  }
}

// =====================================================
// LCD
// =====================================================

void showLCD(String line1, String line2) {

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));

  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));

  displayState = line1;
}

// =====================================================
// BUZZER SOUNDS
// =====================================================

void soundArmed() {

  tone(BUZZER, 1200, 150);
  delay(180);

  tone(BUZZER, 1600, 180);
  delay(220);

  noTone(BUZZER);
}

void soundDisarmed() {

  tone(BUZZER, 1600, 150);
  delay(180);

  tone(BUZZER, 1000, 250);
  delay(300);

  noTone(BUZZER);
}

void soundDoorUnlocked() {

  tone(BUZZER, 1000, 100);
  delay(130);

  tone(BUZZER, 1400, 180);
  delay(220);

  noTone(BUZZER);
}

void soundAlarm() {

  for (int i = 0; i < 3; i++) {

    tone(BUZZER, 1800, 250);
    delay(300);

    tone(BUZZER, 900, 250);
    delay(300);
  }

  noTone(BUZZER);
}

// =====================================================
// EVENT PUBLISH
// =====================================================

void publishEvent(
  const char* type,
  const char* sensor,
  const char* value = nullptr
) {

  if (!mqtt.connected()) return;

  JsonDocument doc;

  doc["type"] = type;
  doc["sensor"] = sensor;
  doc["device"] = "esp32_1";

  if (value != nullptr) {
    doc["value"] = value;
  }

  char buffer[512];

  serializeJson(doc, buffer);

  mqtt.publish(EVENT_TOPIC, buffer);
}

// =====================================================
// STATUS PUBLISH
// =====================================================

void publishStatus() {

  if (!mqtt.connected()) return;

  JsonDocument doc;

  doc["device"] = "esp32_1";
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["mqtt_connected"] = mqtt.connected();
  doc["ip"] = WiFi.localIP().toString();

  doc["keypad"] = lastKey;
  doc["display"] = displayState;

  char buffer[512];

  serializeJson(doc, buffer);

  mqtt.publish(STATUS_TOPIC, buffer);
}

// =====================================================
// COMMAND HANDLER
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

  Serial.print("ESP1 COMMAND: ");
  Serial.println(message);

  JsonDocument doc;

  DeserializationError error =
    deserializeJson(doc, message);

  if (error) {
    Serial.println("Invalid JSON command");
    return;
  }

  const char* command = doc["command"];

  if (!command) return;

  // -----------------------------
  // DISPLAY
  // -----------------------------

  if (strcmp(command, "SHOW_MESSAGE") == 0) {

    const char* text = doc["text"] | "";

    showLCD("MESSAGE", text);

    publishStatus();
  }

  // -----------------------------
  // ARMED
  // -----------------------------

  else if (strcmp(command, "SOUND_ARMED") == 0) {

    soundArmed();

    showLCD("SYSTEM ARMED", "Monitoring...");
  }

  // -----------------------------
  // DISARMED
  // -----------------------------

  else if (strcmp(command, "SOUND_DISARMED") == 0) {

    soundDisarmed();

    showLCD("SYSTEM DISARMED", "Standby");
  }

  // -----------------------------
  // DOOR UNLOCK SOUND
  // -----------------------------

  else if (strcmp(command, "SOUND_DOOR_UNLOCKED") == 0) {

    soundDoorUnlocked();

    showLCD("DOOR UNLOCKED", "Welcome");
  }

  // -----------------------------
  // ALARM
  // -----------------------------

  else if (strcmp(command, "SOUND_ALARM") == 0) {

    soundAlarm();

    digitalWrite(RED_LED, HIGH);
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(GREEN_LED, LOW);

    showLCD("!!! ALERT !!!", "THREAT DETECTED");
  }

  // -----------------------------
  // STATUS
  // -----------------------------

  else if (strcmp(command, "SET_STATUS_GREEN") == 0) {

    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(RED_LED, LOW);
  }

  else if (strcmp(command, "SET_STATUS_YELLOW") == 0) {

    digitalWrite(GREEN_LED, LOW);
    digitalWrite(YELLOW_LED, HIGH);
    digitalWrite(RED_LED, LOW);
  }

  else if (strcmp(command, "SET_STATUS_RED") == 0) {

    digitalWrite(GREEN_LED, LOW);
    digitalWrite(YELLOW_LED, LOW);
    digitalWrite(RED_LED, HIGH);
  }
}

// =====================================================
// KEYPAD PIN ENTRY (per PIN_ENTRY_CONTRACT.md)
// =====================================================
// Digits accumulate locally as they're pressed. The full PIN is only
// published — once — when '#' (Enter) is pressed, as a dedicated
// {"type": "keypad_pin", ...} message on STATUS_TOPIC. '*' clears a
// mistyped entry. Letters A-D are unused for now.

void publishKeypadPin(const String &pin) {

  if (!mqtt.connected()) return;

  JsonDocument doc;

  doc["type"] = "keypad_pin";
  doc["pin"] = pin;
  doc["seq"] = keypadSeq++;
  // No "timestamp" field: this board has no synced clock (no NTP/RTC
  // setup here), so the PC stamps its own receipt time instead — see
  // the open item in PIN_ENTRY_CONTRACT.md Section 6.

  char buffer[256];

  serializeJson(doc, buffer);

  mqtt.publish(STATUS_TOPIC, buffer);
}

void checkKeypad() {

  char key = keypad.getKey();

  if (!key) return;

  Serial.print("KEYPAD: ");
  Serial.println(key);

  tone(BUZZER, 1500, 80);

  if (key == '#') {

    // Enter — submit whatever's been typed so far, then clear.
    lastKey = "idle";
    showLCD("CHECKING...", "");

    publishKeypadPin(pinBuffer);

    pinBuffer = "";

  } else if (key == '*') {

    // Clear — mistyped entry, start over.
    pinBuffer = "";
    lastKey = "idle";
    showLCD("Enter PIN", "");

  } else if (isDigit(key)) {

    if (pinBuffer.length() < 8) {  // cap length per the firmware guide
      pinBuffer += key;
    }

    lastKey = String(key);

    // Masked on-screen — don't show the live PIN to anyone watching.
    String masked = "";
    for (unsigned int i = 0; i < pinBuffer.length(); i++) {
      masked += "*";
    }
    showLCD("Enter PIN", masked);
  }

  // A/B/C/D: reserved, currently unused — ignored.

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
  Serial.println("ESP1 BOOTING");
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

  prefs.begin("sentinelx1", false);

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

  pinMode(GREEN_LED, OUTPUT);
  pinMode(YELLOW_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  digitalWrite(GREEN_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(RED_LED, LOW);

  Wire.begin(21, 22);

  lcd.init();
  lcd.backlight();

  showLCD("SENTINEL X", "Connecting...");

  connectWiFi();

  mqtt.setServer(mqttServerIP.c_str(), MQTT_PORT);
  mqtt.setCallback(mqttCallback);

  showLCD("WiFi OK", "MQTT connecting");

  connectMQTT();

  digitalWrite(GREEN_LED, HIGH);

  showLCD("ESP1 ONLINE", "System Ready");
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

  checkKeypad();

  if (millis() - lastStatusPublish >= STATUS_INTERVAL) {

    lastStatusPublish = millis();

    publishStatus();
  }
}
