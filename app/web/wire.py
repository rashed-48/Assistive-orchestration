"""Watch the MQTT bus and narrate it to the event stream.

The interface's execution view is driven by this and nothing else. It
does not ask the executor what it sent or the orchestrator what it
believes; it subscribes to the same topics the nodes use and reports
what actually crossed the wire, with the time between each leg:

    command   the executor published to assistive/command/<node>
    ack       the node said it received it          (dispatch -> ack)
    complete  the node said the hardware has acted  (ack -> complete)

Because it is a separate subscriber, the browser sees the ack even
though the executor discards it, and sees a retry as a second command
carrying the same id - which is what a retry is.

It also answers "is that node alive?" the honest way: by sending each
node an action it does not have and expecting an error back. A node
that answers is reachable; nothing moved to find out.
"""

import json
import threading
import time
import uuid

import paho.mqtt.client as mqtt

NODES = ("esp32_a", "esp32_b", "esp32_c")
PROBE_ACTION = "PROBE_LIVENESS"


class WireObserver:

    def __init__(self, bus, broker_host, broker_port=1883):
        self.bus = bus
        self.broker_host = broker_host
        self.broker_port = broker_port

        self._lock = threading.Lock()
        self._commands = {}       # command_id -> {"t": perf, "node", "device", "action", "sends"}
        self._acks = {}           # command_id -> perf
        self._probes = {}         # command_id -> node
        self._last_seen = {}      # node -> wall-clock seconds
        self.connected = False

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"wire_{uuid.uuid4().hex[:8]}",
        )
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ---- lifecycle ---------------------------------------------------

    def start(self):
        try:
            self._client.connect(self.broker_host, self.broker_port)
            self._client.loop_start()
        except OSError as error:
            self.bus.emit("wire_error", message=str(error))
        return self

    def stop(self):
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = True
        client.subscribe("assistive/command/#", qos=1)
        client.subscribe("assistive/status/#", qos=1)
        self.bus.emit("wire_connected", broker=f"{self.broker_host}:{self.broker_port}")

    def _on_disconnect(self, client, userdata, flags, reason, properties=None):
        self.connected = False
        self.bus.emit("wire_disconnected")

    # ---- traffic -----------------------------------------------------

    def _on_message(self, client, userdata, message):
        now = time.perf_counter()
        try:
            payload = json.loads(message.payload.decode())
        except ValueError:
            return

        node = message.topic.rsplit("/", 1)[-1]
        command_id = payload.get("command_id")
        if not command_id:
            return

        if "/command/" in message.topic:
            self._saw_command(now, node, command_id, payload)
        else:
            self._saw_status(now, node, command_id, payload)

    def _saw_command(self, now, node, command_id, payload):
        with self._lock:
            entry = self._commands.get(command_id)
            if entry is None:
                entry = {"t": now, "node": node,
                         "device": payload.get("device"),
                         "action": payload.get("action"), "sends": 0}
                self._commands[command_id] = entry
            entry["sends"] += 1
            retry = entry["sends"] > 1
            is_probe = command_id in self._probes

        if is_probe:
            return

        self.bus.emit(
            "wire",
            phase="command",
            node=node,
            device=payload.get("device"),
            action=payload.get("action"),
            command_id=command_id,
            retry=retry,
            attempt=entry["sends"],
        )

    def _saw_status(self, now, node, command_id, payload):
        phase = payload.get("phase", "complete")

        with self._lock:
            self._last_seen[node] = time.time()
            sent = self._commands.get(command_id)
            is_probe = command_id in self._probes

            if phase == "ack":
                self._acks[command_id] = now
                since_send = (now - sent["t"]) * 1000.0 if sent else None
                since_ack = None
            else:
                acked = self._acks.get(command_id)
                since_send = (now - sent["t"]) * 1000.0 if sent else None
                since_ack = (now - acked) * 1000.0 if acked else None

        if is_probe:
            if phase != "ack":
                self.bus.emit("node_probe", node=node, reachable=True,
                              ms=round(since_send, 1) if since_send else None)
            return

        self.bus.emit(
            "wire",
            phase=phase,
            node=node,
            device=payload.get("device"),
            action=payload.get("action"),
            command_id=command_id,
            status=payload.get("status"),
            duplicate=bool(payload.get("duplicate")),
            since_send_ms=round(since_send, 1) if since_send is not None else None,
            since_ack_ms=round(since_ack, 1) if since_ack is not None else None,
        )

    # ---- liveness ----------------------------------------------------

    def probe(self, wait=3.0):
        """Ask every node whether it is there. Returns {node: bool}.

        Uses an action no node implements, so the reply is always an
        error and no hardware is touched. A node that does not answer
        within `wait` is reported unreachable.
        """

        if not self.connected:
            return {node: False for node in NODES}

        ids = {}
        with self._lock:
            for node in NODES:
                command_id = str(uuid.uuid4())
                self._probes[command_id] = node
                ids[node] = command_id

        for node, command_id in ids.items():
            self._client.publish(
                f"assistive/command/{node}",
                json.dumps({"device": "probe", "action": PROBE_ACTION,
                            "parameters": {}, "command_id": command_id}),
                qos=1,
            )

        started = time.time()
        time.sleep(wait)

        result = {}
        with self._lock:
            for node in NODES:
                result[node] = self._last_seen.get(node, 0) >= started
            for command_id in ids.values():
                self._probes.pop(command_id, None)
                self._commands.pop(command_id, None)
                self._acks.pop(command_id, None)

        self.bus.emit("nodes", **result)
        return result

    def last_seen(self):
        with self._lock:
            return dict(self._last_seen)
