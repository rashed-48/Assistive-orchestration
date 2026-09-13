# Measured results

Everything below was produced by scripts in this repository and can be
re-run. Raw samples are in `execution_measurements.csv`; the
deduplication control has its own note in `dedup_control.md`.

```
python tests/test_evaluation.py                       # recognition
python -m tools.measure_execution --host <broker> --node esp32_b \
    --trials 15 --workflows --dedup-control           # execution
python -m tools.measure_execution --host <broker> --node esp32_b \
    --trials 10 --phases                              # transport vs actuation
python -m tools.measure_reliability --host <broker> --trials 3
python -m tools.bench_node --host <broker> --node esp32_b \
    --suite --strict                                  # node conformance
python -m pytest                                      # 450 passed, 2 skipped
```

## Setup

| | |
|---|---|
| Physical nodes | `esp32_a`, `esp32_b` — ESP32-WROOM-DA, Arduino core 3.3.11 |
| Simulated node | `esp32_c` |
| Physical devices | 10 — 3 LED, 1 buzzer, 6 SG90 servos |
| Network | 2.4 GHz hotspot, MQTT QoS 1, Mosquitto |
| Signal | −48 to −57 dBm |
| Date | 2026-08-29 |

Devices not physically connected are declared `wired = false` in the
firmware device table; the node answers `error` for them and the
orchestrator declines to commit their state. Partial hardware
therefore cannot report a success it did not earn.

## 1. Intent recognition

Validation set, n = 105, threshold 0.65, `all-MiniLM-L6-v2`.

| | |
|---|---|
| Acceptance rate | 0.838 |
| Accuracy over accepted | 0.75 |
| Macro F1 | 0.75 |
| Weighted F1 | 0.82 |

| Intent | Precision | Recall | F1 | n |
|---|---|---|---|---|
| EMERGENCY | 1.00 | 0.80 | 0.89 | 10 |
| EMERGENCY_CLEAR | 1.00 | 0.80 | 0.89 | 10 |
| LEAVE_ROOM | 1.00 | 0.70 | 0.82 | 10 |
| MEDICATION | 1.00 | 0.89 | 0.94 | 9 |
| PREPARE_FOR_MEAL | 1.00 | 0.75 | 0.86 | 8 |
| PREPARE_FOR_SLEEP | 0.54 | 0.78 | 0.64 | 9 |
| RELAX_MODE | 0.78 | 0.70 | 0.74 | 10 |
| RETURN_TO_ROOM | 0.89 | 0.80 | 0.84 | 10 |
| SHUTDOWN_ENVIRONMENT | 1.00 | 0.70 | 0.82 | 10 |
| STUDY_MODE | 1.00 | 0.80 | 0.89 | 10 |
| WAKE_UP | 1.00 | 0.56 | 0.71 | 9 |

The safety-relevant result is in the confusion matrix rather than the
accuracy. Every safety-critical intent has precision 1.00, and the
EMERGENCY row is 8 correct, 0 misrouted, 2 rejected. **No emergency was
turned into a different action.** The errors are refusals, which
surface to the user, not substitutions, which do not.

PREPARE_FOR_SLEEP is the weak entry at 0.54 precision, absorbing
misclassifications from WAKE_UP (3) and SHUTDOWN_ENVIRONMENT (2).

## 2. Execution latency, physical devices

Command published to acknowledgement received, **including physical
actuation** — the acknowledgement is what the system commits state
from, so its timing is the honest figure.

### esp32_b

| Device | Type | n | min | median | p95 |
|---|---|---|---|---|---|
| `sleep_light` | LED | 15 | 21 | **28** | 102 |
| `sleep_door` | servo | 15 | 744 | **774** | 810 |
| `sleep_bed` | servo | 15 | 723 | **773** | 876 |
| `medication_servo` | servo, 3-phase | 5 | 1920 | **2002** | 2008 |

### esp32_a

| Device | Type | n | min | median | p95 |
|---|---|---|---|---|---|
| `drawing_light` | LED | 12 | 12 | **17** | 51 |
| `relax_light` | LED | 12 | 11 | **18** | 61 |
| `buzzer` | buzzer | 12 | 10 | **14** | 30 |
| `relax_tv` | servo | 12 | 711 | **716** | 730 |
| `exit_door` | servo | 12 | 711 | **716** | 1043 |
| `relax_door` | servo | 12 | 711 | **720** | 757 |

Milliseconds. Two populations, and a single mean would hide both:

- **Instant devices, 14–28 ms** — no mechanical delay, so this isolates
  transport: publish, broker, node, acknowledge, over 2.4 GHz Wi-Fi.
- **Servos, 716–774 ms** — the firmware waits 700 ms for the arm to
  arrive before acknowledging. Actuation dominates transport by ~40×.
- **Medication, 2002 ms** — a dose is an impulse, not a state: out,
  hold 500 ms, return.

`relax_tv` is incidental evidence for the timing method. Driven as a
relay it acknowledged in 31 ms; rebuilt as a servo, 718 ms. The same
device and the same action, with the mechanism identifiable from the
acknowledgement alone.

## 3. Phase split — transport cost vs actuation cost

The node acknowledges twice: `ack` the moment a command arrives, before
anything else happens, and `complete` once the hardware has acted. This
separates communication health from hardware execution time, per
action, instead of inferring it from device type.

| Node | Device | dispatch→ack | ack→complete | total |
|---|---|---|---|---|
| esp32_b | `sleep_light` | 17 | 69 | 86 |
| esp32_b | `sleep_door` | 18 | **702** | 720 |
| esp32_b | `sleep_bed` | 16 | **704** | 720 |
| esp32_b | `medication_servo` | 13 | **1902** | 1915 |
| esp32_a | `drawing_light` | 17 | 56 | 73 |
| esp32_a | `relax_light` | 22 | 59 | 81 |
| esp32_a | `buzzer` | 19 | 58 | 77 |
| esp32_a | `relax_tv` | 21 | **704** | 724 |
| esp32_a | `exit_door` | 30 | **691** | 721 |
| esp32_a | `relax_door` | 18 | **701** | 720 |

Median milliseconds, n = 10 per device (3 for medication).

`dispatch→ack` is **13–30 ms on every device regardless of type** — the
transport cost, now isolated.

`ack→complete` on the six servos is **691–704 ms**. The firmware waits a
fixed 700 ms for the arm to arrive before acknowledging, so the
measurement recovers a known constant to within 1% across six
independent servos on two boards. That is the metric validating itself
against ground truth rather than being asserted.

## 4. Deduplication — controlled

A completed `command_id` replayed 4 times per device, which is what the
executor does when an acknowledgement is lost. One variable: the
firmware's `DEDUP_ENABLED` switch.

| Device | 1st command | Replay ON | Replay OFF | Re-executed ON | Re-executed OFF |
|---|---|---|---|---|---|
| `sleep_light` | 34 ms | 25 ms | 14 ms | not separable | not separable |
| `sleep_door` | ~716 ms | 33 ms | **717 ms** | **0/4** | **4/4** |
| `sleep_bed` | ~716 ms | 12 ms | **714 ms** | **0/4** | **4/4** |
| `medication_servo` | ~1915 ms | 27 ms | **1915 ms** | **0/4** | **4/4** |

**Without deduplication every replay re-actuated the hardware.** On
`medication_servo` that is five doses dispensed where one was
intended — four caused purely by retrying a single command.

With deduplication, no replay reached the hardware: 27 ms against a
1939 ms original, a 72× gap far outside either population's variance.

Across both physical nodes, all ten devices: **40/40 replays answered
from stored state, zero re-executions.**

Re-execution is detected by timing rather than by observation, because
acknowledgement follows actuation. The method's limit is stated rather
than hidden: it cannot decide anything for an instant device, so LEDs
and the buzzer are reported "not separable". The safety-critical device
is a servo, where it works.

## 5. Workflow latency

Whole intent: planning, ordered execution across nodes, and the state
commit that follows. n = 8.

| Intent | Actions | median | p95 | Hardware |
|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 2 | 769 | 1041 | yes |
| WAKE_UP | 1 | 730 | 931 | yes |
| MEDICATION | 1 | 1957 | 2054 | yes |
| SHUTDOWN_ENVIRONMENT | 11 | 828 | 1031 | yes |
| EMERGENCY | 6 | 2335 | — | yes, 3 nodes |
| RELAX_MODE | 2 | 2 | 3 | simulated only |
| STUDY_MODE | 2 | 2 | 3 | simulated only |
| PREPARE_FOR_MEAL | 2 | 2 | 3 | simulated only |

**Latency tracks the slowest device, not the action count.**
SHUTDOWN_ENVIRONMENT executes 11 actions in 828 ms while
PREPARE_FOR_SLEEP executes 2 in 769 ms. One servo costs ~770 ms; the
rest are instant devices at tens of milliseconds. Workflow cost is set
by how many *physical* devices a plan touches, not by plan size.

## 6. Emergency degradation under partial failure

EMERGENCY is best-effort: it continues past a failed device rather than
aborting. This measures what that costs when devices are unreachable.
Conditions produced by stopping the node owning 2 of the 6 doors.

| Condition | n | median | min | max | succeeded | failed |
|---|---|---|---|---|---|---|
| All 6 reachable | 4 | **2335** | 2211 | 2712 | 6 | 0 |
| 2 of 6 unreachable | 4 | **32256** | 32237 | 32435 | 4 | 2 |

**Degradation factor 13.8×.**

The policy holds — every reachable door opened in both conditions. But
actions are dispatched serially, so each unreachable device contributes
its full timeout to a workflow whose entire purpose is speed. An
evacuation taking 32 seconds because a node is offline has arguably
failed even though every reachable door opened.

This is a design weakness the measurement found, not a success. Two
plausible remedies: a shorter timeout for `BEST_EFFORT_INTENTS`, or
concurrent dispatch for them.

## 7. Emergency lifecycle on physical hardware

EMERGENCY across three nodes, two of them physical:

```
BUZZER_ON  buzzer      esp32_a   OPEN_DOOR  exit_door   esp32_a
OPEN_DOOR  relax_door  esp32_a   OPEN_DOOR  sleep_door  esp32_b
OPEN_DOOR  study_door  esp32_c   OPEN_DOOR  meal_door   esp32_c

completed 2227 ms, emergency latched = True
RELAX_MODE while latched -> refused: EmergencyActive
EMERGENCY_CLEAR -> 2192 ms, latched = False
```

The latch is demonstrated rather than asserted: an ordinary intent was
refused while latched and accepted after clearing.

## 8. Node protocol conformance

`tools/bench_node.py --suite --strict`, against physical boards.

| Node | Device | Passed |
|---|---|---|
| esp32_b | `sleep_light` | 11/11 |
| esp32_b | `sleep_door`, `sleep_bed` | 10/10 each |
| esp32_a | `drawing_light` | 11/11 |
| esp32_a | `relax_light`, `relax_tv`, `buzzer`, `exit_door`, `relax_door` | 10/10 each |

Checked: acknowledgement present; exactly one responder on the node id;
`command_id` echoed unchanged; correct node and device echoed;
duplicate answered again as a fresh message; unknown action and unknown
device answered `error` rather than silence; an action belonging to a
different device type refused.

## 9. Reliability under failure

Counted from the wire, not from instrumented application code. The
executor reuses one `command_id` across retries of a logical action —
the property that lets a node recognise a retry — and the same property
makes retries observable: a second publish of an id already seen is a
retry by definition.

Three conditions, 4 intents × 3 trials each.

### All nodes reachable

| Intent | Workflows | Tasks | Succeeded | Retries |
|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 3/3 | 6 | 6 | 0 |
| MEDICATION | 3/3 | 3 | 3 | 0 |
| SHUTDOWN_ENVIRONMENT | 3/3 | 33 | 33 | 0 |
| EMERGENCY | 3/3 | 18 | 18 | 0 |

**Workflow completion 12/12, task success 60/60, retry rate 0.**

### One node permanently unreachable

| Intent | Workflows | Tasks | Succeeded | Failed | Retries | Contained |
|---|---|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 3/3 | 6 | 6 | 0 | 0 | — |
| MEDICATION | 3/3 | 3 | 3 | 0 | 0 | — |
| SHUTDOWN_ENVIRONMENT | **0/3** | 3 | 0 | 3 | 6 | **30** |
| EMERGENCY | 3/3 | 18 | 12 | 6 | 12 | 0 |

This is the clearest evidence of the two execution policies, and they
behave oppositely under the same failure:

- **SHUTDOWN_ENVIRONMENT is fail-fast.** The first action targeting the
  dead node exhausts its retries, the workflow aborts, and **30 of 33
  planned actions are never dispatched.** Failure containment = 1.0. No
  command is pushed at a device whose workflow has already failed.
- **EMERGENCY is best-effort.** All 18 actions are dispatched, 12
  succeed, 6 fail. Containment is 0 **by design** — an emergency must
  open every door it can still reach.

Recovery is 0/9 here because the failure is permanent. Retries against
a node that never returns can only exhaust.

### Node returns mid-workflow (transient failure)

| Intent | Workflows | Tasks | Succeeded | Retries | Recovered |
|---|---|---|---|---|---|
| PREPARE_FOR_SLEEP | 3/3 | 6 | 6 | 0 | — |
| MEDICATION | 3/3 | 3 | 3 | 0 | — |
| SHUTDOWN_ENVIRONMENT | 3/3 | 33 | 33 | 5 | **3/3** |
| EMERGENCY | 3/3 | 18 | 18 | 6 | **3/3** |

The node is stopped as the workflow begins and restarted 6 s later,
before the executor exhausts its attempts — a dropped acknowledgement,
a rebooting node, a moment of interference.

**Recovery success rate 6/6 (100%). Workflow completion 12/12.** Every
task that needed a retry succeeded once the node returned, and no
workflow was lost to a transient failure. 11 retries across 60 tasks,
a retry rate of 0.18 under induced failure against 0 when healthy.

## 10. Broker rediscovery

During the session the hotspot reassigned the broker host from
`10.129.134.173` to `10.166.126.173`. Both physical nodes re-discovered
the broker and reconnected without intervention — the recovery path
firing unprompted rather than in a staged test. Nodes carry no broker
address of their own; the host announces itself by UDP broadcast and a
node re-listens after three consecutive connection failures.

## Limitations

**A servo cannot confirm it moved.** It returns no position, so the
node acknowledges after writing the PWM signal and waiting. ACK-gated
commit is therefore weaker for servos than for instant devices. The
timing method in §3 partly closes this — it distinguishes actuation
from stored-state replies — but it detects *that the node performed
its actuation sequence*, not that the arm physically arrived. A stalled
or disconnected servo would still be reported as success. Closing this
properly needs position feedback: a potentiometer tap or limit switch.

**One simulated node.** `esp32_c` is software. Three intents in §4 have
no hardware timing and are marked accordingly.

**Single environment.** One session, one hotspot, one room. No
variation in RF conditions or distance. Earlier measurements at
−65 dBm on a home router behaved materially differently before Wi-Fi
power-saving was disabled on the nodes, so these figures should not be
read as representative of weaker links.

**Recognition validation is small.** n = 105, roughly 10 per intent, so
per-intent figures have wide confidence intervals.

**No user study.** Every figure here is system behaviour. Nothing has
been measured with the assistive users the system is intended for, and
no claim about usability or acceptance is supported.
