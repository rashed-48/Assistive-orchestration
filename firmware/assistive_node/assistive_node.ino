/* ============================================================
   Assistive Orchestration - ESP32 node firmware
   ============================================================

   One sketch for all three nodes. Set NODE_ID below, wire the pins
   in the DEVICES table to match, flash, done.

   It speaks exactly the protocol the Python MQTTDeviceExecutor
   already uses, so no application code changes.

     subscribes : assistive/command/<node_id>
     publishes  : assistive/status/<node_id>

   Command in:
     { "device":"sleep_light", "action":"LIGHT_ON",
       "parameters":{}, "command_id":"4b45c942-..." }

   Status out:
     { "command_id":"4b45c942-...", "node":"esp32_b",
       "device":"sleep_light", "action":"LIGHT_ON",
       "status":"success" }

   THREE RULES THAT MATTER
     1. Echo command_id back byte for byte. The executor correlates
        on it; a wrong id reads as a timeout.
     2. Deduplicate on command_id. The executor retries a lost
        acknowledgement using the SAME id. Without dedup a retry
        opens a door twice. On a repeat: re-publish the stored
        status, do NOT actuate.
     3. Only report success after the hardware has actually moved.
        Logical state is committed from this reply.

   Libraries (Library Manager):
     PubSubClient   by Nick O'Leary
     ArduinoJson    by Benoit Blanchon   (v6 or v7)
     ESP32Servo     by Kevin Harrington
   ============================================================ */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <WiFiUdp.h>

/* ArduinoJson v7 removed StaticJsonDocument; v6 has no plain
   JsonDocument. Library Manager installs v7 today but plenty of
   machines still carry v6, so support both rather than pinning. */
#if ARDUINOJSON_VERSION_MAJOR >= 7
  #define JSON_DOC(name, capacity) JsonDocument name
#else
  #define JSON_DOC(name, capacity) StaticJsonDocument<capacity> name
#endif

/* ============================================================
   1. EDIT THIS BLOCK
   ============================================================ */

// Pick ONE board. This is the only line that differs between the
// three nodes; everything else is shared.
// 1 = esp32_a,  2 = esp32_b,  3 = esp32_c
// (numbers, not letters: an undefined identifier evaluates to 0 in a
//  preprocessor #if, so bare letters would all compare equal)
#define NODE_SELECT 2

#if   NODE_SELECT == 1
  #define NODE_ID "esp32_a"
#elif NODE_SELECT == 3
  #define NODE_ID "esp32_c"
#else
  #define NODE_ID "esp32_b"
#endif

const char *WIFI_SSID = "ci";                 // hotspot
const char *WIFI_PASS = "qwerty12";

const char *MQTT_HOST = "10.166.126.173";  // fallback only; normally discovered
const uint16_t MQTT_PORT = 1883;

// The address above is only a fallback. On boot the node listens for
// the broker announcing itself, so moving to a phone hotspot - where
// the host gets a completely different address - needs no reflash.
// Set to 0 to always use MQTT_HOST.
#define DISCOVER_BROKER 1
const uint16_t DISCOVERY_PORT = 18830;
const uint32_t DISCOVERY_WAIT_MS = 8000;

// Set to 0 while bringing a board up with nothing but an LED wired.
// Servos are then never initialised and never claimed to have moved:
// a servo action answers "error" rather than reporting success for
// hardware that is not there. Set to 1 once the servos are connected.
#define WIRE_SERVOS 1

// EXPERIMENT ONLY. 1 is correct behaviour and the default.
//
// Set to 0 and the node re-executes a command it has already
// completed, instead of re-sending its stored acknowledgement.
// That is the control condition for the idempotency measurement:
// it makes the failure happen so it can be quantified, rather
// than only asserting that it does not.
//
// Never leave a node running with this at 0. A retried
// ACTIVATE_MEDICATION becomes a second dose.
#define DEDUP_ENABLED 1

/* ============================================================
   2. DEVICE TABLE
   Device names are fixed by app/devices/device_registry.py.
   Change the PINS to match your wiring, not the names.

   The last column says whether anything is actually connected to that
   pin. Set it false for a device you have not wired yet: the node then
   answers "error" for it rather than reporting a success for hardware
   that never moved, and the application declines to commit its state.
   ============================================================ */

enum Kind { RELAY_LIGHT, RELAY_TV, SERVO_TV, SERVO_DOOR, SERVO_TABLE,
            SERVO_BED, SERVO_MED, BUZZER };

struct Device {
  const char *name;
  Kind kind;
  uint8_t pin;
  int restAngle;     // servos: closed / normal
  int activeAngle;   // servos: open / ready
  bool wired;        // false = nothing on this pin; answer "error"
};

Device DEVICES[] = {
#if NODE_SELECT == 1
  { "drawing_light",     RELAY_LIGHT,  23,   0,   0, true },
  { "relax_light",       RELAY_LIGHT,  22,   0,   0, true },
  { "relax_tv",          SERVO_TV,     21,   0,  90, true },
  { "buzzer",            BUZZER,       19,   0,   0, true },
  { "exit_door",         SERVO_DOOR,   18,   0,  90, true },
  { "relax_door",        SERVO_DOOR,    5,   0,  90, true },
#elif NODE_SELECT == 3
  { "study_light",       RELAY_LIGHT,  23,   0,   0, true },
  { "meal_light",        RELAY_LIGHT,  22,   0,   0, true },
  { "study_door",        SERVO_DOOR,   18,   0,  90, true },
  { "meal_door",         SERVO_DOOR,    5,   0,  90, true },
  { "study_table",       SERVO_TABLE,  17,   0,  60, true },
  { "meal_table",        SERVO_TABLE,  16,   0,  60, true },
#else   /* 2 - esp32_b, the default */
  { "sleep_light",       RELAY_LIGHT,  23,   0,   0, true },
  { "sleep_door",        SERVO_DOOR,   18,   0,  90, true },
  { "sleep_bed",         SERVO_BED,    17,   0,  45, true },
  { "medication_servo",  SERVO_MED,    16,   0,  80, true },
#endif
};

const int DEVICE_COUNT = sizeof(DEVICES) / sizeof(DEVICES[0]);

// Relay boards are usually active LOW. Set false for plain LEDs.
const bool RELAY_ACTIVE_LOW = false;

/* KEEP THIS THE FIRST FUNCTION IN THE FILE.
   The Arduino builder generates prototypes for every function and
   injects them immediately above the first one it finds. Anything
   defined before the types above would put those prototypes ahead of
   `struct Device`, and the sketch stops compiling with
   "'Device' does not name a type" - pointing at a line that is fine. */
inline bool isRelay(Kind k) { return k == RELAY_LIGHT || k == RELAY_TV; }

/* ============================================================
   3. RUNTIME
   ============================================================ */

WiFiClient net;
PubSubClient mqtt(net);
Servo servos[DEVICE_COUNT];

char commandTopic[64];
char statusTopic[64];

WiFiUDP discoveryUdp;
char brokerHost[40];      // resolved at boot, then on repeated failure

/* ---- dedup: the last N completed commands and their replies ---- */
#define HISTORY 32

struct Completed {
  char id[40];
  char device[24];
  char action[24];
  char status[10];
};

Completed history[HISTORY];
int historyNext = 0;

int findCompleted(const char *id) {
  for (int i = 0; i < HISTORY; i++) {
    if (history[i].id[0] && !strcmp(history[i].id, id)) return i;
  }
  return -1;
}

void remember(const char *id, const char *device, const char *action, const char *status) {
  if (!id || !*id) return;                 // nothing to correlate on
  Completed &slot = history[historyNext];
  strncpy(slot.id, id, sizeof(slot.id) - 1);        slot.id[sizeof(slot.id) - 1] = 0;
  strncpy(slot.device, device, sizeof(slot.device) - 1); slot.device[sizeof(slot.device) - 1] = 0;
  strncpy(slot.action, action, sizeof(slot.action) - 1); slot.action[sizeof(slot.action) - 1] = 0;
  strncpy(slot.status, status, sizeof(slot.status) - 1); slot.status[sizeof(slot.status) - 1] = 0;
  historyNext = (historyNext + 1) % HISTORY;
}

/* ============================================================
   4. HARDWARE
   ============================================================ */

int deviceIndex(const char *name) {
  for (int i = 0; i < DEVICE_COUNT; i++) {
    if (!strcmp(DEVICES[i].name, name)) return i;
  }
  return -1;
}

void writeRelay(const Device &d, bool on) {
  digitalWrite(d.pin, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

/* Returns false when the servo is not wired, so the caller reports an
   error instead of an unearned success. */
bool moveServo(int i, int angle) {
#if WIRE_SERVOS
  servos[i].write(angle);
  delay(700);                  // let it physically arrive before we ACK
  return true;
#else
  (void)i; (void)angle;
  return false;
#endif
}

/* Returns true only when the hardware actually moved. */
bool actuate(int i, const char *action) {
  const Device &d = DEVICES[i];

  // Nothing on this pin, so nothing can have moved. Reporting success
  // here would have the application commit a state for absent
  // hardware - the precise failure the acknowledgement gate exists to
  // stop.
  if (!d.wired) return false;

  switch (d.kind) {

    case RELAY_LIGHT:
      if (!strcmp(action, "LIGHT_ON"))  { writeRelay(d, true);  return true; }
      if (!strcmp(action, "LIGHT_OFF")) { writeRelay(d, false); return true; }
      return false;

    case RELAY_TV:
      if (!strcmp(action, "TV_ON"))  { writeRelay(d, true);  return true; }
      if (!strcmp(action, "TV_OFF")) { writeRelay(d, false); return true; }
      return false;

    // A television driven by a servo pressing its button, rather than
    // by a relay in its supply. Same two actions, different mechanism.
    case SERVO_TV:
      if (!strcmp(action, "TV_ON"))  { return moveServo(i, d.activeAngle); }
      if (!strcmp(action, "TV_OFF")) { return moveServo(i, d.restAngle); }
      return false;

    case BUZZER:
      if (!strcmp(action, "BUZZER_ON"))  { digitalWrite(d.pin, HIGH); return true; }
      if (!strcmp(action, "BUZZER_OFF")) { digitalWrite(d.pin, LOW);  return true; }
      return false;

    case SERVO_DOOR:
      if (!strcmp(action, "OPEN_DOOR"))  { return moveServo(i, d.activeAngle); }
      if (!strcmp(action, "CLOSE_DOOR")) { return moveServo(i, d.restAngle); }
      return false;

    case SERVO_TABLE:
      if (!strcmp(action, "PREPARE_TABLE")) { return moveServo(i, d.activeAngle); }
      if (!strcmp(action, "RESET_TABLE"))   { return moveServo(i, d.restAngle); }
      return false;

    case SERVO_BED:
      if (!strcmp(action, "PREPARE_BED")) { return moveServo(i, d.activeAngle); }
      if (!strcmp(action, "RESET_BED"))   { return moveServo(i, d.restAngle); }
      return false;

    case SERVO_MED:
      // A dose is an impulse, not a state: sweep out and return.
      // This is the ONE action that is not safe to repeat, which is
      // exactly why the dedup above must work.
      if (!strcmp(action, "ACTIVATE_MEDICATION")) {
        if (!moveServo(i, d.activeAngle)) return false;
        delay(500);
        return moveServo(i, d.restAngle);
      }
      return false;
  }
  return false;
}

/* ============================================================
   5. MQTT
   ============================================================ */

/* Sent the moment a command arrives, before the duplicate check and
   before any actuation. Separates how long the command took to get
   here from how long the hardware took to act on it. */
void publishAck(const char *id, const char *device, const char *action) {
  JSON_DOC(doc, 256);
  doc["command_id"] = id;
  doc["node"]       = NODE_ID;
  doc["device"]     = device;
  doc["action"]     = action;
  doc["phase"]      = "ack";

  char buffer[256];
  size_t n = serializeJson(doc, buffer);
  mqtt.publish(statusTopic, (uint8_t *)buffer, n, false);
}

void publishStatus(const char *id, const char *device, const char *action,
                   const char *status, bool duplicate) {
  JSON_DOC(doc, 256);
  doc["command_id"] = id;
  doc["node"]       = NODE_ID;
  doc["device"]     = device;
  doc["action"]     = action;
  doc["status"]     = status;
  doc["phase"]      = "complete";
  if (duplicate) doc["duplicate"] = true;

  char buffer[256];
  size_t n = serializeJson(doc, buffer);
  mqtt.publish(statusTopic, (uint8_t *)buffer, n, false);

  Serial.printf("  -> %s %s %s%s\n", status, device, action, duplicate ? " (duplicate)" : "");
}

void onMessage(char *topic, byte *payload, unsigned int length) {
  JSON_DOC(doc, 384);
  if (deserializeJson(doc, payload, length)) {
    Serial.println("  !! unparsable command");
    return;
  }

  const char *device = doc["device"]     | "";
  const char *action = doc["action"]     | "";
  const char *id     = doc["command_id"] | "";

  Serial.printf("<- %s %s  id=%s\n", action, device, id);

  // Before the duplicate check and before actuation, so the two costs
  // stay separable.
  publishAck(id, device, action);

  // RULE 2: a repeated id means a lost acknowledgement, not a new
  // command. Answer again; do not touch the hardware.
#if DEDUP_ENABLED
  int seen = findCompleted(id);
  if (seen >= 0) {
    publishStatus(id, history[seen].device, history[seen].action, history[seen].status, true);
    return;
  }
#else
  // Control condition: the replay falls through and actuates.
#endif

  int i = deviceIndex(device);
  bool ok = (i >= 0) && actuate(i, action);   // RULE 3: actuate, then report

  const char *status = ok ? "success" : "error";
  remember(id, device, action, status);
  publishStatus(id, device, action, status, false);   // RULE 1: echo the id
}

/* Listen for the broker announcing itself. Returns true when a
   usable address was heard; brokerHost is left untouched otherwise so
   the caller can fall back to the compiled-in one. */
bool discoverBroker(uint32_t waitMs) {
#if !DISCOVER_BROKER
  (void)waitMs;
  return false;
#else
  Serial.print("looking for the broker");
  if (!discoveryUdp.begin(DISCOVERY_PORT)) {
    Serial.println(" - cannot open the discovery port");
    return false;
  }

  uint32_t deadline = millis() + waitMs;
  while (millis() < deadline) {
    int size = discoveryUdp.parsePacket();
    if (size > 0) {
      char buffer[192];
      int n = discoveryUdp.read(buffer, sizeof(buffer) - 1);
      buffer[n > 0 ? n : 0] = 0;

      JSON_DOC(doc, 192);
      if (!deserializeJson(doc, buffer)) {
        const char *service = doc["service"] | "";
        const char *host    = doc["broker"]  | "";
        // Anything may be broadcasting on a shared network; only act
        // on an announcement that names this service.
        if (!strcmp(service, "assistive-broker") && *host) {
          strncpy(brokerHost, host, sizeof(brokerHost) - 1);
          brokerHost[sizeof(brokerHost) - 1] = 0;
          discoveryUdp.stop();
          Serial.printf(" found %s\n", brokerHost);
          return true;
        }
      }
    }
    Serial.print(".");
    delay(200);
  }

  discoveryUdp.stop();
  Serial.println(" nothing heard");
  return false;
#endif
}

void connectMQTT() {
  static int failures = 0;
  while (!mqtt.connected()) {
    Serial.print("MQTT connecting... ");
    // The client id must be unique per board or the broker will
    // disconnect them in a loop.
    if (mqtt.connect(NODE_ID)) {
      Serial.println("ok");
      mqtt.subscribe(commandTopic, 1);
      Serial.printf("listening on %s  via %s\n",
                    commandTopic, brokerHost);
    } else {
      Serial.printf("failed rc=%d, retrying\n", mqtt.state());
      delay(2000);

      // Several failures in a row usually means the host moved -
      // a new hotspot, a new lease - rather than that it is down.
      // Listen again rather than retrying a stale address forever.
      if (++failures % 3 == 0 && discoverBroker(DISCOVERY_WAIT_MS)) {
        mqtt.setServer(brokerHost, MQTT_PORT);
      }
    }
  }
}

/* ============================================================
   6. LIFECYCLE
   ============================================================ */

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\n=== Assistive node %s ===\n", NODE_ID);
#if !DEDUP_ENABLED
  Serial.println("  *** DEDUP DISABLED - EXPERIMENT BUILD ***");
  Serial.println("  A retried command will be executed again.");
#endif

  snprintf(commandTopic, sizeof(commandTopic), "assistive/command/%s", NODE_ID);
  snprintf(statusTopic,  sizeof(statusTopic),  "assistive/status/%s",  NODE_ID);

  // Every device starts in its resting state, matching the logical
  // world the application assumes on a fresh start.
#if WIRE_SERVOS
  // ESP32Servo drives servos from the LEDC peripheral and will not
  // hand out a channel until timers have been claimed. Calling
  // attach() without this aborts inside the library, which on an
  // ESP32 means a panic and an immediate reboot - so the sketch never
  // finishes setup() and reprints its banner forever.
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
#endif

#ifdef BOARD_HAS_DUAL_ANTENNA
  // The ESP32-WROOM-DA switches between its two antennas using
  // these pins. Driving one as a device output breaks wifi in a way
  // that looks like a flaky network, not a wiring mistake.
  for (int i = 0; i < DEVICE_COUNT; i++) {
    if (DEVICES[i].pin == ANT1 || DEVICES[i].pin == ANT2) {
      Serial.printf("  FATAL: %s is on pin %d, reserved for the "
                    "antenna switch on this board\n",
                    DEVICES[i].name, DEVICES[i].pin);
    }
  }
#endif

  for (int i = 0; i < DEVICE_COUNT; i++) {
    Device &d = DEVICES[i];
    if (isRelay(d.kind) || d.kind == BUZZER) {
      pinMode(d.pin, OUTPUT);
      if (isRelay(d.kind)) writeRelay(d, false); else digitalWrite(d.pin, LOW);
      Serial.printf("  %-18s pin %2d\n", d.name, d.pin);
    } else {
#if WIRE_SERVOS
      servos[i].setPeriodHertz(50);
      servos[i].attach(d.pin, 500, 2400);
      servos[i].write(d.restAngle);
      Serial.printf("  %-18s pin %2d\n", d.name, d.pin);
#else
      Serial.printf("  %-18s pin %2d  (servo disabled)\n", d.name, d.pin);
#endif
    }
    if (!d.wired) Serial.printf("  %-18s NOT WIRED - answers error\n", d.name);
    Serial.flush();
  }

  // Modem sleep parks the radio between beacons to save power. On a
  // marginal link it silently drops inbound packets, so the node
  // stays subscribed but never hears its commands - and stops
  // answering ping too. A mains-powered node has nothing to gain
  // from it.
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.printf(" %s  rssi %d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());

  // Below about -75 dBm the link is too weak to stay usable, and the
  // failure looks like a broker or firmware problem rather than a
  // radio one. Say so plainly here instead.
  if (WiFi.RSSI() < -75) {
    Serial.println("  WARNING: weak signal. Move the board closer to");
    Serial.println("  the router - drops here look like MQTT faults.");
  }

  strncpy(brokerHost, MQTT_HOST, sizeof(brokerHost) - 1);
  brokerHost[sizeof(brokerHost) - 1] = 0;
  if (!discoverBroker(DISCOVERY_WAIT_MS)) {
    Serial.printf("falling back to %s\n", brokerHost);
  }

  mqtt.setServer(brokerHost, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(512);       // default 256 is tight; give headroom
  mqtt.setKeepAlive(15);         // notice a dead link sooner
  connectMQTT();
}

void loop() {
  // A dropped association is reported, not silently endured: without
  // this the board sits in mqtt.loop() forever and the only symptom
  // is that commands go unanswered.
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, reconnecting");
    WiFi.reconnect();
    while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
    Serial.printf(" back %s  rssi %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  }

  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  // A quiet heartbeat, so a board that is alive but unheard can be
  // told apart from one that has crashed.
  static unsigned long lastBeat = 0;
  if (millis() - lastBeat > 15000) {
    lastBeat = millis();
    Serial.printf("[alive] rssi %d dBm  mqtt %s\n",
                  WiFi.RSSI(), mqtt.connected() ? "up" : "down");
  }
}
