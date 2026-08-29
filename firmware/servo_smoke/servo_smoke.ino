/* ============================================================
   Servo smoke test - wiring and power only
   ============================================================

   No wifi, no MQTT, no application. This sketch does one thing:
   sweep a servo back and forth forever, printing where it thinks the
   arm is.

   The point is to split one question into two. The node firmware
   reports "success" for a servo command because it sent the signal -
   a servo returns no position, so it cannot know more than that. If
   the arm does not move, that tells you nothing about which part is
   at fault.

   Run this instead. Then:

     arm sweeps  -> wiring and power are fine; the fault is in how
                    the node is driving it, and I want to know that.
     arm still   -> wiring or power. Nothing above this layer can
                    help, and the checklist below is the whole
                    problem space.

   CHECKLIST when the arm does not move:

     1. Servo RED goes to a 5V supply. The ESP32 3V3 pin will not
        drive an SG90; the 5V pin often browns the board out.
     2. Servo BROWN goes to that supply's ground AND that ground is
        tied to an ESP32 GND pin. Without the shared ground the servo
        has no reference for the signal and simply ignores it. This
        is the most common cause by a wide margin.
     3. Servo ORANGE goes to the pin below, and to nothing else.
     4. On a breadboard, check the jumpers are in the rows you think
        they are. A row out is an open circuit that looks connected.
   ============================================================ */

#include <ESP32Servo.h>

const int SERVO_PIN = 18;     // sleep_door on esp32_b

Servo arm;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== servo smoke test ===");
  Serial.printf("driving pin %d\n", SERVO_PIN);

  // Same requirement as the node firmware: ESP32Servo hands out no
  // channel until timers are claimed, and attach() aborts without it.
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  arm.setPeriodHertz(50);
  arm.attach(SERVO_PIN, 500, 2400);

  Serial.println("attached. sweeping 0 <-> 90 forever.");
  Serial.println("if the arm is still, the fault is wiring or power.");
}

void loop() {
  Serial.println("  -> 0 degrees");
  arm.write(0);
  delay(1200);

  Serial.println("  -> 90 degrees");
  arm.write(90);
  delay(1200);
}
