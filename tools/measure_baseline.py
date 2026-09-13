"""Open-loop vs acknowledgement-gated actuation.

One variable: whether an action's completion is confirmed or assumed.
Same orchestrator, same planner, same nodes, same network, same
command envelope - a node cannot tell which executor sent a command.

Two failures are counted, both from the wire rather than from
instrumented application code:

  ordering violation
      an action was dispatched before the previous action in the plan
      had physically completed. Plan order is the dependency order -
      the planner emits actions in the sequence they must happen - so
      the test is whether action i+1's command timestamp precedes
      action i's completion. Acknowledgement-gating makes this
      impossible by construction; open loop permits it whenever delta
      is shorter than the device takes.

  silent success
      the workflow reported completion while a device did not act. A
      node is made unreachable, so its commands cannot have taken
      effect; any workflow still reporting success is counting actions
      that never happened.

Delta is the baseline's whole problem and both ends are bad. Two
values are run:

  delta_tight  near the mean cost of the instant devices. Fast, and
               wrong whenever a servo is involved.
  delta_safe   above the slowest action measured (medication, ~2 s).
               Correct ordering, at the cost of making every device
               wait for the worst one.

    python -m tools.measure_baseline --host 10.166.126.173
"""

import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
import uuid

import paho.mqtt.client as mqtt

# Each is (intent, room, starting mode). Chosen for multi-action plans
# touching physical devices, so ordering has something to violate.
INTENTS = [
    ("PREPARE_FOR_SLEEP", "SLEEP_ROOM", "NONE"),
    ("SHUTDOWN_ENVIRONMENT", "DRAWING_ROOM", "NONE"),
    ("EMERGENCY", "SLEEP_ROOM", "NONE"),
]


class Wire:
    """Timestamps every command and completion on the bus."""

    def __init__(self, host, port):
        self.events = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"base_{uuid.uuid4().hex[:8]}")
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.subscribe("assistive/command/#", qos=1)
        self.client.subscribe("assistive/status/#", qos=1)
        self.client.loop_start()
        time.sleep(0.5)

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode())
        except ValueError:
            return
        at = time.perf_counter()
        if "/command/" in message.topic:
            kind = "command"
        elif payload.get("phase", "complete") == "complete":
            kind = "complete"
        else:
            return
        self.events.append((at, kind, payload))

    def mark(self):
        return len(self.events)

    def since(self, mark):
        return self.events[mark:]

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def analyse(events):
    """Count ordering violations and completions for one workflow."""

    commands = []
    completed = {}
    seen = set()

    for at, kind, payload in events:
        key = payload.get("command_id")
        if key is None:
            continue
        if kind == "command":
            if key not in seen:
                seen.add(key)
                commands.append((at, key, payload.get("device")))
        elif key not in completed:
            completed[key] = (at, payload.get("status"))

    violations = []
    for index in range(1, len(commands)):
        dispatched_at, key, device = commands[index]
        previous_at, previous_key, previous_device = commands[index - 1]
        finished = completed.get(previous_key)
        # Dispatched before the previous action was confirmed done -
        # or with the previous action never confirmed at all.
        if finished is None or dispatched_at < finished[0]:
            violations.append((previous_device, device))

    acted = sum(1 for at, status in completed.values() if status == "success")

    return {
        "dispatched": len(commands),
        "acted": acted,
        "violations": len(violations),
        "violation_pairs": violations,
    }


def stop_node():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'simulated_node esp32_c' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True)
    time.sleep(1.5)


def start_node(host):
    subprocess.Popen(
        [r"e:\Assistive-orchestration\.venv\Scripts\python.exe", "-u", "-m",
         "app.devices.simulated_node", "esp32_c", host, "1883"],
        cwd="e:/Assistive-orchestration",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4.0)


def run(host, port, trials, deltas):
    from app.devices.mqtt_client import MQTTClient
    from app.devices.mqtt_device import MQTTDeviceExecutor
    from app.devices.open_loop_device import OpenLoopExecutor
    from app.orchestration.state import Mode, Room
    from app.runtime import ApplicationRuntime

    def quiet(call, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return call(*args)

    wire = Wire(host, port)
    rows = []

    def one_condition(label, make_executor, degraded):
        client = MQTTClient(broker_host=host, broker_port=port,
                            client_id=f"cmp_{uuid.uuid4().hex[:6]}")
        quiet(client.connect)
        runtime = ApplicationRuntime(broker_host=host, broker_port=port,
                                     device_executor=make_executor(client),
                                     persist=False)
        quiet(runtime.connect)

        totals = {"workflows": 0, "reported": 0, "dispatched": 0,
                  "acted": 0, "violations": 0, "silent": 0, "latency": []}
        try:
            for intent, room, mode in INTENTS:
                for _ in range(trials):
                    if runtime.context.emergency_latched():
                        quiet(runtime.execute_intent, "EMERGENCY_CLEAR")
                    runtime.context.confirm_location(getattr(Room, room))
                    runtime.context.set_mode(getattr(Mode, mode))

                    mark = wire.mark()
                    started = time.perf_counter()
                    reported = True
                    try:
                        quiet(runtime.execute_intent, intent)
                    except Exception:
                        reported = False
                    elapsed = (time.perf_counter() - started) * 1000.0
                    time.sleep(1.0)

                    counts = analyse(wire.since(mark))
                    totals["workflows"] += 1
                    totals["reported"] += int(reported)
                    totals["dispatched"] += counts["dispatched"]
                    totals["acted"] += counts["acted"]
                    totals["violations"] += counts["violations"]
                    totals["latency"].append(elapsed)

                    # Silent success, counted per workflow: this run
                    # reported completion while at least one of its own
                    # actions was never confirmed. Aggregating across
                    # the condition would credit every workflow with
                    # one failure anywhere.
                    if reported and counts["acted"] < counts["dispatched"]:
                        totals["silent"] += 1

                    if intent == "EMERGENCY":
                        with contextlib.suppress(Exception):
                            quiet(runtime.execute_intent, "EMERGENCY_CLEAR")
                        time.sleep(0.5)
        finally:
            quiet(runtime.shutdown)
            with contextlib.suppress(Exception):
                quiet(client.disconnect)

        latency = sorted(totals["latency"])
        median = latency[len(latency) // 2] if latency else 0
        rows.append({
            "condition": label,
            "degraded": degraded,
            "workflows": totals["workflows"],
            "reported": totals["reported"],
            "dispatched": totals["dispatched"],
            "acted": totals["acted"],
            "violations": totals["violations"],
            "silent": totals["silent"],
            "median_ms": median,
        })
        return rows[-1]

    try:
        for degraded in (False, True):
            if degraded:
                stop_node()
            else:
                start_node(host)

            header = "TWO OF SIX DEVICES UNREACHABLE" if degraded \
                else "ALL DEVICES REACHABLE"
            print()
            print(f"  {header}")
            print("  " + "-" * 76)
            print(f"  {'executor':<26}{'wf ok':>7}{'sent':>7}{'acted':>7}"
                  f"{'ordering viol.':>16}{'silent':>8}{'median ms':>11}")
            print("  " + "-" * 76)

            one_condition("closed loop (proposed)",
                          lambda c: MQTTDeviceExecutor(c), degraded)
            for delta in deltas:
                one_condition(f"open loop, d={delta:g}s",
                              lambda c, d=delta: OpenLoopExecutor(c, delay=d),
                              degraded)

            for row in rows[-(1 + len(deltas)):]:
                print(f"  {row['condition']:<26}"
                      f"{row['reported']}/{row['workflows']:<5}"
                      f"{row['dispatched']:>7}{row['acted']:>7}"
                      f"{row['violations']:>16}{row['silent']:>8}"
                      f"{row['median_ms']:>11.0f}")
            print("  " + "-" * 76)
    finally:
        wire.close()
        start_node(host)

    print()
    print("  ordering viol.  an action dispatched before the previous one")
    print("                  in the plan was confirmed complete")
    print("  silent          workflows reported complete while a device")
    print("                  could not have acted")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--delta-tight", type=float, default=0.1,
                        help="near the instant-device mean; fast and wrong")
    parser.add_argument("--delta-safe", type=float, default=2.1,
                        help="above the slowest measured action")
    args = parser.parse_args()

    print()
    print("=" * 82)
    print("  OPEN-LOOP vs ACKNOWLEDGEMENT-GATED ACTUATION")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}   broker {args.host}")
    print("=" * 82)
    run(args.host, args.port, args.trials, [args.delta_tight, args.delta_safe])
    return 0


if __name__ == "__main__":
    sys.exit(main())
