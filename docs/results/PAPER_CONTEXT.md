# Research-grade technical extraction and evidence audit

**Source of truth:** this repository — source, tests, firmware, and the
measured results in `RESULTS.md`, `dedup_control.md`,
`execution_measurements.csv`, `INTAKE_FILLED.md`.

**Method note.** The brief asks for extraction from "project
documentation". There is no prose design document in this repository.
The artefact *is* the source, the test suite, and the measurement
records. Every fact below cites a file. Where a fact would normally
come from a written spec and cannot be recovered from code or logs, it
is marked `NOT FOUND` rather than reconstructed.

---

# SECTION A — PROJECT IDENTITY

| Item | Value | Evidence | Confidence |
|---|---|---|---|
| System name | Assistive Orchestration | repository root, `app/` | HIGH |
| Working title | `NOT FOUND` — no title recorded | — | — |
| Domain | Voice-controlled assistive smart environment | `app/voice/`, `app/orchestration/` | HIGH |
| Target users | People with mobility limitations | inferred from device set (bed, medication dispenser, doors) | MEDIUM |
| Intended environment | Single dwelling, 6 rooms | `app/orchestration/state.py` `Room` enum | HIGH |
| Main use case | One spoken utterance triggers a multi-device, state-dependent workflow | `app/orchestration/orchestrator.py` | HIGH |
| Secondary use case | Latched emergency mode with explicit clearance | `EMERGENCY_INTENTS`, `orchestrator.py:60` | HIGH |

**Target-user claim is `NEEDS VERIFICATION`.** No requirements
document, no user consultation, and no user study exists. The device
set implies the population; nothing states it.

### One-sentence technical definition

A distributed voice-controlled home orchestration system in which a
spoken utterance is mapped to an intent by sentence-embedding
similarity, expanded into an ordered device-action plan conditioned on
persisted logical state, dispatched over MQTT to ESP32 nodes with
stable per-action command identifiers, and committed to state only on
receipt of a correlated node acknowledgement.

### Technical overview (≈130 words)

The system converts a single spoken command into a multi-device
workflow whose content depends on current logical state rather than on
the utterance alone. Speech is transcribed offline with faster-whisper
and matched against 313 reference sentences using `all-MiniLM-L6-v2`
embeddings, scored max-over-sentences per intent against a 0.65
cosine threshold. An accepted intent is expanded by a planner that
consults room occupancy, mode, location certainty, and an emergency
latch, producing an ordered action list. Actions are published over
MQTT QoS 1 to ESP32 nodes, each carrying a command identifier that is
held stable across retries so a node can distinguish a retry from a new
command. Device state is committed only when a correlated
acknowledgement arrives; room, mode, and location commit only after a
workflow completes. State is persisted atomically and recovered on
restart.

---

# SECTION B — PROBLEM STATEMENT

### Clearly documented problem

**None.** There is no problem statement in the repository. This is a
genuine gap: `CLAIM NOT SUPPORTED BY DOCUMENTATION`.

### Problem inferred from implementation

Each of the following is inferred from a mechanism that exists to solve
it. The inference is defensible; the motivation is not written down.

| Inferred problem | Mechanism that implies it | Evidence |
|---|---|---|
| A retried command can actuate hardware twice | 32-entry dedup ring buffer keyed on `command_id` | `assistive_node.ino`, `findCompleted()` |
| A system may commit state for hardware that did not move | commit gated on acknowledgement | `orchestrator.py`, `_is_acknowledged()` |
| The person's location may be unknown after a restart | `LocationStatus` KNOWN/IN_TRANSIT/UNKNOWN | `state.py:15` |
| An emergency must not be silently cancelled | latch requiring explicit `EMERGENCY_CLEAR` | `orchestrator.py:151` `EmergencyActive` |
| Ordinary and safety workflows need different failure policies | `BEST_EFFORT_INTENTS` vs fail-fast | `orchestrator.py:60` |

### Problem NOT adequately established

- That voice control specifically benefits this user population
- That existing commercial systems fail at these tasks
- That double-actuation occurs in deployed assistive systems

All three would need literature. **Do not assert them from this
artefact.**

---

# SECTION C — RESEARCH GAP

### Gap supported by the implementation

The system's distinctive commitment is that **an acknowledgement, not a
dispatch, is what licenses a state change** — and that the
acknowledgement must be idempotent under retry. This is visible in
three coupled mechanisms:

1. `command_id` stable across retries (`mqtt_device.py:78–82`, comment
   explains the reasoning explicitly)
2. node-side dedup returning stored status without re-actuating
   (`assistive_node.ino`)
3. two-tier commit — device state per acknowledged action, room/mode
   after full workflow (`orchestrator.py`)

### GAP THAT STILL NEEDS LITERATURE SUPPORT

**This is the paper's largest external dependency.** A prior audit in
this project concluded the headline framing — state-aware
dependency-driven voice orchestration — is **pre-empted by SmartAid
(PLOS ONE 2024) and HearthNet (CAIS 2026)**. That audit is recorded in
conversation history, not in this repository: `NEEDS VERIFICATION`
against the actual papers.

Literature must establish, and currently does not:

- whether idempotent actuation is already standard in assistive IoT
- whether ACK-gated commit is claimed by prior work
- whether location-certainty modelling is novel
- whether anyone reports measured double-actuation rates

---

# SECTION D — SYSTEM OBJECTIVES

No objectives are stated anywhere. The following are **reconstructed
from implemented mechanisms** and must not be presented as authored
objectives.

| Reconstructed objective | Status | Evidence |
|---|---|---|
| Recognise 11 assistive intents from speech | **Fully achieved** | 0.718 accuracy on 110-sentence holdout |
| Never route a safety-critical intent to a different action | **Fully achieved** | precision 1.00 all intents, holdout |
| Expand an intent into a state-dependent plan | **Fully achieved** | `workflow_engine.py`, 566 lines |
| Ensure a retry cannot actuate twice | **Fully achieved, controlled** | 0/4 vs 4/4, `dedup_control.md` |
| Commit state only for acknowledged actions | **Partially achieved** | holds for relays; for servos the ACK does not prove movement |
| Survive restart with recovered state | **Fully achieved** | 36 tests, `test_startup_recovery.py` |
| Operate across multiple physical nodes | **Partially achieved** | 2 of 3 nodes physical |
| Degrade safely when a node is unreachable | **Achieved but slow** | 13.8× latency penalty |
| Compare against a baseline scheduler | **Not implemented** | no baseline exists |

---

# SECTION E — SYSTEM ARCHITECTURE

| Component | Exact name | Role | Inputs | Outputs | Connected to | Protocol | Evidence |
|---|---|---|---|---|---|---|---|
| Microphone capture | `SpeechRecorder` | 16 kHz mono float32 WAV | audio | `.wav` | transcriber | sounddevice | `recorder.py:13–17` |
| STT | `SpeechTranscriber` (faster-whisper `base`, int8, CPU) | transcript | `.wav` | text | recogniser | in-process | `transcriber.py` |
| Intent recognition | `IntentRecognizer` (`all-MiniLM-L6-v2`) | intent + decision | text | `{intent, score, decision}` | orchestrator | in-process | `recognizer.py` |
| Voice pipeline | `VoiceController` | binds the three above | audio | intent | web/console | in-process | `controller.py`, 364 lines |
| Planner | `WorkflowEngine` | ordered action list | intent + state | `[Action]` | orchestrator | in-process | `workflow_engine.py`, 566 lines |
| Topology | `TransitionBuilder` | room-graph traversal | from/to room | actions | planner | in-process | `transitions.py`, 392 lines |
| Logical state | `ContextManager` | authoritative state | commits | state | all | in-process | `context_manager.py`, 406 lines |
| Orchestrator | `Orchestrator` | workflow entry point, commit | intent | results | executor | in-process | `orchestrator.py`, 982 lines |
| Executor | `MQTTDeviceExecutor` | dispatch + retry | Action | status | MQTT | MQTT QoS 1 | `mqtt_device.py`, 309 lines |
| Transport | `MQTTClient` | pub/sub, correlation | payloads | replies | broker | paho-mqtt 2.1.0 | `mqtt_client.py`, 232 lines |
| Broker | Mosquitto | message routing | — | — | all | MQTT 1883 | `tools/setup_broker.ps1` |
| Discovery | `BrokerBeacon` | announces broker address | — | UDP datagram | nodes | UDP 18830 | `discovery.py`, 162 lines |
| Persistence | `StateRepository` | atomic snapshot + event log | state | JSON, JSONL | runtime | filesystem | `persistence.py`, 237 lines |
| Runtime | `ApplicationRuntime` | lifecycle, recovery | — | — | all | in-process | `runtime.py`, 520 lines |
| Web UI | Flask app | operator interface | HTTP | JSON/HTML | runtime | HTTP :5000 | `web/server.py`, 362 lines |
| Console | `ConsoleAssistant` | continuous CLI loop | speech | — | runtime | stdio | `console.py`, 376 lines |
| Node firmware | `assistive_node.ino` | actuation + dedup | MQTT | MQTT | broker | MQTT/Wi-Fi | firmware |
| Simulated node | `SimulatedNode` | software stand-in | MQTT | MQTT | broker | MQTT | `simulated_node.py`, 567 lines |

### Data flow (as implemented)

```
speech → 16kHz WAV → faster-whisper → text
       → MiniLM embedding → cosine vs 313 refs → max-per-intent
       → threshold 0.65 → {PREDICTED | UNKNOWN}
       → [web only] human confirmation
       → WorkflowEngine(intent, state) → ordered [Action]
       → per action: publish assistive/command/<node>, QoS 1,
         stable command_id, 5 s timeout, ≤2 retries
       → node: publish ack → dedup check → actuate → publish complete
       → executor correlates on command_id, ignores phase=ack
       → orchestrator commits device state per acknowledged action
       → on workflow completion commits room / mode / location
       → snapshot written atomically, event appended to JSONL
```

**Classification: distributed, edge-actuated, locally hosted.** No
cloud service is used anywhere. STT and embeddings run on the
controller CPU. `HIGH` confidence — verified by absence of any network
client other than MQTT and the UDP beacon.

---

# SECTION F — HARDWARE INVENTORY

| Component | Model | Qty | Purpose | Voltage | Interface | Pins | Power source | Evidence |
|---|---|---|---|---|---|---|---|---|
| MCU | ESP32-WROOM-DA | 2 | node controllers | 3.3 V logic | Wi-Fi 2.4 GHz | — | USB | build log FQBN `esp32:esp32:esp32da` |
| Servo | SG90 | 6 | doors, bed, TV, dispenser | 5 V | PWM 50 Hz | see below | external 5 V | `PLANS` in `measure_execution.py` |
| LED | generic + 220 Ω | 3 | room lights | 3.3 V | GPIO | 23, 22 | ESP32 GPIO | device table |
| Buzzer | `NOT FOUND` — model unrecorded | 1 | emergency alarm | 3.3 V | GPIO | 19 | ESP32 GPIO | device table |
| Power supply | `NOT FOUND` — battery type unrecorded | 1 | servo rail | 5 V | — | — | — | — |
| Capacitor | 470 µF (specified, fitment `NEEDS VERIFICATION`) | 1 | rail decoupling | — | — | — | — | wiring guidance only |

### Pin map (authoritative — firmware device table)

**esp32_a** — `drawing_light` 23, `relax_light` 22, `relax_tv` 21
(servo), `buzzer` 19, `exit_door` 18 (servo), `relax_door` 5 (servo)

**esp32_b** — `sleep_light` 23, `sleep_door` 18 (servo), `sleep_bed` 17
(servo), `medication_servo` 16 (servo)

**esp32_c** — simulated only: `study_light` 23, `meal_light` 22,
`study_door` 18, `meal_door` 5, `study_table` 17, `meal_table` 16

**Reserved:** GPIO 2 and 25 are the WROOM-DA antenna switch
(`variants/esp32da/pins_arduino.h`, `ANT1`/`ANT2`). The firmware
refuses to use them and warns at boot.

**Servo PWM:** 50 Hz, 500–2400 µs pulse range, `attach(pin, 500, 2400)`.

**No sensors of any kind.** No `digitalRead`, no input pin, no
feedback path. `HIGH` confidence — verified by grep over the firmware.

**Current draw, power consumption, battery capacity, runtime: NOT
MEASURED.** No instrumentation exists.

---

# SECTION G — SOFTWARE STACK

| Layer | Component | Version | Function |
|---|---|---|---|
| Language | Python | 3.11.9 | controller |
| Language | C++ / Arduino | esp32 core 3.3.11 | firmware |
| OS | Windows 11 | 10.0.26200 | controller host |
| STT | faster-whisper `base` | int8, CPU | transcription |
| Embeddings | sentence-transformers | 5.7.0, `all-MiniLM-L6-v2` | intent similarity |
| ML utility | scikit-learn | 1.9.0 | cosine similarity, metrics |
| Data | pandas | — | dataset loading |
| Messaging | paho-mqtt | 2.1.0 | client |
| Broker | Mosquitto | — | routing |
| Web | Flask | — | operator UI |
| Audio | sounddevice | — | capture |
| Firmware libs | PubSubClient 2.8, ArduinoJson 7.4.3, ESP32Servo 3.2.1 | | MQTT, JSON, PWM |
| Test | pytest | — | 450 tests |

`Mosquitto`, `pandas`, `Flask`, `sounddevice` versions: `NOT FOUND`.

**Database: none.** Persistence is a JSON snapshot plus an append-only
JSONL event log on the local filesystem. **Cloud services: none.**

---

# SECTION H — COMMUNICATION AND NETWORKING

| Source | Destination | Protocol | Data | Trigger | Purpose | Evidence |
|---|---|---|---|---|---|---|
| Executor | node | MQTT QoS 1, `assistive/command/<node>` | `{device, action, parameters, command_id}` | per action | dispatch | `mqtt_device.py` |
| Node | executor | MQTT QoS 1, `assistive/status/<node>` | `{command_id, node, device, action, phase:"ack"}` | on receipt | arrival receipt | firmware `publishAck` |
| Node | executor | same topic | `{…, status, phase:"complete", duplicate?}` | after actuation | result | firmware `publishStatus` |
| Controller | broadcast | UDP 18830 | `{service, broker, port}` | every 2 s | broker discovery | `discovery.py` |
| Browser | controller | HTTP :5000 | JSON | user action | UI | `web/server.py` |

**Network:** 2.4 GHz Wi-Fi, shared phone hotspot, RSSI −48 to −57 dBm.
ESP32 has no 5 GHz radio — a hard constraint that caused two observed
outages when the hotspot changed band.

**Reliability mechanisms:** QoS 1; 5 s per-action timeout; 2 retries (3
attempts); stable `command_id` across attempts; node-side 32-entry
dedup ring buffer; `WiFi.setSleep(false)`; 15 s MQTT keepalive;
automatic re-discovery after 3 consecutive connection failures.

**Security: none.** `allow_anonymous true`, no TLS, no authentication,
no authorisation, no encryption. See Section T.

---

# SECTION I — DATA FLOW

| Stage | Input | Processing | Output | Component | Timing |
|---|---|---|---|---|---|
| Acquisition | microphone | 16 kHz mono capture | WAV | `SpeechRecorder` | user-paced |
| Transcription | WAV | faster-whisper int8 CPU | text | `SpeechTranscriber` | `NOT MEASURED` |
| Recognition | text | embed, cosine vs 313, max-per-intent | intent + decision | `IntentRecognizer` | `NOT MEASURED` |
| Validation | intent | threshold 0.65; web adds human confirm | accept/reject | recogniser + UI | — |
| Planning | intent + state | state-conditioned expansion | `[Action]` | `WorkflowEngine` | ~2 ms (simulated-only workflows) |
| Dispatch | Action | publish, await, retry | status | `MQTTDeviceExecutor` | 13–19 ms to ack |
| Actuation | command | GPIO / PWM + fixed delay | status | firmware | 54–1902 ms |
| Commit | status | per-action device state | new state | `ContextManager` | — |
| Persistence | state | temp → flush → fsync → replace | snapshot + `.bak` | `StateRepository` | `NOT MEASURED` |
| Logging | event | append | `events.jsonl` | `StateRepository` | — |
| Notification | result | UI render | HTML/JSON | Flask | — |

**Two latencies are unmeasured and matter for an end-to-end claim: STT
and embedding inference.** Every latency figure in this project starts
at *command publish*, not at *utterance*. `CRITICAL` — see Section Z.

---

# SECTION J — ALGORITHMS AND CONTROL LOGIC

### J1 — Intent recognition (max-over-sentences)

```
embed query, L2-normalised
similarities ← cosine(query, 313 reference embeddings)
for each intent: score[intent] ← MAX over that intent's sentences
best ← argmax score
decision ← PREDICTED if score[best] ≥ 0.65 else UNKNOWN
```

Max-over-sentences, **not** centroid. Consequence: one strong
paraphrase carries the intent; class imbalance (19–58 sentences) does
not dilute a score. Threshold 0.65. Vocabulary is exactly
`{PREDICTED, UNKNOWN}` — enforced by `test_intent_contract.py`.

### J2 — Dispatch with idempotent retry

```
command_id ← uuid4()               # once per logical action
for attempt in 1..3:
    publish(command)                # SAME id every attempt
    status ← wait(5 s, phase="complete")
    if status.success: return
    if status.error:   raise ActionExecutionError
raise ActionNotAcknowledged
```

**The stable id is the load-bearing decision.** A fresh id per attempt
would make a retry indistinguishable from a new command
(`mqtt_device.py:78–82`).

### J3 — Node dedup

```
on message:
    publish ack                     # before dedup, before actuation
    if id in history[32]:  publish stored status, duplicate=true; return
    ok ← actuate(device, action)
    remember(id, device, action, ok)
    publish status
```

### J4 — Two-tier commit

Device state commits per acknowledged action. Room, mode, and location
commit only after the whole workflow succeeds. Consequence: a partial
failure never leaves a claimed mode.

### J5 — Failure policy by intent class

`BEST_EFFORT_INTENTS = {EMERGENCY, EMERGENCY_CLEAR}` continue past
failures. All others fail fast and abandon remaining actions.

### J6 — Emergency latch

`EMERGENCY` sets a latch with `emergency_declared_at`. Ordinary intents
raise `EmergencyActive` until `EMERGENCY_CLEAR`.

### J7 — Location certainty

`LocationStatus ∈ {KNOWN, IN_TRANSIT, UNKNOWN}`, deliberately **not**
members of `Room`. Location-dependent intents raise `LocationUnknown`
when not KNOWN. Recovery is an explicit human declaration.

### J8 — Corridor traversal invariant

Drawing Room is the central transition area. Traversal ending elsewhere
lights the corridor unless state says it is already lit
(`transitions.py:31–52`).

### J9 — Crash detection

`clean_shutdown` is written **false** at startup and true only on
orderly shutdown. A snapshot found with `false` implies a crash.

---

# SECTION K — AI / MACHINE LEARNING

| Item | Value |
|---|---|
| Task | 11-class intent classification with rejection |
| Method | **Retrieval by embedding similarity. No training.** |
| Model | `all-MiniLM-L6-v2`, frozen, pre-trained |
| Reference set | 313 sentences, 19–58 per intent |
| Holdout | 110, balanced 10/intent, 0 exact overlap, 4 near-duplicates |
| Validation | 105, 0 exact overlap, **7 near-duplicates** |
| Preprocessing | L2 normalisation only |
| Augmentation | none |
| Training / epochs / optimiser / loss | **not applicable — nothing is trained** |
| Threshold τ | 0.65, single operating point, **no sweep** |
| Inference hardware | controller CPU |
| Inference latency | **NOT MEASURED** |
| Model size | ~80 MB (`NEEDS VERIFICATION` — not recorded) |

### Results — holdout (recommended)

Accuracy **0.718**, macro F1 0.74, weighted precision **1.00**,
rejection **0.282**, n = 110.

| Intent | P | R | F1 |
|---|---|---|---|
| PREPARE_FOR_SLEEP | 1.00 | 1.00 | 1.00 |
| PREPARE_FOR_MEAL | 1.00 | 1.00 | 1.00 |
| MEDICATION | 1.00 | 1.00 | 1.00 |
| EMERGENCY | 1.00 | 0.90 | 0.95 |
| EMERGENCY_CLEAR | 1.00 | 0.90 | 0.95 |
| WAKE_UP | 1.00 | 0.70 | 0.82 |
| RETURN_TO_ROOM | 1.00 | 0.60 | 0.75 |
| SHUTDOWN_ENVIRONMENT | 1.00 | 0.60 | 0.75 |
| RELAX_MODE | 1.00 | 0.50 | 0.67 |
| STUDY_MODE | 1.00 | 0.50 | 0.67 |
| LEAVE_ROOM | 1.00 | 0.20 | 0.33 |

**Zero cross-intent confusions.** All 31 errors are rejections.

Validation (n = 105): accuracy 0.752, rejection 0.162, but
`PREPARE_FOR_SLEEP` precision falls to 0.54 — it absorbs 3 from
`WAKE_UP` and 2 from `SHUTDOWN_ENVIRONMENT`, consistent with the 7
near-duplicates found in that split.

**"Training performance" does not exist here** — nothing is trained, so
the usual train/test gap is not the risk. The risk is reference-set
leakage, quantified above.

---

# SECTION L — IMPLEMENTATION DETAILS

**33 Python modules, ~7,300 lines** in `app/` and `tools/`. Largest:
`orchestrator.py` 982, `workflow_engine.py` 566, `simulated_node.py`
567, `runtime.py` 520.

**Startup:** construct `ContextManager` → optional `StateRepository`
restore → `_apply_recovery_policy()` → build executor → `connect()` →
start beacon.

**Restore is all-or-nothing** — `StateRestoreError` rejects a partial
snapshot rather than resuming half a world.

**Recovery policy:** unclean shutdown downgrades location to UNKNOWN;
an interrupted transit is abandoned; a latched emergency survives
restart.

**Concurrency:** beacon on a daemon thread; MQTT on a paho network
thread with a `Condition`-guarded status buffer; **workflow execution
is strictly serial**.

**Error handling:** `ActionExecutionError`, `ActionNotAcknowledged`,
`EmergencyActive`, `LocationUnknown`, `StateRestoreError`.

**Fail-safe:** node reports `error` for unwired devices (`wired` flag)
and for unknown device/action, so the orchestrator refuses to commit.

**Deliberate omission — no automatic action replay.**
`ACTIVATE_MEDICATION` must never be replayed after restart.

---

# SECTION M — USER INTERACTION

**Web (Flask, port 5000):** `GET /`, `POST /api/recording/start`,
`POST /api/recording/stop`, `POST /api/intent/confirm`,
`POST /api/intent/cancel`, `POST /api/location/confirm`,
`GET /api/state`.

**Console:** continuous loop preserving state between commands; `where
<room>` resolves an unknown location; exit words end the session.

### Pipeline

```
speech → WAV 16 kHz → faster-whisper → text
       → embed → max-per-intent cosine → τ=0.65
       → PREDICTED: shown to user for confirmation (web)
         UNKNOWN:   refused, user informed
       → confirm → plan → execute → per-action results rendered
       → state panel and floor plan updated
```

**Confirmation is explicit in the web path.** No workflow executes on
recognition alone. `HIGH` — `test_web_confirmation_flow.py`, 20 tests.

**Authentication: none. Permissions: none.**

---

# SECTION N — EXPERIMENTAL SETUP

| Item | Value |
|---|---|
| Controller | Windows 11, Python 3.11.9; **CPU/RAM `NOT FOUND`** |
| Nodes | 2 physical ESP32-WROOM-DA + 1 simulated |
| Physical devices | 10 — 3 LED, 1 buzzer, 6 SG90 |
| Network | 2.4 GHz hotspot, shared, −48 to −57 dBm |
| Broker | Mosquitto, QoS 1, on controller |
| Dates | 2026-08-29 to 2026-08-30 |
| Total duration | `NOT RECORDED` |
| Baseline system | **NONE** |

**Trial counts:** latency n=10–15 per device (3 for medication);
workflow n=8; dedup control n=4 replays × 4 devices × 2 conditions;
degradation n=4 per condition; reliability 4 intents × 3 trials × 3
conditions; recognition n=110 holdout, n=105 validation.

**Instruments:** `time.perf_counter()` on the controller; wire
observation via a subscribed MQTT client; **human visual observation**
for physical actuation.

**Fault injection method:** software process termination of the
simulated node — permanent, or restarted after 6 s. **Not** physical
power-down and **not** message dropping.

---

# SECTION O — PERFORMANCE RESULTS

| Metric | Value | Unit | Condition | n | Method | Confidence |
|---|---|---|---|---|---|---|
| Intent accuracy | 0.718 | — | holdout | 110 | scripted | HIGH |
| Rejection rate | 0.282 | — | holdout | 110 | scripted | HIGH |
| Weighted precision | 1.00 | — | holdout | 110 | scripted | HIGH |
| Intent accuracy | 0.752 | — | validation | 105 | scripted | MEDIUM (leakage) |
| dispatch→ack | 13–19 | ms | per device | 10 each | perf_counter | HIGH |
| ack→complete, LED/buzzer | 54–61 | ms | per device | 10 each | perf_counter | HIGH |
| ack→complete, servo | 698–704 | ms | per device | 10 each | perf_counter | HIGH |
| ack→complete, medication | 1896 | ms | esp32_b | 3 | perf_counter | MEDIUM (n=3) |
| Total per-action, LED | 66–77 | ms | both nodes | 10 each | perf_counter | HIGH |
| Total per-action, servo | 713–721 | ms | both nodes | 10 each | perf_counter | HIGH |
| Workflow PREPARE_FOR_SLEEP | 769 | ms median | healthy | 8 | perf_counter | HIGH |
| Workflow SHUTDOWN_ENVIRONMENT | 828 | ms median | healthy, 11 actions | 8 | perf_counter | HIGH |
| Workflow EMERGENCY | 2335 | ms median | healthy, 6 actions, 3 nodes | 4 | perf_counter | HIGH |
| EMERGENCY, 2 of 6 unreachable | 32256 | ms median | degraded | 4 | perf_counter | HIGH |
| Degradation factor | 13.8 | × | — | 4+4 | derived | HIGH |
| Replay re-execution, dedup ON | 0/40 | — | all devices | 40 | timing | HIGH |
| Replay re-execution, dedup OFF | 4/4 per servo | — | 3 servos | 12 | timing | HIGH |
| Workflow completion, healthy | 12/12 | — | — | 12 | wire count | HIGH |
| Workflow completion, node down | 9/12 | — | — | 12 | wire count | HIGH |
| Workflow completion, transient | 12/12 | — | — | 12 | wire count | HIGH |
| Task success, healthy | 60/60 | — | — | 60 | wire count | HIGH |
| Retry rate, healthy | 0 | — | — | 60 | wire count | HIGH |
| Retry rate, degraded | 0.60 | — | — | 30 | wire count | HIGH |
| Recovery success | 6/6 | — | transient | 6 | wire count | HIGH |
| Failure containment | 30/30 = 1.0 | — | fail-fast | 3 | plan diff | HIGH |
| Node conformance | 11/11, 10/10 | checks | both nodes | 9 devices | bench suite | HIGH |
| Wi-Fi dropouts | 0 | in 5.5 min | after `setSleep(false)` | 1 run | probe | MEDIUM |

### Strong evidence
Per-action and workflow latency; dedup control; degradation;
reliability; recognition on holdout; conformance.

### Weak evidence
Medication latency (n=3); EMERGENCY workflow (n=4); Wi-Fi stability
(single run); the three simulated-only workflows carry no hardware
timing.

### Missing measurements
**STT latency. Embedding inference latency. End-to-end
utterance-to-actuation latency. Power, current, battery life. CPU and
RAM utilisation. Persistence write latency. Throughput. Packet loss.**

---

# SECTION P — BASELINES AND COMPARISONS

## NO BASELINE COMPARISON IDENTIFIED

No fixed-delay scheduler, no alternative algorithm, no commercial
system, no literature method is implemented or compared against.

**Two internal controlled comparisons exist** and are the closest thing
to a baseline:

| Comparison | Variable | Result |
|---|---|---|
| Dedup ON vs OFF | firmware `DEDUP_ENABLED` | 0/4 vs **4/4** re-execution per servo |
| All nodes reachable vs 2 of 6 down | node availability | 2335 ms vs **32256 ms** |

Both are single-variable, same-hardware, same-network. They are
legitimate controlled experiments; **neither is a scheduler
comparison.**

### Scientifically useful additions

1. **Fixed-delay baseline** — dispatch on a timer instead of on ACK,
   at δ_tight ≈ mean actuation and δ_safe ≈ worst case. This yields
   ordering violations and silent successes, the two numbers that would
   most directly evidence the central claim.
2. **Centroid vs max-over-sentences** recognition.
3. **τ sweep.**
4. **Concurrent vs serial dispatch** for best-effort intents — the
   13.8× result already motivates it.

---

# SECTION Q — NOVELTY EXTRACTION

### A. Architectural — potential novelty candidate
Two-tier commit: device state per acknowledged action, room/mode/location
only after full workflow. **Distinctiveness not established by this
artefact.** Literature comparison required. Confidence LOW.

### B. Functional — potential novelty candidate
Per-intent failure policy: best-effort for emergency, fail-fast
otherwise, with measured containment 1.0 and 0. The **measurement** of
both policies under one injected failure may be more distinctive than
the design. Confidence MEDIUM for the measurement, LOW for the design.

### C. Algorithmic — potential novelty candidate, strongest
**Detecting actuator re-execution from acknowledgement latency alone.**
Because the node acknowledges only after its actuation sequence, a
replay served from stored state costs transport (27 ms) while a
re-execution costs full actuation (1915 ms) — a 72× separation. This
permits machine-checkable idempotency verification on actuators with no
position feedback.

**Stated limits, which strengthen rather than weaken it:** it cannot
decide anything for instant devices (reported "not separable"), and it
detects *that the node ran its actuation sequence*, not that the arm
moved. Confidence MEDIUM. Literature comparison required.

### D. Integration — weak
Whisper + MiniLM + MQTT + ESP32 is a conventional stack. **Do not claim
novelty.**

### E. Application — weak
Assistive smart home is well populated. A prior audit identified
SmartAid and HearthNet as prior art (`NEEDS VERIFICATION`).

### F. Interaction — potential novelty candidate
`LocationStatus` as a first-class three-valued type, deliberately not a
`Room` member, with human declaration as the only recovery. Rated
moderate novelty by the earlier audit. Confidence LOW-MEDIUM.

### G. Engineering — potential novelty candidate
Zero-configuration broker discovery by UDP beacon with re-discovery
after 3 failures. Demonstrated surviving an unplanned address change
mid-session. Common technique; the *demonstration* is evidence, the
technique is not novel.

**No claim in this section is established by the artefact alone.**

---

# SECTION R — RESEARCH CONTRIBUTIONS

### Contribution 1 — An implemented, measured, idempotent actuation path
Stable `command_id` across retries with node-side dedup, measured
across 10 physical devices: **40/40 replays served from stored state,
zero re-execution**, against **4/4 re-execution per servo** with the
mechanism disabled. **Strongly supported.**

### Contribution 2 — Latency-based verification of actuation idempotency
A method for detecting re-execution on feedback-less actuators using
acknowledgement timing, with its applicability limit stated (fails for
instant devices). **Moderately supported** — demonstrated on one
platform, not compared to alternatives.

### Contribution 3 — Quantified cost of best-effort execution
Emergency workflow latency degrades **13.8×** (2335 → 32256 ms) with 2
of 6 devices unreachable, while still completing every reachable
action. A negative result about the system's own design.
**Strongly supported.**

### Contribution 4 — Rejection-dominant intent recognition
On a disjoint 110-sentence holdout, **precision 1.00 for all 11
intents**; all 31 errors are rejections, none substitutions.
**Moderately supported** — n=110, single τ, no sweep.

### Contribution 5 — Failure containment measurement
Fail-fast intents dispatch **0 of 30** remaining planned actions after
abort (containment 1.0); best-effort dispatch all. **Strongly
supported**, but the term must be defined as implemented — there is no
dependency graph and no `CANCELLED` state.

---

# SECTION S — LIMITATIONS

### Documented in the repository

1. **A servo cannot confirm it moved.** ACK-gated commit is weaker for
   servos than relays (`RESULTS.md`, Limitations).
2. One node simulated; three workflows carry no hardware timing.
3. Single environment, single session.
4. n = 105/110 recognition; wide per-intent intervals.
5. No user study.

### Analyst-identified — not stated by the authors

6. **A real silent success occurred during data collection.** Six
   servos lost power; all reported `success`; `PREPARE_FOR_SLEEP`
   committed `sleep_bed = READY`. Caught only by human observation.
   This is simultaneously the strongest evidence for the paper's thesis
   and a threat to the validity of any servo measurement collected
   without a visual check.
7. **No end-to-end latency.** All timing starts at command publish.
   STT and embedding cost are unmeasured, so no "response time" claim
   can be made.
8. **No baseline** — Section P.
9. **No security whatsoever** — Section T.
10. **Serial execution only**; the 13.8× degradation follows directly.
11. **Fixed 700 ms actuation delay** is a hard-coded constant, not
    derived from servo specification or measurement.
12. **Timeouts judged, not measured** — 5 s against a 2 s worst-case
    action.
13. **Paraphrase leakage** in the validation split (7 near-duplicates).
14. **Class imbalance** in the reference set, 19–58 sentences.
15. **No τ sweep.**
16. **Wi-Fi band fragility** — 2.4 GHz only; two observed outages when
    the hotspot moved band.
17. **Credentials in source.** Wi-Fi SSID and password are committed
    in the firmware.

---

# SECTION T — SECURITY AND PRIVACY

| Mechanism | Status |
|---|---|
| Broker authentication | **None** — `allow_anonymous true` |
| TLS / encryption | **None** — plaintext MQTT 1883 |
| Device authentication | **None** — any client may claim any node id |
| Authorisation | **None** |
| Web authentication | **None** |
| Credential handling | **Plaintext in firmware source, committed to git** |
| Discovery integrity | **None** — any host may broadcast a broker address |

### Major gaps

Any device on the network can open every door, silence the alarm, or
dispense medication. The discovery beacon is unauthenticated, so an
attacker can redirect nodes to a hostile broker. `setup_broker.ps1`
carries a warning to this effect.

**Privacy:** audio is transcribed locally and never leaves the machine
— a genuine privacy property, and the only defensible security-adjacent
claim. Whether recordings persist on disk: `NEEDS VERIFICATION`
(`command.wav` exists in the repository root).

**Do not describe this system as secure.**

---

# SECTION U — RELIABILITY AND FAULT HANDLING

| Mechanism | Implemented | Tested |
|---|---|---|
| Per-action timeout (5 s) | yes | yes |
| Retry ×2 with stable id | yes | **yes, measured** |
| Node-side dedup | yes | **yes, controlled** |
| Unknown device/action → error | yes | yes, bench suite |
| Unwired device → error | yes | yes |
| Wi-Fi reconnect + report | yes | observed |
| Broker re-discovery after 3 failures | yes | **observed in the wild** |
| MQTT keepalive 15 s | yes | — |
| Crash detection via `clean_shutdown` | yes | 36 tests |
| Atomic snapshot + `.bak` | yes | 26 tests |
| All-or-nothing restore | yes | yes |
| Emergency latch survives restart | yes | yes |
| Watchdog timer | **no** | — |
| Heartbeat / offline detection | **no** | — |
| Actuator stall detection | **no — impossible without sensors** | — |

**Failures actually injected:** node unreachable (permanent), node
unreachable (transient, 6 s). **Not injected:** physical actuator
block, message dropping, broker failure, controller crash mid-workflow,
power loss.

---

# SECTION V — POWER AND RESOURCE ANALYSIS

**Nothing in this category was measured.**

Battery voltage, capacity, current draw, peak current, power
consumption, runtime, converter efficiency, CPU utilisation, memory
utilisation, communication overhead: **all NOT MEASURED.**

No derived values are offered, because no inputs exist to derive from.

The only power-related observation is qualitative: powering an ESP32
through its 3V3 pin from a shared breadboard supply caused repeated
brownouts under Wi-Fi transmission, resolved by USB power with a
separate servo rail and common ground. **Observational, uninstrumented,
n = 1.**

---

# SECTION W — FIGURES AND TABLES FOR THE PAPER

| # | Figure/Table | Shows | Data exists? | Still needed |
|---|---|---|---|---|
| 1 | System architecture | 5 layers, 3 nodes | **yes** | redraw |
| 2 | Hardware block + pin map | 10 devices, GPIO | **yes** | draw |
| 3 | Voice→actuation pipeline | full path | **yes** | draw |
| 4 | Message sequence with ack/complete | two-phase reply, dedup branch | **yes** | draw |
| 5 | Per-action latency, split | dispatch→ack vs ack→complete, 10 devices | **yes** | plot |
| 6 | Dedup control | 0/4 vs 4/4 | **yes** | plot |
| 7 | Emergency degradation | 2335 vs 32256 ms | **yes** | plot |
| 8 | Reliability, 3 conditions | completion, retries, recovery | **yes** | plot |
| 9 | Per-intent P/R/F1, holdout | recognition | **yes** | plot |
| 10 | Confusion matrix, holdout | zero off-diagonal | **yes** | plot |
| 11 | Hardware table | components | **yes** | tabulate |
| 12 | Software stack table | versions | **mostly** | fill 4 versions |
| 13 | Testbed photograph | rig | **no** | **take one** |
| 14 | Scheduler comparison | proposed vs fixed-delay | **NO** | **build baseline** |
| 15 | τ sweep | accuracy vs rejection | **NO** | run sweep |
| 16 | End-to-end latency budget | STT + embed + plan + actuate | **NO** | instrument |

---

# SECTION X — PAPER SECTION MAPPING

| IEEE Section | Available | Missing |
|---|---|---|
| Abstract | all headline numbers | the claim itself — depends on framing |
| Introduction | mechanisms and their rationale | motivation, citations |
| Related Work | **nothing** | entire section; SmartAid/HearthNet positioning |
| Problem Statement | inferred from mechanisms | any written statement |
| Proposed System | complete | — |
| System Architecture | complete, code-verified | diagrams |
| Methodology | algorithms J1–J9 | complexity analysis |
| Implementation | 33 modules, firmware, pin map | CPU/RAM spec |
| Experimental Setup | conditions, trial counts, injection method | host spec, duration, baseline |
| Results | §O in full | end-to-end latency, scheduler comparison, power |
| Discussion | degradation, containment, silent success | — |
| Limitations | 17 items | — |
| Conclusion | derivable | — |
| Future Work | derivable from gaps | — |

---

# SECTION Y — CLAIM AUDIT

| Claim | Evidence | Strength | Quantitative? | Safe for IEEE? |
|---|---|---|---|---|
| Retries do not re-actuate hardware | 40/40 vs 4/4 controlled | strong | yes | **YES** |
| Re-execution detectable from ACK latency | 72× separation | strong | yes | **YES, WITH QUALIFICATION** — state the instant-device limit |
| Emergency intents never misrouted | precision 1.00, holdout | strong | yes | **YES, WITH QUALIFICATION** — n=110, single τ |
| Best-effort execution degrades 13.8× | 4+4 trials | strong | yes | **YES** |
| Fail-fast containment is 1.0 | 30/30 | strong | yes | **YES, WITH QUALIFICATION** — define as implemented |
| Transient failures recover fully | 6/6 | moderate | yes | **YES, WITH QUALIFICATION** — n=6 |
| State commits only for acknowledged actions | code + tests | strong | partly | **YES, WITH QUALIFICATION** — ACK ≠ movement for servos |
| System is "real-time" | none | none | no | **NO** |
| System is "reliable" | fault tests only | partial | partly | **NO** unqualified |
| System is "secure" | none | none | no | **NO** |
| System is "novel" | none | none | no | **NO** |
| System is "low-cost" | no costing | none | no | **NO** |
| System is "energy-efficient" | no power data | none | no | **NO** |
| System is "scalable" | 3 nodes, no study | none | no | **NO** |
| Reduces user interaction burden | analytic only | weak | derivable | **YES, WITH QUALIFICATION** — analytic, not a usability finding |
| Sensor-gated completion | **contradicted** | none | no | **NO — no sensors exist** |

---

# SECTION Z — MISSING INFORMATION AUDIT

### CRITICAL MISSING
1. **Fixed-delay baseline** — without it, no ordering-violation or
   silent-success numbers, and the headline comparison cannot be made.
2. **End-to-end latency** — STT and embedding inference unmeasured.
3. **Ground-truth actuation sensing** — one position sensor would
   convert the central claim from argued to measured.
4. **Related-work positioning** against SmartAid and HearthNet.
5. **Problem statement and objectives** — none written.

### IMPORTANT MISSING
6. Controller CPU/RAM; total experiment duration.
7. τ sweep.
8. Hardware-fault injection (physically blocking a servo).
9. Dataset provenance — generation method, split method, manual review.
10. Larger n for medication (3) and EMERGENCY (4).
11. Buzzer and power-supply model numbers.

### NICE TO HAVE
12. Power and CPU/RAM measurements.
13. Persistence write latency.
14. Multi-session repeatability across RF conditions.
15. Third node physical.
16. Testbed photograph.

---

# SECTION AA — CONTRADICTION AUDIT

| Topic | Statement A | Statement B | Conflict | Verify |
|---|---|---|---|---|
| Node count | Intake sheet: "all five nodes integrated" | Registry: 3 nodes, 2 physical | **Direct** | Registry is authoritative |
| Sensor gating | Intake: "Access Node gates COMPLETE on a real door sensor" | Firmware: no `digitalRead`, no input pin | **Direct, most serious** | Firmware is authoritative |
| Scheduler comparison | Intake: "both schedulers compared" | No baseline in codebase | **Direct** | Codebase authoritative |
| Device names | Intake: `access01`, `mobility01`, `care01` | Registry: `sleep_door`, `exit_door`, … | **Direct** | Registry authoritative |
| Action names | Intake: `MOVE_FORWARD`, `BED_UP` | `ActionType` enum | **Direct** | Enum authoritative |
| Intent count | Intake: 10 intents | Dataset: 11 | **Minor** | Dataset authoritative |
| Task-status vocabulary | Intake: `DISPATCHED`/`RETRY_WAIT`/`CANCELLED` | Implemented: `status ∈ {success,error}`, `phase ∈ {ack,complete}` | **Direct** | Redraw Algorithm 1 and Fig. 4 |
| Recognition accuracy | 0.752 (validation) | 0.718 (holdout) | **Apparent** | Different sets; report holdout, disclose both |
| Servo latency | 774 ms (§2, early run) | 702 ms (§3, later run) | **Apparent** | Different runs; ~700 ms delay dominates both |

**The first five contradictions all originate in the intake sheet, not
in this repository.** Filling that sheet as written would place
unsupported claims in the paper.

---

# SECTION AB — REPRODUCIBILITY AUDIT

| Item | Available |
|---|---|
| Hardware specification | partial — boards and servos yes; buzzer and supply no |
| Wiring | **yes** — pin map in firmware, plus documented rules |
| Software dependencies | **yes** — versions for 8 of 12 |
| Configuration | **yes** — all constants in source |
| Algorithms | **yes** — source is the specification |
| Parameters | **yes** — τ=0.65, timeout 5 s, retries 2, delay 700 ms |
| Dataset | **yes** — 313/110/105 in `data/` |
| Training procedure | n/a — nothing trained |
| Communication protocol | **yes** — topics, payloads, phases |
| Deployment instructions | partial — broker script yes; no end-to-end runbook |
| Test conditions | **yes** — conditions and trial counts recorded |
| Evaluation procedure | **yes** — every result re-runnable from a named command |

### Reproducibility score: 8/10

**Why 8:** every measurement in `RESULTS.md` names the command that
produces it; 450 tests pin behaviour; the dataset ships; firmware
constants are explicit; the protocol is fully specified.

**Why not higher:** the controller host specification is unrecorded, so
CPU-bound timings cannot be reproduced; the servo power supply is
unspecified, and it demonstrably affects results; and two results
(actuation, and the dedup dose count) depend on human visual
confirmation that a reproducer cannot verify from the artefact.

---

# SECTION AC — IEEE-QUALITY READINESS AUDIT

| Criterion | Rating | Basis |
|---|---|---|
| Clearly defined research problem | **Weak** | inferred from mechanisms, never stated |
| Research gap | **Weak** | no related-work grounding; prior audit suggests pre-emption |
| Technical contribution | **Moderate** | idempotency result and latency method are real |
| Novelty potential | **Moderate** | the latency-based detection method is the strongest candidate |
| Methodological rigor | **Strong** | controlled single-variable experiments, stated limits |
| Experimental rigor | **Moderate** | good conditions and trial counts; small n on two metrics |
| Quantitative evaluation | **Strong** | 25+ measured quantities with n and spread |
| Baseline comparison | **Missing** | no baseline scheduler |
| Reproducibility | **Strong** | 8/10 |
| Limitations | **Strong** | 17 identified, including one that undercuts own data |
| Security / privacy | **Weak** | none implemented; local-only audio is the sole positive |
| Scalability | **Missing** | 3 nodes, no study |

### IEEE PAPER READINESS: 6/10

**Justification.** The experimental and reproducibility work is
genuinely strong — controlled comparisons, honest negative results, a
limitation that undercuts the project's own measurements and is
reported anyway. That is above typical student-project standard.

Three things hold the score at 6: **no baseline** for the comparison
the paper is organised around; **no related-work positioning**, with a
prior audit suggesting the headline claim is pre-empted; and **no
stated problem or objectives**, so motivation must be reconstructed.

The first is a day of engineering. The second is a week of reading. The
third is an afternoon of writing. **None require new hardware.** With
all three, this would sit at 8/10.

---

# SECTION AD — MASTER PROJECT KNOWLEDGE BASE

**1. Identity.** Assistive Orchestration: voice-controlled,
state-conditioned, distributed home orchestration over MQTT with
idempotent ESP32 actuation.

**2. Problem.** Not stated; inferable — a retried command can actuate
twice, and a dispatched command can be recorded as done without having
happened.

**3. Gap.** Idempotent, acknowledgement-gated actuation for
safety-critical assistive commands. **Requires literature validation.**

**4. Objectives.** Reconstructed, §D. 6 fully achieved, 2 partially, 1
not implemented.

**5. Solution.** Speech → embedding retrieval with rejection →
state-conditioned planning → MQTT dispatch with stable ids → node
dedup → ACK-gated two-tier commit → atomic persistence.

**6. Architecture.** 5 layers, 18 components, §E.

**7. Hardware.** 2× ESP32-WROOM-DA, 6× SG90, 3 LED, 1 buzzer. Pin map
§F. No sensors.

**8. Software.** Python 3.11.9, faster-whisper base int8,
all-MiniLM-L6-v2, paho 2.1.0, Flask, Mosquitto; Arduino core 3.3.11
with PubSubClient 2.8 / ArduinoJson 7.4.3 / ESP32Servo 3.2.1.

**9. Communication.** MQTT QoS 1 on two topics; two-phase reply
(ack/complete); UDP 18830 discovery; HTTP UI. No security.

**10. Algorithms.** J1–J9: max-over-sentences retrieval, idempotent
retry, node dedup, two-tier commit, per-intent failure policy,
emergency latch, location certainty, corridor invariant, crash
detection.

**11. Data flow.** §I. Distributed, edge-actuated, entirely local.

**12. Interaction.** 7 HTTP endpoints, explicit confirmation, console
loop, `where <room>` recovery.

**13. Experimental setup.** §N. 2 physical nodes, 10 devices, 2.4 GHz
hotspot, no baseline.

**14. Results.** §O. 25+ measured quantities.

**15. Baseline.** **None.** Two internal controlled comparisons.

**16. Contributions.** 5 candidates: 3 strongly supported, 2
moderately.

**17. Novelty.** One strong candidate — latency-based idempotency
verification for feedback-less actuators. All require literature
comparison.

**18. Limitations.** 17, §S. The most important: an ACK does not prove
a servo moved, and this failure actually occurred during data
collection.

**19. Missing evidence.** 5 critical, 6 important, 5 nice-to-have.

**20. Contradictions.** 9, of which 5 originate in the external intake
sheet and are resolved against this repository.

**21. Reproducibility.** 8/10.

**22. IEEE readiness.** 6/10.

---

# APPENDIX — DESIGN RATIONALE

The brief asks why particular choices are better. Each is a real
trade-off with a cost.

### Stable `command_id` across retries
**Why.** A fresh id per attempt makes a retry indistinguishable from a
new command; the node cannot deduplicate what it cannot recognise.
**Cost.** The node must keep history (32 entries), and an id colliding
across a reboot would suppress a real command.

### Node-side dedup rather than broker-side
**Why.** The node is the only component that knows whether its hardware
already moved. Broker-level exactly-once delivery would not help: the
danger is re-actuation, not re-delivery.
**Cost.** Every node must implement it correctly; a wrong node
silently breaks the guarantee.

### Two-tier commit
**Why.** A workflow that fails halfway must not leave a claimed mode.
Device state is evidence-backed per action; room/mode are conclusions
that require the whole workflow.
**Cost.** Two commit points to reason about, and partial device state
after an abort.

### Acknowledgement before dedup check
**Why.** It separates transport cost from actuation cost, and makes a
replay measurable — a duplicate shows ack→complete near zero.
**Cost.** Two messages per command; every consumer must filter
`phase`, which is exactly what broke the executor until it was fixed.

### Rejection over substitution (τ = 0.65)
**Why.** A rejected command is visible to the user and can be repeated.
A substituted one silently does the wrong thing — and for `EMERGENCY`
that could be fatal. Holdout precision 1.00 with 0.282 rejection is the
intended trade.
**Cost.** Nearly a third of valid utterances refused; `LEAVE_ROOM`
recall 0.20.

### Max-over-sentences rather than centroid
**Why.** One strong paraphrase should carry the intent, and a centroid
would be dragged by the 19–58 sentence imbalance.
**Cost.** Sensitive to a single bad reference sentence.

### `LocationStatus` not a `Room` member
**Why.** Making `UNKNOWN` a room would let it flow silently into
planning and be treated as a place. As a separate axis it must be
handled explicitly, and location-dependent intents refuse.
**Cost.** Every location consumer must check two fields.

### Best-effort emergency, fail-fast otherwise
**Why.** An evacuation must open every door it can reach; a sleep
routine should stop rather than half-complete.
**Cost.** Measured — 13.8× degradation, because best-effort waits out
every unreachable device serially.

### Per-device `wired` flag
**Why.** A half-populated board otherwise reports success for empty
pins, which is the exact failure the project exists to prevent. This
was not hypothetical: it corrupted an EMERGENCY measurement before the
flag existed.
**Cost.** The table must be kept truthful by hand.

### Atomic snapshot with `clean_shutdown` written false at startup
**Why.** A crash cannot write a marker, so the absence of an orderly
shutdown must be the default assumption.
**Cost.** A write on every startup, and a hard crash mid-write relies
on `os.replace` atomicity plus the `.bak`.

### No automatic replay after restart
**Why.** Replaying `ACTIVATE_MEDICATION` after a crash could dispense a
second dose, and the system cannot know whether the first one landed.
**Cost.** An interrupted workflow needs a human to reissue it.
