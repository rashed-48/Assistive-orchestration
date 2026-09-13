# Deduplication: control experiment

Same board, same commands, same network. One variable: the firmware's
`DEDUP_ENABLED` switch. A completed `command_id` is replayed 4 times
per device, which is what the executor does when an acknowledgement is
lost.

Re-execution is detected by timing. The node acknowledges only after
actuation completes, so a replay answered from stored state costs
transport alone while a re-executed one carries the full actuation
time. On a servo the two differ by more than an order of magnitude.

## Results

| Device | 1st command | Replay, dedup ON | Replay, dedup OFF | Re-executed ON | Re-executed OFF |
|---|---|---|---|---|---|
| `sleep_light` | 34 ms | 25 ms | 14 ms | not separable | not separable |
| `sleep_door` | 755 / 716 ms | 33 ms | 717 ms | **0/4** | **4/4** |
| `sleep_bed` | 733 / 716 ms | 12 ms | 714 ms | **0/4** | **4/4** |
| `medication_servo` | 1939 / 1915 ms | 27 ms | 1915 ms | **0/4** | **4/4** |

With deduplication disabled, every replay re-actuated the hardware. On
`medication_servo` that is **five doses dispensed where one was
intended** - four of them caused purely by retries of a single command.

With deduplication enabled, no replay reached the hardware. A replay
costs 27 ms against a 1939 ms original: a 72x gap, far outside the
variance of either population.

## Why timing is admissible evidence here

A servo returns no position, so nothing in a reply states whether the
arm moved. That gap was previously closed only by watching the device.
Because acknowledgement follows actuation, latency separates the two
populations cleanly, and the property becomes machine-checkable rather
than observational.

The method has a stated limit: it cannot decide anything for a relay.
`sleep_light` switches in ~14 ms whether or not it re-executes, so the
two conditions are indistinguishable by timing and are reported as
"not separable" rather than guessed. The safety-critical device is a
servo, where the method does work.

## Reproducing

```
# control condition
#   firmware/assistive_node/assistive_node.ino
#   #define DEDUP_ENABLED 0        -- flash, measure, then restore to 1
python -m tools.measure_execution --host <broker> --node esp32_b \
    --trials 6 --skip-idempotency --dedup-control --replays 4
```

`DEDUP_ENABLED 0` is an experiment build only. A node left running
with it re-dispenses medication on every retry, and the retry path is
automatic.
