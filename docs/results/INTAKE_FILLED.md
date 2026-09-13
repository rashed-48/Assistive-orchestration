# Results data intake — filled from measured data

Every figure below traces to a script in this repository or a logged
run. Cells that were not measured are left blank and named as blank.
Nothing is estimated or reconstructed.

---

## ⚠ CORRECTIONS TO THE SHEET'S PREMISES

The intake sheet's status line asserts five things. **Four are not true
of this system.** They must be corrected before any section is filled,
because each one, taken at face value, would put an unsupported claim
in the paper.

| Sheet asserts | Actual |
|---|---|
| "all five nodes integrated" | **Three nodes exist** — `esp32_a`, `esp32_b`, `esp32_c`. Two are physical; `esp32_c` is a software simulation. |
| "Access Node gates `COMPLETE` on a real door sensor" | **No sensor of any kind exists.** The firmware contains no `digitalRead`, no input pin, no sensor. `COMPLETE` is emitted after a fixed 700 ms delay, with no confirmation the actuator moved. |
| "both schedulers compared" | **Only one scheduler is implemented.** There is no fixed-delay baseline anywhere in the codebase. Experiment 3 has not been run. |
| "fault-injection results" | **Partially true.** Communication failure was injected and measured. Hardware-failure and heartbeat/offline paths were not. |
| "timing logs from real runs" | True. |

The sheet also names devices (`access01`, `mobility01`, `care01`) and
actions (`MOVE_FORWARD`, `BED_UP`) that do not exist in this system.
The real inventory is in §1 below.

**The door-sensor claim matters most.** This system's central
contribution is that acknowledgement-gated commit can report success
for hardware that never moved. Claiming a sensor gates `COMPLETE`
would assert exactly the property the system does not have — and
during data collection this failure actually occurred: six servos lost
power and every one reported `success`, with `PREPARE_FOR_SLEEP`
committing `sleep_bed = READY`. See Limitations.

---

## 0. INTEGRITY CHECKS

### 0.1 Intent accuracy — was the test set disjoint?

**Answer: Yes, with a caveat, and there is a cleaner set available.**

| Set | n | Exact overlap with reference | Near-duplicates (Jaccard ≥ 0.8) |
|---|---|---|---|
| `validation.csv` | 105 | **0** | **7** |
| `holdout.csv` | 110 | **0** | **4** |

Reference (`intents.csv`): 313 sentences, all unique.

No test sentence appears verbatim in the reference set. Seven
validation sentences are close paraphrases of reference sentences, e.g.
`"Settle the room down for the night"` against `"Settle the room for
the night"`. That is paraphrase-family leakage, and it inflates
validation numbers slightly.

**Recommendation: report `holdout.csv`.** It is balanced at exactly 10
per intent, has fewer near-duplicates, and produces the stronger safety
result (§2).

**Split:** 313 reference · 110 holdout · 105 validation. Selection
method for the splits is **not recorded** — this needs your answer.

### 0.2 Fixed-delay baseline — how was δ chosen?

**Cannot be answered. The baseline does not exist.**

No fixed-delay scheduler is implemented. `grep` over the codebase finds
no such module. **Experiment 3 — the sheet's headline — has not been
run and cannot be filled from existing data.** See §4.

---

## 1. TESTBED AND PROTOCOL FACTS

| Item | Value |
|---|---|
| Controller OS | Windows 11 (10.0.26200) |
| Controller Python | 3.11.9 |
| CPU / RAM class | **not recorded** |
| Network | 2.4 GHz Wi-Fi, phone hotspot, shared AP; RSSI −48 to −57 dBm |
| MQTT broker | Mosquitto, on the controller machine, **QoS 1** |
| Broker discovery | UDP broadcast, port 18830, 2 s interval |
| ESP32 nodes active | **2 physical** (`esp32_a`, `esp32_b`) + 1 simulated (`esp32_c`) |
| Board | ESP32-WROOM-DA |
| Firmware toolchain | Arduino, esp32 core 3.3.11; PubSubClient 2.8, ArduinoJson 7.4.3, ESP32Servo 3.2.1 |
| STT engine | Whisper, offline |
| Embedding model | `all-MiniLM-L6-v2`, sentence-transformers 5.7.0 |
| Confidence threshold τ | **0.65** |
| Retry count R | **2** (3 total attempts) |
| Timeout per action | **5 s** |
| Timeouts measured or judged? | **Judged.** Not derived from measured actuation times. Measured actuation is 14–28 ms (instant devices) and 691–2002 ms (servos), so 5 s is ~2.5× the slowest action. |
| paho-mqtt / scikit-learn | 2.1.0 / 1.9.0 |
| Experiment date | 2026-08-29 to 2026-08-30 |
| Total duration | **not recorded** |

**Topic structure:** `assistive/command/<node_id>` and
`assistive/status/<node_id>`, QoS 1 both directions.

### Physical device inventory

| Node | Physical? | Devices |
|---|---|---|
| `esp32_a` | yes | `drawing_light` (LED), `relax_light` (LED), `buzzer`, `relax_tv` (servo), `exit_door` (servo), `relax_door` (servo) |
| `esp32_b` | yes | `sleep_light` (LED), `sleep_door` (servo), `sleep_bed` (servo), `medication_servo` (servo) |
| `esp32_c` | **simulated** | `study_light`, `meal_light`, `study_door`, `meal_door`, `study_table`, `meal_table` |

**10 physical devices**: 3 LEDs, 1 buzzer, 6 SG90 servos.

### Action vocabulary (authoritative — answers §6 Q4)

`OPEN_DOOR`, `CLOSE_DOOR`, `LIGHT_ON`, `LIGHT_OFF`, `TV_ON`, `TV_OFF`,
`PREPARE_TABLE`, `RESET_TABLE`, `PREPARE_BED`, `RESET_BED`,
`ACTIVATE_MEDICATION`, `BUZZER_ON`, `BUZZER_OFF`

Form is `LIGHT_ON`, not `TURN_LIGHT_ON`.

### Workflows

| Workflow | Tasks | Nodes | Parallel branch? | Used in |
|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 2 | esp32_b | no | E2, E4 |
| WAKE_UP | 1 | esp32_b | no | E2 |
| MEDICATION | 1 | esp32_b | no | E2, E4 |
| RELAX_MODE | 2 | esp32_a | no | E2 |
| STUDY_MODE | 2 | esp32_c | no | E2 |
| PREPARE_FOR_MEAL | 2 | esp32_c | no | E2 |
| SHUTDOWN_ENVIRONMENT | 11 | all 3 | no | E2, E4 |
| EMERGENCY | 6 | all 3 | no | E2, E4 |
| EMERGENCY_CLEAR | 6 | all 3 | no | E4 |
| LEAVE_ROOM | — | — | no | not measured |
| RETURN_TO_ROOM | — | — | no | not measured |

**No workflow contains a parallel branch. Execution is strictly
serial.** This is measurable in its consequences — see §4 note on
emergency degradation.

**Intents recognized: 11. Intents with executable workflows: 11.**
(The sheet assumes 10; there are 11, including `EMERGENCY_CLEAR`.)

---

## 2. EXPERIMENT 1 — INTENT RECOGNITION

**Dataset as built:**

| Item | Value |
|---|---|
| Intents | 11 |
| Reference sentences | 313, uneven: 19 (MEDICATION) to 58 (EMERGENCY) |
| Holdout | 110, balanced 10 per intent |
| Validation | 105, 8–10 per intent |
| Generation method | **not recorded** — needs your answer |
| Manual review performed? | **not recorded** |

### Overall — holdout (recommended for the paper)

| Metric | Value | n |
|---|---|---|
| Accuracy | **0.718** | 110 |
| Macro precision | 0.92 | 110 |
| Macro recall | 0.66 | 110 |
| Macro F1 | 0.74 | 110 |
| Weighted precision | **1.00** | 110 |
| Weighted F1 | 0.81 | 110 |
| Rejection rate | **0.282** | 110 |

### Overall — validation (for comparison)

| Metric | Value | n |
|---|---|---|
| Accuracy | 0.752 | 105 |
| Macro F1 | 0.75 | 105 |
| Weighted F1 | 0.82 | 105 |
| Rejection rate | 0.162 | 105 |

### Per-intent — holdout

| Intent | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 1.00 | 1.00 | 1.00 | 10 |
| LEAVE_ROOM | 1.00 | 0.20 | 0.33 | 10 |
| RETURN_TO_ROOM | 1.00 | 0.60 | 0.75 | 10 |
| PREPARE_FOR_MEAL | 1.00 | 1.00 | 1.00 | 10 |
| MEDICATION | 1.00 | 1.00 | 1.00 | 10 |
| STUDY_MODE | 1.00 | 0.50 | 0.67 | 10 |
| RELAX_MODE | 1.00 | 0.50 | 0.67 | 10 |
| EMERGENCY | 1.00 | 0.90 | 0.95 | 10 |
| EMERGENCY_CLEAR | 1.00 | 0.90 | 0.95 | 10 |
| SHUTDOWN_ENVIRONMENT | 1.00 | 0.60 | 0.75 | 10 |
| WAKE_UP | 1.00 | 0.70 | 0.82 | 10 |

### Top confusions

**There are none on the holdout set.** Precision is 1.00 for every
intent, so **not one utterance was routed to a different intent**. All
31 errors are rejections.

This is the strongest safety claim available: the failure mode is
refusal, which surfaces to the user, never substitution, which does
not. `LEAVE_ROOM` at 0.20 recall is the weakest — 8 of 10 rejected —
but none misrouted.

On validation, misclassification does occur: `PREPARE_FOR_SLEEP`
absorbs 3 from `WAKE_UP` and 2 from `SHUTDOWN_ENVIRONMENT`, giving 0.54
precision. This is consistent with the paraphrase leakage found in 0.1.

**τ sweep: not run.** Single operating point 0.65. Worth doing — the
sheet is right that it makes a strong small figure, and it would
justify the 0.282 rejection rate on holdout.

---

## 3. EXPERIMENT 2 — WORKFLOW EXECUTION

**N = 8 per workflow** unless stated.

| Workflow | N | Completion rate | Task success | Latency median (ms) | p95 |
|---|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 8 | 100% | 100% | 769 | 1041 |
| WAKE_UP | 8 | 100% | 100% | 730 | 931 |
| MEDICATION | 8 | 100% | 100% | 1957 | 2054 |
| SHUTDOWN_ENVIRONMENT | 8 | 100% | 100% | 828 | 1031 |
| EMERGENCY | 4 | 100% | 100% | 2335 | 2712 (max) |
| RELAX_MODE | 8 | 100% | 100% | 2 | 3 |
| STUDY_MODE | 8 | 100% | 100% | 2 | 3 |
| PREPARE_FOR_MEAL | 8 | 100% | 100% | 2 | 3 |

The last three touch **only the simulated node** and carry no hardware
timing. They must be marked as such in the paper.

### Per-task latency, decomposed

The node emits `ack` on arrival and `complete` after actuation, so the
two legs are measured, not inferred. **n = 10 per device** (3 for
medication).

| Task (node, action, device) | n | t_ACK − t_COMMAND (ms) | t_COMPLETE − t_ACK (ms) | Total (ms) |
|---|---|---|---|---|
| esp32_b LIGHT_ON `sleep_light` | 10 | 13 | 54 | 66 |
| esp32_b OPEN_DOOR `sleep_door` | 10 | 15 | 702 | 717 |
| esp32_b PREPARE_BED `sleep_bed` | 10 | 14 | 699 | 713 |
| esp32_b ACTIVATE_MEDICATION | 3 | 19 | 1896 | 1915 |
| esp32_a LIGHT_ON `drawing_light` | 10 | 14 | 61 | 75 |
| esp32_a LIGHT_ON `relax_light` | 10 | 16 | 58 | 74 |
| esp32_a BUZZER_ON `buzzer` | 10 | 19 | 58 | 77 |
| esp32_a TV_ON `relax_tv` | 10 | 16 | 704 | 721 |
| esp32_a OPEN_DOOR `exit_door` | 10 | 15 | 704 | 718 |
| esp32_a OPEN_DOOR `relax_door` | 10 | 18 | 698 | 716 |

`t_ACK − t_COMMAND` is **13–19 ms on every device regardless of type** —
transport cost, isolated.

**`t_COMPLETE − t_ACK` must be described precisely.** It is the node's
actuation *sequence* duration, not proof of movement. The firmware
writes the PWM signal, waits a **fixed 700 ms**, then acknowledges. An
unpowered servo yields the same number. The six servos returning
698–704 ms is consistent with the constant, not independent evidence of
actuation.

**Parallel execution: implemented but not exercised — actually, not
implemented.** Execution is strictly serial. Max concurrent tasks
observed: **1**.

---

## 4. EXPERIMENT 3 — SCHEDULER COMPARISON

## **CANNOT BE FILLED. NOT RUN.**

No fixed-delay baseline scheduler exists in the codebase. Without it:

- the comparison grid is entirely blank
- **ordering violations** were never instrumented and cannot be
  recovered retrospectively, because there is no second scheduler whose
  ordering could be violated
- **silent successes** were not measured systematically

The sheet calls this the headline experiment. **It is the single
largest gap between what the paper plans and what exists.**

### What does exist, and is adjacent

**One silent success was observed, unplanned.** During data collection
the servo supply failed. All six servos reported `success` with
`t_COMPLETE − t_ACK` of 691–704 ms, and `PREPARE_FOR_SLEEP` committed
`sleep_bed = READY`. Ground truth was established by **manual
observation** — a person looked at the rig. This is a real instance of
the failure the paper is about, but n = 1 and it was not a controlled
condition.

**A deduplication control experiment was run**, which is structurally
similar to what Experiment 3 wants — same hardware, same commands, one
firmware variable (`DEDUP_ENABLED`):

| Device | Replay, dedup ON | Replay, dedup OFF | Re-executed ON | Re-executed OFF |
|---|---|---|---|---|
| `sleep_door` | 33 ms | 717 ms | **0/4** | **4/4** |
| `sleep_bed` | 12 ms | 714 ms | **0/4** | **4/4** |
| `medication_servo` | 27 ms | 1915 ms | **0/4** | **4/4** |
| `sleep_light` | 25 ms | 14 ms | not separable | not separable |

Without deduplication every replay re-ran the actuation sequence. On
`medication_servo` that is five dose cycles where one was intended.
Detection is by timing: a reply from stored state costs transport
alone. The method cannot decide anything for an instant device, which
is stated rather than hidden.

**Emergency degradation under partial failure was measured** (4 trials
per condition):

| Condition | median (ms) | min | max | succeeded | failed |
|---|---|---|---|---|---|
| All 6 devices reachable | **2335** | 2211 | 2712 | 6 | 0 |
| 2 of 6 unreachable | **32256** | 32237 | 32435 | 4 | 2 |

**13.8× degradation.** Best-effort policy holds — every reachable door
opened — but dispatch is serial, so each unreachable device contributes
its full 15 s of retries to a workflow whose purpose is speed.

---

## 5. EXPERIMENT 4 — FAULT RECOVERY

Partially filled. 4 intents × 3 trials per condition.

| Fault type | Injections | Detected | Detection latency | Recovered after retry | Mean retries | Dependents cancelled |
|---|---|---|---|---|---|---|
| Communication failure (node unreachable) | 12 workflows / 30 tasks | 100% | ~15 s (3 × 5 s timeout) | **0%** (permanent) | 2.0 | **100%** |
| Communication failure (node returns mid-workflow) | 12 workflows / 60 tasks | 100% | ~5 s | **100% (6/6)** | 1.8 | n/a |
| Hardware failure (actuator blocked/stalled) | **not run** | | | | | |
| Timeout (actuation exceeds task timeout) | **not run** | | | | | |
| Node offline before start (heartbeat) | **not run — heartbeat not implemented** | | | | | |

**How faults were injected:** the simulated node process was killed
(permanent condition) or killed and restarted 6 s later (transient
condition). Injection was **software-level process termination**, not
physical power-down or message dropping.

**Identical across both schedulers:** n/a — only one scheduler exists.

### Failure containment

**1.0 across all trials**, for the fail-fast path.

`SHUTDOWN_ENVIRONMENT` plans 33 tasks over 3 trials. With one node
unreachable, 3 tasks were dispatched, all failed after retries, the
workflow aborted, and **30 of 33 planned tasks were never dispatched**.
No command was pushed at a device whose workflow had already failed.

`EMERGENCY` shows containment **0 by design** — it is best-effort and
dispatches all 18 tasks regardless, because an emergency must reach
every door it can.

**Note on terminology:** this system has no task DAG and no `CANCELLED`
state. Containment here means *planned actions never dispatched after a
fail-fast abort*, which is what the code actually guarantees. The
sheet's "dependents correctly CANCELLED" implies a dependency graph
that does not exist.

### Reliability summary

| Condition | Workflow completion | Task success | Retry rate | Recovery |
|---|---|---|---|---|
| All nodes reachable | **12/12** | **60/60** | 0 | n/a |
| One node unreachable | 9/12 | 21/30 | 0.60 | 0/9 |
| Node returns mid-workflow | **12/12** | **60/60** | 0.18 | **6/6 (100%)** |

**Heartbeat:** not implemented. Interval, threshold and detection
latency are all blank.

---

## 6. REMAINING DESIGN DECISIONS

| # | Question | Answer |
|---|---|---|
| 1 | Fixed task graphs or runtime state guards? | **Neither purely.** Workflows are selected by intent, then the planner consults logical state (room, mode, location certainty, emergency latch) to decide which actions are needed. Preconditions are checked at plan time, not carried as per-task guards. |
| 2 | MQTT the only transport? | **Yes.** No HTTP transport was ever built. |
| 3 | QoS and topics | QoS 1. `assistive/command/<node>`, `assistive/status/<node>`. Plus UDP broadcast on 18830 for broker discovery. |
| 4 | Action vocabulary | `LIGHT_ON` form. Full list in §1. |
| 5 | Task-status vocabulary | Neither set. The implemented reply is `{command_id, node, device, action, status, phase}` where `status ∈ {success, error}` and `phase ∈ {ack, complete}`. There is no `DISPATCHED`/`RETRY_WAIT`/`CANCELLED` enum. **Algorithm 1 and Fig. 4 must be redrawn to match.** |
| 6 | Descendant or immediate-child cancellation? | **Neither.** On failure an ordinary workflow raises and abandons all remaining actions; there is no cancellation mechanism. |
| 7 | Emergency pre-emption | **Implemented and tested.** EMERGENCY latches the environment; ordinary intents are refused with `EmergencyActive` until `EMERGENCY_CLEAR`. Verified on physical hardware: refusal demonstrated, not asserted. |

---

## 7. PAPER METADATA

All blank — needs your answers. Testbed photograph: **available if you
take one**; the rig is currently assembled with 10 physical devices.

---

## WHAT IS MISSING, RANKED

1. **Experiment 3 in full.** No baseline scheduler exists. This is the
   sheet's headline and the paper's central comparison. Building a
   fixed-delay executor is perhaps a day's work; without it, ordering
   violations and silent successes cannot be reported as measurements.
2. **Ground-truth actuation sensing.** Every servo result rests on the
   firmware's fixed delay. One silent success was observed by eye. A
   limit switch or potentiometer tap on one door would convert the
   paper's central claim from argued to measured.
3. **Hardware-fault injection** — physically blocking a servo. Cheap to
   do and fills a row of Experiment 4.
4. **τ sweep** — one afternoon, produces a figure, justifies 0.65.
5. **Heartbeat/offline detection** — not implemented; either build it
   or drop that row.
6. **Dataset provenance** — how sentences were generated and split, and
   whether they were manually reviewed. Needed for §2.
7. **Controller hardware spec and total experiment duration** — trivial
   to record.
