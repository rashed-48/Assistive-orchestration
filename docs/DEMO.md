# Demo runbook

## 1. Which board is which room

| Board | `NODE_SELECT` | Rooms | Devices | Pin |
|---|---|---|---|---|
| **esp32_a** | `1` | Drawing Room + Relax Room | `drawing_light` LED | 23 |
| | | | `relax_light` LED | 22 |
| | | | `relax_tv` servo | 21 |
| | | | `buzzer` | 19 |
| | | | `exit_door` servo | 18 |
| | | | `relax_door` servo | 5 |
| **esp32_b** | `2` | Sleep Room | `sleep_light` LED | 23 |
| | | | `sleep_door` servo | 18 |
| | | | `sleep_bed` servo | 17 |
| | | | `medication_servo` servo | 16 |
| **esp32_c** | `3` | Study Room + Meal Room | `study_light` LED | 23 |
| | | | `meal_light` LED | 22 |
| | | | `study_door` servo | 18 |
| | | | `meal_door` servo | 5 |
| | | | `study_table` servo | 17 |
| | | | `meal_table` servo | 16 |

**Never use GPIO 2 or 25** — they drive the antenna switch on the
WROOM-DA and the board will lose Wi-Fi.

Every LED: `GPIO → 220 Ω → long leg → LED → short leg → GND`.
Every servo: orange → GPIO, red → external 5 V, brown → GND **tied to
the ESP32's GND**. ESP32 itself on USB, never on the 3V3 pin.

## 2. What each voice command does

| Say | Must be in | Board(s) | What moves |
|---|---|---|---|
| "I want to sleep" | Sleep Room | b | sleep light on, bed prepares |
| "I'm awake" / "wake up" | Sleep Room | b | bed resets |
| "I need my medication" | Sleep Room | b | dispenser sweeps out and back |
| "I want to relax" | Relax Room | a | relax light on, TV servo presses |
| "I want to study" | Study Room | c | study light on, table prepares |
| "It's time to eat" | Meal Room | c | meal light on, table prepares |
| "Shut everything down" | Drawing Room | a, b, c | all lights off, tables/bed reset, exit door opens then closes |
| **"Emergency"** | anywhere | a, b, c | **buzzer, all five doors open**; environment latches |
| "Emergency is over" | anywhere | a, b, c | buzzer off, doors close, latch clears |

The room matters: the system refuses a command that does not make
sense where the person is. Set location first with the amber banner in
the web UI, or `where sleep` in the console.

**The most impressive sequence:** "Emergency" → everything opens and
the buzzer sounds → try "I want to relax" → **refused** (latched) →
"Emergency is over" → doors close → "I want to relax" → works.

## 3. Wire esp32_c tonight

2 LEDs + 4 servos. That is a lot of servo current on one supply — use
a phone charger through a USB breakout or 4×AA, not a 9 V block.

If you cannot wire all six, set the unwired ones to `false` in the
device table (last column) before flashing. They will answer `error`
and the workflow will stop honestly rather than pretend.

For the demo, the minimum that makes `STUDY_MODE` and
`PREPARE_FOR_MEAL` work: `study_light` 23, `study_table` 17,
`meal_light` 22, `meal_table` 16. The two doors (18, 5) only matter for
EMERGENCY — wire them if you can, mark `false` if not.

## 4. Flash checklist — all three boards

One file: `firmware/assistive_node/assistive_node.ino`. Same for every
board. Before each upload check these lines:

```
#define NODE_SELECT     1 / 2 / 3     <- the ONLY line that differs
#define WIRE_SERVOS     1
#define DEDUP_ENABLED   1             <- MUST be 1. 0 re-dispenses medication.
const char *WIFI_SSID = "ci";         <- the hotspot
```

Serial monitor at 115200 after each flash. You want:

```
=== Assistive node esp32_c ===
  study_light        pin 23
  ...
WiFi ..... 10.x.x.x  rssi -xx dBm
looking for the broker.... found 10.x.x.x
MQTT connecting... ok
listening on assistive/command/esp32_c  via 10.x.x.x
```

`NOT WIRED` next to a device means its flag is `false`. `(servo
disabled)` means `WIRE_SERVOS` is 0 — wrong for the demo.

## 4b. What the dashboard shows

Open `http://127.0.0.1:5000`. Three columns and a trace:

- **Voice** — hold the mic (or hold Space), release, see the transcript,
  the recognised intent, its similarity score against the 0.65
  threshold, and the top-3 candidates. Confirm or cancel.
- **Environment** — the floor plan. Rooms light up, doors open, tiles
  show live device state. The person marker is where the system
  believes they are. Click a room to declare location.
- **Pipeline** — five stages, live: speech, recognition, plan (the
  ordered actions before anything is sent), execution (each action
  advances sent → ack → done → commit with real millisecond timing),
  and commit (what changed in logical state).
- **Wire** — every MQTT message on the bus, observed by an independent
  subscriber. Commands, acks, completions, retries, duplicates, with
  the interval between each leg.

The header shows each node's liveness, probed every minute with an
action no node has, so nothing moves to find out.

Things worth pointing at for an audience: the **ack** column (the
command reached the node) versus the **done** column (the hardware
finished) — that gap is the servo moving; a **retry** row carrying the
same command_id, answered with **dedup** and no second actuation; and
during EMERGENCY, the refused command in the message box while the
banner is red.

## 5. Startup sequence on the day

**Order matters.** Broker first, then app, then boards.

```powershell
# 1. hotspot on, laptop connected to "ci"
# 2. broker is a Windows service - check it:
Get-Service mosquitto            # must say Running

# 3. the app (starts the broker beacon automatically)
cd E:\Assistive-orchestration
.\.venv\Scripts\python.exe run_web.py
# open http://127.0.0.1:5000

# 4. power the three boards. They find the broker themselves.
```

**Do NOT start any simulated node.** All three boards are real now. A
simulated node with the same id would answer alongside the real one
and corrupt everything.

Confirm each board is genuinely answering (in a second terminal):

```powershell
.\.venv\Scripts\python.exe -m tools.bench_node --host <laptop ip> --node esp32_a --device drawing_light --action LIGHT_ON --off-action LIGHT_OFF --suite --strict
.\.venv\Scripts\python.exe -m tools.bench_node --host <laptop ip> --node esp32_b --device sleep_light   --action LIGHT_ON --off-action LIGHT_OFF --suite --strict
.\.venv\Scripts\python.exe -m tools.bench_node --host <laptop ip> --node esp32_c --device study_light   --action LIGHT_ON --off-action LIGHT_OFF --suite --strict
```

Each must say **11/11** and **"exactly one node is answering"**.

Find the laptop IP with `ipconfig` — it changes when the hotspot
restarts. The boards handle that on their own; only the bench command
needs it.

## 6. If something is wrong

| Symptom | Cause | Fix |
|---|---|---|
| Board prints `WiFi.....` forever | hotspot on 5 GHz, or off | phone hotspot settings → 2.4 GHz |
| `nothing heard`, `failed rc=-2` | app not running, so no beacon | start `run_web.py` first |
| Servo doesn't move, LED does | servo supply dead or unplugged | check battery, check GND tie |
| Board reboots repeatedly | brownout | servos off the ESP32's pins, onto the external supply |
| "exactly one node is answering" FAILS | a simulated node is running | kill it (see below) |
| Command refused: location unknown | after a restart | amber banner in UI, pick the room |
| Command refused: `EmergencyActive` | latched | say "emergency is over" |

Kill any stray simulated node:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'simulated_node' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Watch the raw traffic if a board seems deaf:
```powershell
.\.venv\Scripts\python.exe -m tools.bench_node --host <laptop ip> --watch
```

## 7. Before you leave tonight

- Wire esp32_c, flash it with `NODE_SELECT 3`, see `listening on`.
- Run the three bench commands. Three × 11/11.
- Say "emergency" once, watch all five doors and the buzzer. Say
  "emergency is over".
- Charge the phone. Charge the servo battery or bring a charger.
- **Commit the repository.** Everything from the last two sessions is
  uncommitted.
