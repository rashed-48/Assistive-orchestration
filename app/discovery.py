"""Tell the nodes where the broker is, so they never carry its address.

A node compiled with a fixed broker IP works on exactly one network. Move
to a phone hotspot and the address it was built with no longer exists, so
it joins the wifi, fails to open a socket, and retries forever - looking
for all the world like a broken board.

The broker's host announces itself instead. Every couple of seconds it
sends one small UDP datagram to the local broadcast address:

    {"service": "assistive-broker", "broker": "192.168.43.17", "port": 1883}

A node listens for that on boot and connects to whatever it hears,
falling back to its compiled-in address when nothing answers. Nothing
here touches MQTT, the orchestrator, or any state: it only answers the
question "where is the broker", and only ever for listeners already on
the same network.
"""

import json
import socket
import threading

DEFAULT_DISCOVERY_PORT = 18830
DEFAULT_INTERVAL_SECONDS = 2.0
SERVICE_NAME = "assistive-broker"


def local_ip():
    """This host's address on the network it would use to reach others.

    Opening a UDP socket to an outside address sends nothing, but it
    makes the OS pick a route, and the chosen source address is the one
    a node on the LAN would have to talk to. Hostname lookup is not a
    substitute: it often answers 127.0.0.1.
    """

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def broadcast_targets(address):
    """Where to send so every node on this network hears it.

    255.255.255.255 is the general case, but some stacks and access
    points drop it while still passing a subnet-directed broadcast, so
    send both. A /24 is assumed, which is what home routers and phone
    hotspots hand out.
    """

    targets = ["255.255.255.255"]

    octets = address.split(".")
    if len(octets) == 4 and all(part.isdigit() for part in octets):
        subnet = ".".join(octets[:3]) + ".255"
        if subnet not in targets:
            targets.append(subnet)

    return targets


class BrokerBeacon:
    """Announces the broker's address until stopped.

    Runs on a daemon thread so it can never hold the process open, and
    swallows send errors: an unreachable network is a reason for a node
    to fall back, not for the application to fail.
    """

    def __init__(
        self,
        broker_port=1883,
        discovery_port=DEFAULT_DISCOVERY_PORT,
        interval=DEFAULT_INTERVAL_SECONDS,
        host=None,
    ):
        self.broker_port = broker_port
        self.discovery_port = discovery_port
        self.interval = interval
        self._host = host

        self._socket = None
        self._thread = None
        self._stop = threading.Event()
        self.sent = 0
        self.last_error = None

    @property
    def host(self):
        """Resolved late, so a beacon started before the network is up
        still announces the right address once it is."""

        return self._host or local_ip()

    def payload(self):
        return json.dumps({
            "service": SERVICE_NAME,
            "broker": self.host,
            "port": self.broker_port,
        }).encode("utf-8")

    def announce_once(self):
        """Send one round of datagrams. Returns how many were accepted."""

        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        message = self.payload()
        delivered = 0

        for target in broadcast_targets(self.host):
            try:
                self._socket.sendto(message, (target, self.discovery_port))
                delivered += 1
            except OSError as error:
                self.last_error = str(error)

        self.sent += delivered
        return delivered

    def _run(self):
        while not self._stop.is_set():
            self.announce_once()
            self._stop.wait(self.interval)

    def start(self):
        if self._thread is not None:
            return self

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="broker-beacon",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1.0)
            self._thread = None

        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
        return False
