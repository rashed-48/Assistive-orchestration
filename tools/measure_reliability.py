"""Reliability metrics: retries, recovery, completion, containment.

Everything here is counted from the wire rather than from instrumented
application code. The executor reuses one command_id across retries of
a logical action - that is what lets a node recognise a retry - and the
same property makes retries observable: a second publish carrying an id
already seen is a retry, by definition.

    dispatched     distinct command_ids published
    retries        publishes beyond the first for an id
    succeeded      ids whose completion carried status "success"
    recovered      ids that succeeded only after a retry

Failure containment is measured against a baseline plan. An intent is
first run with every node reachable to learn how many actions it
dispatches; the same intent is then run with a node down. Actions in
the plan that were never dispatched after the abort are contained -
the system did not push commands at devices whose preconditions had
already failed.

    python -m tools.measure_reliability --host 10.166.126.173
"""

import argparse
import contextlib
import io
import json
import subprocess
import sys
import threading
import time
import uuid

import paho.mqtt.client as mqtt

INTENTS = [
    ("PREPARE_FOR_SLEEP", "SLEEP_ROOM", "NONE"),
    ("MEDICATION", "SLEEP_ROOM", "NONE"),
    ("SHUTDOWN_ENVIRONMENT", "DRAWING_ROOM", "NONE"),
    ("EMERGENCY", "SLEEP_ROOM", "NONE"),
]


class Wire:
    """Counts commands and results without touching the application."""

    def __init__(self, host, port):
        self.commands = []
        self.results = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"wire_{uuid.uuid4().hex[:8]}")
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
        if "/command/" in message.topic:
            self.commands.append(payload)
        elif payload.get("phase", "complete") == "complete":
            self.results.append(payload)

    def mark(self):
        return len(self.commands), len(self.results)

    def since(self, mark):
        return self.commands[mark[0]:], self.results[mark[1]:]

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def tally(commands, results):
    """Reduce one workflow's traffic to counts."""

    order = []
    seen = {}
    for command in commands:
        key = command.get("command_id")
        if key is None:
            continue
        if key not in seen:
            seen[key] = 0
            order.append(key)
        seen[key] += 1

    status = {}
    for result in results:
        key = result.get("command_id")
        if key in seen and key not in status:
            status[key] = result.get("status")

    dispatched = len(order)
    retries = sum(count - 1 for count in seen.values())
    succeeded = sum(1 for key in order if status.get(key) == "success")
    needed_retry = [key for key in order if seen[key] > 1]
    recovered = sum(1 for key in needed_retry if status.get(key) == "success")

    return {
        "dispatched": dispatched,
        "retries": retries,
        "succeeded": succeeded,
        "failed": dispatched - succeeded,
        "needed_retry": len(needed_retry),
        "recovered": recovered,
    }


def stop_node():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'simulated_node' } | "
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


def return_node_after(host, seconds):
    """Bring the node back mid-workflow.

    A permanently dead node can never be recovered from, so retries
    against it only ever exhaust. Recovery is observable only when the
    failure is transient - which is also the realistic case: a dropped
    acknowledgement, a node rebooting, a moment of interference.
    """

    def later():
        time.sleep(seconds)
        start_node(host)

    thread = threading.Thread(target=later, daemon=True)
    thread.start()
    return thread


def run(host, port, trials):
    from app.orchestration.state import Mode, Room
    from app.runtime import ApplicationRuntime

    def quiet(call, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return call(*args)

    wire = Wire(host, port)
    runtime = ApplicationRuntime(broker_host=host, broker_port=port,
                                 client_id="reliability", persist=False)
    quiet(runtime.connect)

    def once(intent, room, mode):
        if runtime.context.emergency_latched():
            quiet(runtime.execute_intent, "EMERGENCY_CLEAR")
        runtime.context.confirm_location(getattr(Room, room))
        runtime.context.set_mode(getattr(Mode, mode))

        mark = wire.mark()
        completed = True
        try:
            quiet(runtime.execute_intent, intent)
        except Exception:
            completed = False
        time.sleep(0.8)

        counts = tally(*wire.since(mark))
        counts["completed"] = completed
        if intent == "EMERGENCY":
            quiet(runtime.execute_intent, "EMERGENCY_CLEAR")
            time.sleep(0.5)
        return counts

    report = {}
    try:
        for label, prepare in (
                ("all nodes reachable", start_node),
                ("one node unreachable", lambda h: stop_node()),
                ("node returns mid-workflow", None)):
            transient = prepare is None
            if not transient:
                prepare(host)
            print()
            print(f"  {label.upper()}")
            print("  " + "-" * 72)
            print(f"  {'intent':<23}{'wf ok':>7}{'tasks':>7}{'ok':>5}"
                  f"{'fail':>6}{'retries':>9}{'recovered':>11}{'contained':>11}")
            print("  " + "-" * 72)

            for intent, room, mode in INTENTS:
                runs = []
                for _ in range(trials):
                    if transient:
                        # Down when the workflow starts, back before the
                        # executor exhausts its attempts.
                        stop_node()
                        return_node_after(host, 6.0)
                    runs.append(once(intent, room, mode))
                    if transient:
                        time.sleep(1.0)

                dispatched = sum(r["dispatched"] for r in runs)
                succeeded = sum(r["succeeded"] for r in runs)
                failed = sum(r["failed"] for r in runs)
                retries = sum(r["retries"] for r in runs)
                needed = sum(r["needed_retry"] for r in runs)
                recovered = sum(r["recovered"] for r in runs)
                completed = sum(1 for r in runs if r["completed"])

                baseline = report.get(intent)
                if baseline is None:
                    contained = "-"
                else:
                    # Actions in the baseline plan that were never
                    # dispatched once the workflow aborted.
                    skipped = max(0, baseline - dispatched)
                    contained = f"{skipped}"

                print(f"  {intent:<23}{completed}/{len(runs):<5}{dispatched:>7}"
                      f"{succeeded:>5}{failed:>6}{retries:>9}"
                      f"{recovered:>4}/{needed:<6}{contained:>11}")

                if baseline is None:
                    report[intent] = dispatched

            print("  " + "-" * 72)
    finally:
        wire.close()
        quiet(runtime.shutdown)
        start_node(host)

    print()
    print("  wf ok      workflows reaching completion / workflows started")
    print("  tasks      distinct command_ids published")
    print("  retries    republishes of an id already sent")
    print("  recovered  ids that succeeded only after a retry")
    print("  contained  planned actions never dispatched after an abort")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()

    print()
    print("=" * 78)
    print("  RELIABILITY - retries, recovery, completion, containment")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}   broker {args.host}")
    print("=" * 78)
    run(args.host, args.port, args.trials)
    return 0


if __name__ == "__main__":
    sys.exit(main())
