"""Bench-test one node - real ESP32 or simulated - over MQTT.

Speaks the same protocol the application uses, so a board that passes
this will work with the real system. Nothing here touches the
orchestrator; it is a hardware bring-up tool.

    python -m tools.bench_node --host 192.168.0.103 --node esp32_b \
        --device sleep_light --action LIGHT_ON

    python -m tools.bench_node --host 192.168.0.103 --node esp32_b --suite

When nothing answers, watch the wire instead - this prints every
command and status on the broker, so you can see whether the board
subscribed at all:

    python -m tools.bench_node --host 192.168.0.103 --watch

The suite checks the three rules a node must satisfy:

    1. it echoes command_id back unchanged
    2. a repeated command_id is re-acknowledged, NOT re-actuated
    3. an unknown device or action answers "error", never silence

--strict adds a fourth: an action belonging to a different kind of
device is refused. Real firmware enforces this; the simulated node
does not, so it is opt-in and excluded from the baseline score.
"""

import argparse
import json
import sys
import time
import uuid

import paho.mqtt.client as mqtt


class Bench:
    def __init__(self, host, port, node):
        self.node = node
        self.command_topic = f"assistive/command/{node}"
        self.replies = []

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bench_{uuid.uuid4().hex[:8]}",
        )
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.subscribe(f"assistive/status/{node}", qos=1)
        self.client.loop_start()
        time.sleep(0.4)

    def _on_message(self, client, userdata, message):
        try:
            self.replies.append(json.loads(message.payload.decode()))
        except ValueError:
            pass

    def send(self, device, action, command_id=None, wait=6.0, settle=0.0,
             phase="complete"):
        """Publish one command and wait for its acknowledgement.

        Only replies that arrive after this call are considered. A
        duplicate carries the same command_id as the original, so
        matching on the id alone would return the earlier reply and
        never observe the new one.
        """

        command_id = command_id or str(uuid.uuid4())
        since = len(self.replies)

        self.client.publish(
            self.command_topic,
            json.dumps({
                "device": device,
                "action": action,
                "parameters": {},
                "command_id": command_id,
            }),
            qos=1,
        )

        self.last_since = since
        self.last_command_id = command_id

        deadline = time.time() + wait
        while time.time() < deadline:
            for reply in self.replies[since:]:
                # A node answers twice: "ack" on arrival and "complete"
                # once the hardware has acted. Only the second carries a
                # status. Older firmware sends no phase at all.
                if (reply.get("command_id") == command_id
                        and reply.get("phase", "complete") == phase):
                    # Give any second responder time to be heard before
                    # reporting; see the solo check in the suite.
                    if settle:
                        time.sleep(settle)
                    return reply
            time.sleep(0.05)

        return None

    def replies_for(self, command_id, since=0):
        """Every reply carrying this command_id, oldest first."""

        return [r for r in self.replies[since:]
                if r.get("command_id") == command_id
                and r.get("phase", "complete") == "complete"]

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def check(label, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    return passed


def run_suite(bench, device, on_action, off_action, strict=False):
    print(f"\nBench suite against {bench.node} / {device}\n" + "-" * 58)
    results = []

    # 1 - a plain command is acknowledged, with the id echoed back
    cid = str(uuid.uuid4())
    reply = bench.send(device, on_action, command_id=cid, settle=0.8)
    results.append(check("command is acknowledged", reply is not None,
                         "no reply within timeout" if reply is None else ""))
    if reply is None:
        print("\n  Nothing is answering. Check: node id, broker host, "
              "wifi, and that the board subscribed to\n  "
              f"{bench.command_topic}")
        return False

    # Before anything else: exactly one thing may be answering. A
    # simulated node left running on the same node id also replies, and
    # every check below would then be scoring whichever answer arrived
    # first - passing or failing for reasons that have nothing to do
    # with the board under test.
    answers = bench.replies_for(cid, bench.last_since)
    solo = check("exactly one node is answering", len(answers) == 1,
                 "" if len(answers) == 1 else
                 f"{len(answers)} replies to one command_id")
    results.append(solo)
    if not solo:
        print()
        print("  More than one responder is on this node id. Stop any")
        print("  simulated node still running as " + bench.node + ":")
        print("    Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |")
        print("      Where-Object { $_.CommandLine -match 'simulated_node' } |")
        print("      Stop-Process -Id { $_.ProcessId } -Force")
        print("  Results below are unreliable until then.")
        print()

    results.append(check("command_id echoed unchanged", reply.get("command_id") == cid))
    results.append(check("status is success", reply.get("status") == "success",
                         f"got {reply.get('status')!r}"))
    results.append(check("node field is correct", reply.get("node") == bench.node,
                         f"got {reply.get('node')!r}"))
    results.append(check("device echoed", reply.get("device") == device))

    # 2 - the same id again must be answered but NOT re-actuated
    repeat = bench.send(device, on_action, command_id=cid)
    results.append(check("duplicate id is answered again", repeat is not None,
                         "silence - the retry would look like a timeout" if repeat is None else ""))
    results.append(check("duplicate reply is a fresh message",
                         repeat is not None and repeat is not reply))
    print("         (watch the hardware: it must NOT move on the duplicate)")

    # 3 - errors are reported rather than ignored
    bad = bench.send(device, "FLY_TO_THE_MOON", wait=4.0)
    results.append(check("unknown action answers error",
                         bad is not None and bad.get("status") == "error",
                         "silence" if bad is None else f"got {bad.get('status')!r}"))

    ghost = bench.send("no_such_device", on_action, wait=4.0)
    results.append(check("unknown device answers error",
                         ghost is not None and ghost.get("status") == "error",
                         "silence" if ghost is None else f"got {ghost.get('status')!r}"))

    if strict:
        # A light must not accept a TV action. The pins are the same;
        # only the device table says which is which, so a node that
        # switches on kind alone will wrongly report success here.
        foreign = "TV_ON" if not on_action.startswith("TV") else "LIGHT_ON"
        reply = bench.send(device, foreign, wait=4.0)
        results.append(check(f"{foreign} refused on this device",
                             reply is not None and reply.get("status") == "error",
                             "silence" if reply is None else f"got {reply.get('status')!r}"))

    # leave the device as we found it
    bench.send(device, off_action)

    passed = sum(1 for r in results if r)
    print("-" * 58)
    print(f"  {passed}/{len(results)} checks passed")
    return passed == len(results)


def watch(host, port):
    """Print every message on assistive/# until interrupted."""

    seen = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"watch_{uuid.uuid4().hex[:8]}")
    client.on_message = lambda c, u, m: seen.append(
        (time.strftime("%H:%M:%S"), m.topic, m.payload.decode(errors="replace")))
    client.connect(host, port)
    client.subscribe("assistive/#", qos=1)
    client.loop_start()

    print(f"Watching assistive/# on {host}:{port} - Ctrl-C to stop.")
    print("Nothing appears until something is sent. If a command shows up")
    print("with no status line after it, the board is not listening.")
    print()

    printed = 0
    try:
        while True:
            while printed < len(seen):
                stamp, topic, body = seen[printed]
                arrow = "->" if "/command/" in topic else "<-"
                print(f"  {stamp} {arrow} {topic}")
                print(f"       {body}")
                printed += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
        print(f"stopped after {len(seen)} messages")
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


def monitor(host, port, node, device, every):
    """Probe the node on a timer and report only when it changes state.

    The probe is a deliberately invalid action. A node answers it with
    "error", which proves the whole round trip - broker out, node in,
    node out, broker back - without moving any hardware.

    This is the other half of the board's own heartbeat. A board
    printing "[alive] mqtt up" while this prints "unreachable" means
    the board is fine and the path between it and the broker is not.
    """

    bench = Bench(host, port, node)
    print(f"Probing {node} every {every}s - Ctrl-C to stop.")
    print("Only changes are printed; silence means nothing changed.")
    print()

    state = None
    since = time.time()
    ups = downs = 0
    try:
        while True:
            started = time.time()
            reply = bench.send(device, "PROBE_LIVENESS", wait=min(every, 4.0))
            now = "reachable" if reply is not None else "unreachable"

            if now != state:
                stamp = time.strftime("%H:%M:%S")
                if state is None:
                    print(f"  {stamp}  {now}")
                else:
                    held = int(time.time() - since)
                    print(f"  {stamp}  {state} -> {now}   "
                          f"(previous state held {held}s)")
                    if now == "reachable":
                        ups += 1
                    else:
                        downs += 1
                state, since = now, time.time()

            time.sleep(max(0.0, every - (time.time() - started)))
    except KeyboardInterrupt:
        held = int(time.time() - since)
        print()
        print(f"stopped. finished {state} for {held}s, "
              f"{downs} dropout(s), {ups} recovery(ies)")
    finally:
        bench.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--node", default="esp32_b")
    parser.add_argument("--device", default="sleep_light")
    parser.add_argument("--action", default="LIGHT_ON")
    parser.add_argument("--off-action", default="LIGHT_OFF",
                        help="how the suite restores the device afterwards")
    parser.add_argument("--suite", action="store_true",
                        help="run the full protocol conformance suite")
    parser.add_argument("--strict", action="store_true",
                        help="also require that a foreign action is refused")
    parser.add_argument("--watch", action="store_true",
                        help="print all broker traffic instead of testing")
    parser.add_argument("--monitor", action="store_true",
                        help="probe the node on a timer, reporting dropouts")
    parser.add_argument("--every", type=float, default=10.0,
                        help="seconds between probes for --monitor")
    args = parser.parse_args()

    if args.monitor:
        try:
            return monitor(args.host, args.port, args.node,
                           args.device, args.every)
        except OSError as error:
            print(f"Cannot reach the broker at {args.host}:{args.port} - {error}")
            return 2

    if args.watch:
        try:
            return watch(args.host, args.port)
        except OSError as error:
            print(f"Cannot reach the broker at {args.host}:{args.port} - {error}")
            return 2

    try:
        bench = Bench(args.host, args.port, args.node)
    except OSError as error:
        print(f"Cannot reach the broker at {args.host}:{args.port} - {error}")
        return 2

    try:
        if args.suite:
            ok = run_suite(bench, args.device, args.action, args.off_action,
                           strict=args.strict)
            return 0 if ok else 1

        reply = bench.send(args.device, args.action)
        if reply is None:
            print(f"No acknowledgement for {args.action} {args.device}")
            return 1

        print(json.dumps(reply, indent=2))
        return 0
    finally:
        bench.close()


if __name__ == "__main__":
    sys.exit(main())
