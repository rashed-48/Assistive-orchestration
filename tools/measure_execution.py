"""Measure execution on real hardware, for reporting.

The recognition layer already has an evaluation harness. This is its
counterpart for the layer below it: what the system actually costs and
how reliably it behaves once an intent has been recognised and has to
reach a physical device.

Three experiments, each repeatable and each emitting a CSV:

  latency      round trip from publishing a command to the
               acknowledgement that permits a state commit. Reported
               per device, since a relay and a servo differ by an
               order of magnitude and averaging them hides that.

  idempotency  a completed command_id replayed N times. Counts how
               many were answered, and how many were answered from
               stored state rather than re-executed. Re-execution is
               the failure this measures; on a dosing mechanism it is
               a second dose.

  workflow     end to end, an intent through planning, execution and
               state commit.

Latency here includes physical actuation - a servo is given time to
arrive before the node acknowledges - so these are not network
numbers. That is deliberate: the acknowledgement is what the system
commits state from, so its timing is the honest figure.

    python -m tools.measure_execution --host 10.129.134.173
    python -m tools.measure_execution --host ... --trials 30 --csv out/
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
import uuid

import paho.mqtt.client as mqtt

# device, action, restoring action, trials - medication is deliberately
# sampled less: every trial is a physical dose cycle.
# Below this, a device's acknowledgement is transport alone: there is
# no actuation delay for a replay to reveal, so timing cannot detect
# re-execution. Well above the observed relay median (~28 ms) and well
# below the servo median (~774 ms).
SEPARABLE_MS = 200.0

PLANS = {
    "esp32_b": [
        ("sleep_light", "LIGHT_ON", "LIGHT_OFF", 1.0),
        ("sleep_door", "OPEN_DOOR", "CLOSE_DOOR", 1.0),
        ("sleep_bed", "PREPARE_BED", "RESET_BED", 1.0),
        ("medication_servo", "ACTIVATE_MEDICATION", None, 0.34),
    ],
    "esp32_a": [
        ("drawing_light", "LIGHT_ON", "LIGHT_OFF", 1.0),
        ("relax_light", "LIGHT_ON", "LIGHT_OFF", 1.0),
        ("buzzer", "BUZZER_ON", "BUZZER_OFF", 1.0),
        ("relax_tv", "TV_ON", "TV_OFF", 1.0),
        ("exit_door", "OPEN_DOOR", "CLOSE_DOOR", 1.0),
        ("relax_door", "OPEN_DOOR", "CLOSE_DOOR", 1.0),
    ],
    "esp32_c": [
        ("study_light", "LIGHT_ON", "LIGHT_OFF", 1.0),
        ("meal_light", "LIGHT_ON", "LIGHT_OFF", 1.0),
        ("study_door", "OPEN_DOOR", "CLOSE_DOOR", 1.0),
        ("study_table", "PREPARE_TABLE", "RESET_TABLE", 1.0),
    ],
}

PLAN = PLANS["esp32_b"]


class Probe:
    """One MQTT client, timing each command to its acknowledgement."""

    def __init__(self, host, port, node):
        self.node = node
        self.replies = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"measure_{uuid.uuid4().hex[:8]}",
        )
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.subscribe(f"assistive/status/{node}", qos=1)
        self.client.loop_start()
        time.sleep(0.4)

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
        except ValueError:
            return
        key = payload.get("command_id")
        if key:
            self.replies.setdefault(key, []).append((time.perf_counter(), payload))

    def timed(self, device, action, command_id=None, wait=12.0):
        """Publish and wait. Returns (milliseconds, reply) or (None, None)."""

        command_id = command_id or str(uuid.uuid4())
        already = len([r for r in self.replies.get(command_id, [])
                       if r[1].get("phase", "complete") == "complete"])

        started = time.perf_counter()
        self.client.publish(
            f"assistive/command/{self.node}",
            json.dumps({"device": device, "action": action,
                        "parameters": {}, "command_id": command_id}),
            qos=1,
        )

        deadline = started + wait
        while time.perf_counter() < deadline:
            arrived = [r for r in self.replies.get(command_id, [])
                       if r[1].get("phase", "complete") == "complete"]
            if len(arrived) > already:
                at, payload = arrived[already]
                return (at - started) * 1000.0, payload
            time.sleep(0.002)

        return None, None

    def phases(self, device, action, command_id=None, wait=12.0):
        """Publish once and time both replies.

        Returns (dispatch_to_ack_ms, ack_to_complete_ms, reply). The
        first is how long the command took to reach the node; the
        second is how long the hardware took. Older firmware sends only
        one message, so the ack leg comes back None.
        """

        command_id = command_id or str(uuid.uuid4())
        self.replies.pop(command_id, None)

        started = time.perf_counter()
        self.client.publish(
            f"assistive/command/{self.node}",
            json.dumps({"device": device, "action": action,
                        "parameters": {}, "command_id": command_id}),
            qos=1,
        )

        ack_at = None
        deadline = started + wait
        while time.perf_counter() < deadline:
            for at, payload in self.replies.get(command_id, []):
                phase = payload.get("phase", "complete")
                if phase == "ack" and ack_at is None:
                    ack_at = at
                elif phase == "complete":
                    dispatch = (ack_at - started) * 1000.0 if ack_at else None
                    actuate = ((at - ack_at) * 1000.0 if ack_at
                               else (at - started) * 1000.0)
                    return dispatch, actuate, payload
            time.sleep(0.002)

        return None, None, None

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def summarise(samples):
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
        "stdev": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
    }


def experiment_latency(probe, trials, rows, baseline=None):
    print()
    print("  LATENCY - command published to acknowledgement received")
    print("  " + "-" * 62)
    print(f"  {'device':<19}{'n':>4}{'min':>9}{'median':>9}{'p95':>9}{'max':>9}")
    print("  " + "-" * 62)

    for device, action, restore, share in PLAN:
        count = max(3, int(round(trials * share)))
        samples = []
        lost = 0

        for _ in range(count):
            elapsed, reply = probe.timed(device, action)
            if elapsed is None or (reply or {}).get("status") != "success":
                lost += 1
            else:
                samples.append(elapsed)
                rows.append({"experiment": "latency", "device": device,
                             "action": action, "ms": round(elapsed, 2)})
            time.sleep(0.35)
            if restore:
                probe.timed(device, restore)
                time.sleep(0.35)

        if not samples:
            print(f"  {device:<19}{'--':>4}   no successful trials")
            continue

        s = summarise(samples)
        if baseline is not None:
            baseline[device] = s["median"]
        print(f"  {device:<19}{s['n']:>4}{s['min']:>9.0f}{s['median']:>9.0f}"
              f"{s['p95']:>9.0f}{s['max']:>9.0f}")
        if lost:
            print(f"  {'':19}     {lost} unacknowledged")

    print("  " + "-" * 62)
    print("  milliseconds. Includes physical actuation, not network only.")


def experiment_idempotency(probe, replays, rows):
    """Replay one completed command and count how it is handled."""

    print()
    print("  IDEMPOTENCY - a completed command_id replayed")
    print("  " + "-" * 62)

    for device, action, restore, _ in PLAN:
        command_id = str(uuid.uuid4())
        elapsed, first = probe.timed(device, action, command_id=command_id)
        if elapsed is None:
            print(f"  {device:<19} original command unacknowledged - skipped")
            continue
        time.sleep(0.5)
        if restore:
            probe.timed(device, restore)
            time.sleep(0.5)

        answered = 0
        from_store = 0
        for _ in range(replays):
            _, reply = probe.timed(device, action, command_id=command_id)
            if reply is not None:
                answered += 1
                from_store += bool(reply.get("duplicate"))
            time.sleep(0.3)

        rows.append({"experiment": "idempotency", "device": device,
                     "action": action, "replays": replays,
                     "answered": answered, "from_store": from_store})

        verdict = "ok" if answered == replays == from_store else "CHECK"
        print(f"  {device:<19} {replays} replays -> {answered} answered, "
              f"{from_store} from stored state   [{verdict}]")

    print("  " + "-" * 62)
    print("  Every replay must be answered (a silent one reads as a")
    print("  timeout and the action is lost) and answered from stored")
    print("  state (re-execution on a dosing device is a second dose).")


def experiment_phases(probe, trials, rows):
    """Separate getting the command there from the hardware acting.

    A node acknowledges on arrival and again on completion, so the two
    costs no longer have to be inferred from device type. Communication
    health and true hardware execution time are measured directly, per
    action, on every device.
    """

    print()
    print("  PHASE SPLIT - transport cost vs actuation cost")
    print("  " + "-" * 66)
    print(f"  {'device':<19}{'n':>4}{'dispatch->ack':>15}{'ack->complete':>15}"
          f"{'sd':>7}{'total':>8}")
    print("  " + "-" * 66)

    for device, action, restore, share in PLAN:
        count = max(3, int(round(trials * share)))
        dispatch_samples = []
        actuate_samples = []
        unsplit = 0

        for _ in range(count):
            dispatch, actuate, reply = probe.phases(device, action)
            if reply is None:
                continue
            if dispatch is None:
                unsplit += 1
            else:
                dispatch_samples.append(dispatch)
            actuate_samples.append(actuate)
            rows.append({"experiment": "phases", "device": device,
                         "action": action,
                         "dispatch_ms": round(dispatch, 2) if dispatch else "",
                         "actuate_ms": round(actuate, 2)})
            time.sleep(0.35)
            if restore:
                probe.phases(device, restore)
                time.sleep(0.35)

        if not actuate_samples:
            print(f"  {device:<19}{'--':>4}   no successful trials")
            continue

        if unsplit:
            print(f"  {device:<19}{len(actuate_samples):>4}"
                  f"{'no ack - firmware predates the split':>40}")
            continue

        d = summarise(dispatch_samples)
        a = summarise(actuate_samples)

        print(f"  {device:<19}{a['n']:>4}{d['median']:>15.0f}"
              f"{a['median']:>15.0f}{a['stdev']:>7.1f}"
              f"{d['median'] + a['median']:>8.0f}")

    print("  " + "-" * 66)
    print("  median milliseconds. dispatch->ack is communication health.")
    print("  ack->complete is the node's actuation SEQUENCE, not proof of")
    print("  movement: the firmware writes the signal, waits a fixed")
    print("  delay, then acknowledges. An unpowered servo yields the same")
    print("  number, and sd is network jitter, not mechanical load. Only")
    print("  a person or a position sensor can confirm the arm moved.")


def experiment_dedup_control(probe, replays, rows, baseline):
    """Quantify what deduplication prevents.

    Run once against a normal build and once against one compiled with
    DEDUP_ENABLED 0. The node acknowledges only after actuation
    finishes, so a replay answered from stored state returns in
    transport time while a re-executed one carries the full actuation
    cost. `baseline` is the measured single-command latency per device,
    and a replay landing near it means the hardware moved again.
    """

    print()
    print("  DEDUP CONTROL - what a replayed command actually costs")
    print("  " + "-" * 62)
    print(f"  {'device':<19}{'n':>4}{'replay ms':>12}{'1st cmd ms':>12}"
          f"{'re-executed':>13}")
    print("  " + "-" * 62)

    for device, action, restore, _ in PLAN:
        first_cost = baseline.get(device)
        if first_cost is None:
            continue

        command_id = str(uuid.uuid4())
        elapsed, reply = probe.timed(device, action, command_id=command_id)
        if elapsed is None:
            print(f"  {device:<19} original unacknowledged - skipped")
            continue
        time.sleep(0.5)
        if restore:
            probe.timed(device, restore)
            time.sleep(0.5)

        # The proxy only works where actuation dominates transport.
        # A relay switches instantly, so a replay costs exactly what
        # the original did and the two are indistinguishable by timing
        # - dividing that baseline would flag every replay as a
        # re-execution. Say so rather than report a false count.
        separable = first_cost >= SEPARABLE_MS
        threshold = first_cost / 2.0

        samples = []
        reexecuted = 0

        for _ in range(replays):
            took, reply = probe.timed(device, action, command_id=command_id)
            if took is None:
                continue
            samples.append(took)
            if took >= threshold:
                reexecuted += 1
            time.sleep(0.4)

        if not samples:
            print(f"  {device:<19} no replays answered")
            continue

        median = statistics.median(samples)
        verdict = (f"{reexecuted}/{len(samples)}" if separable
                   else "not separable")
        rows.append({"experiment": "dedup_control", "device": device,
                     "action": action, "replays": len(samples),
                     "ms": round(median, 2),
                     "first_command_ms": round(first_cost, 2),
                     "reexecuted": reexecuted if separable else "",
                     "separable": separable})

        print(f"  {device:<19}{len(samples):>4}{median:>12.0f}"
              f"{first_cost:>12.0f}{verdict:>14}")

    print("  " + "-" * 62)
    print("  A node acknowledges only after actuation completes, so a")
    print("  replay answered from stored state costs transport alone")
    print("  while a re-executed one carries the full actuation time.")
    print("  Counted as re-executed when a replay takes at least half")
    print(f"  the first command's latency. Devices whose first command")
    print(f"  costs under {SEPARABLE_MS:.0f} ms have no actuation delay to")
    print("  separate, so timing cannot decide it either way.")


def experiment_workflows(host, port, trials, rows, real_nodes=()):
    """Time whole intents, not single actions.

    This runs the real orchestrator, so it measures planning, ordered
    execution across nodes, and the state commit that follows - the
    figure a user actually waits through. Each trial resets the logical
    state first, otherwise a workflow already satisfied would return
    immediately and flatter the result.
    """

    from app.orchestration.state import Mode, Room
    from app.runtime import ApplicationRuntime

    print()
    print("  WORKFLOW - intent to committed state")
    print("  " + "-" * 62)
    print(f"  {'intent':<24}{'n':>4}{'actions':>9}{'median':>9}{'p95':>9}")
    print("  " + "-" * 62)

    # intent, room to be in, mode to start from, intent that undoes it
    plans = [
        ("PREPARE_FOR_SLEEP", Room.SLEEP_ROOM, Mode.NONE, None),
        ("WAKE_UP", Room.SLEEP_ROOM, Mode.SLEEP, None),
        ("MEDICATION", Room.SLEEP_ROOM, Mode.NONE, None),
        ("RELAX_MODE", Room.RELAX_ROOM, Mode.NONE, None),
        ("STUDY_MODE", Room.STUDY_ROOM, Mode.NONE, None),
        ("PREPARE_FOR_MEAL", Room.MEAL_ROOM, Mode.NONE, None),
        ("SHUTDOWN_ENVIRONMENT", Room.DRAWING_ROOM, Mode.NONE, None),
        # EMERGENCY latches the environment; the latch has to be
        # released or every later trial is refused.
        ("EMERGENCY", Room.SLEEP_ROOM, Mode.NONE, "EMERGENCY_CLEAR"),
    ]

    runtime = ApplicationRuntime(broker_host=host, broker_port=port,
                                 client_id="measure_workflow", persist=False)
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        runtime.connect()

    try:
        for intent, room, start_mode, undo in plans:
            samples = []
            action_count = 0
            failures = 0
            reason = ""

            for _ in range(trials):
                runtime.context.confirm_location(room)
                runtime.context.set_mode(start_mode)

                started = time.perf_counter()
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        results = runtime.execute_intent(intent)
                except Exception as error:
                    failures += 1
                    reason = f"{type(error).__name__}: {error}"
                    continue
                elapsed = (time.perf_counter() - started) * 1000.0

                samples.append(elapsed)
                action_count = len(results)
                touched = sorted({r.get("node") for r in results if r.get("node")})
                rows.append({"experiment": "workflow", "intent": intent,
                             "actions": action_count, "ms": round(elapsed, 2),
                             "nodes": "|".join(touched),
                             "hardware": "|".join(
                                 n for n in touched if n in real_nodes) or "none"})

                if undo:
                    with contextlib.redirect_stdout(io.StringIO()):
                        runtime.execute_intent(undo)
                time.sleep(0.4)

            if not samples:
                print(f"  {intent:<24}{'--':>4}   none succeeded"
                      + (f" - {reason}" if reason else ""))
                continue

            s = summarise(samples)
            on_hardware = any(
                row.get("experiment") == "workflow"
                and row.get("intent") == intent
                and row.get("hardware", "none") != "none"
                for row in rows)
            print(f"  {intent:<24}{s['n']:>4}{action_count:>9}"
                  f"{s['median']:>9.0f}{s['p95']:>9.0f}"
                  f"{'' if on_hardware else '   simulated only'}")
            if failures:
                print(f"  {'':24}     {failures} failed")
    finally:
        with contextlib.redirect_stdout(io.StringIO()):
            runtime.shutdown()

    print("  " + "-" * 62)
    print("  milliseconds, whole intent: planning, execution across")
    print("  nodes, and the state commit that follows.")


def write_csv(rows, directory):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "execution_measurements.csv")
    fields = sorted({key for row in rows for key in row})
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--node", default="esp32_b")
    parser.add_argument("--trials", type=int, default=15,
                        help="latency trials per device")
    parser.add_argument("--replays", type=int, default=5,
                        help="replays per device for idempotency")
    parser.add_argument("--csv", default=None,
                        help="directory to write the raw samples into")
    parser.add_argument("--skip-idempotency", action="store_true")
    parser.add_argument("--phases", action="store_true",
                        help="split each action into transport and "
                             "actuation using the node's ack/complete "
                             "messages")
    parser.add_argument("--dedup-control", action="store_true",
                        help="measure what a replay costs; run once "
                             "normally and once against a DEDUP_ENABLED 0 "
                             "build to get both conditions")
    parser.add_argument("--workflows", action="store_true",
                        help="also time whole intents through the orchestrator")
    parser.add_argument("--workflow-trials", type=int, default=5)
    parser.add_argument("--real-nodes", default="esp32_b",
                        help="comma separated nodes backed by real hardware; "
                             "recorded so simulated timings are never "
                             "reported as measured hardware")
    args = parser.parse_args()

    global PLAN
    PLAN = PLANS.get(args.node, PLANS["esp32_b"])

    try:
        probe = Probe(args.host, args.port, args.node)
    except OSError as error:
        print(f"Cannot reach the broker at {args.host}:{args.port} - {error}")
        return 2

    print()
    print("=" * 66)
    print(f"  Execution measurements - {args.node} via {args.host}")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    real = [n.strip() for n in args.real_nodes.split(",") if n.strip()]
    simulated = [n for n in ("esp32_a", "esp32_b", "esp32_c") if n not in real]
    print(f"  real hardware: {', '.join(real) or 'none'}")
    print(f"  simulated:     {', '.join(simulated) or 'none'}")
    print("=" * 66)

    rows = []
    baseline = {}
    try:
        experiment_latency(probe, args.trials, rows, baseline=baseline)
        if not args.skip_idempotency:
            experiment_idempotency(probe, args.replays, rows)
        if args.phases:
            experiment_phases(probe, args.trials, rows)
        if args.dedup_control:
            experiment_dedup_control(probe, args.replays, rows, baseline)
    finally:
        probe.close()

    if args.workflows:
        experiment_workflows(args.host, args.port, args.workflow_trials,
                             rows, real_nodes=real)

    if args.csv:
        print()
        print(f"  raw samples -> {write_csv(rows, args.csv)}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
