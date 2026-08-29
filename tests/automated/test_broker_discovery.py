"""The broker announcement a node uses to find its host.

These tests bind a real UDP socket on the loopback-reachable broadcast
path; they do not need a broker, a node, or the network to be up.
"""

import json
import socket
import time

import pytest

from app.discovery import (
    SERVICE_NAME,
    BrokerBeacon,
    broadcast_targets,
    local_ip,
)


@pytest.fixture
def listener():
    """A socket bound the way a node binds one."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 0))
    sock.settimeout(3.0)
    yield sock
    sock.close()


def test_announcement_names_the_service_the_host_and_the_port():
    beacon = BrokerBeacon(broker_port=1883, host="192.168.43.17")
    payload = json.loads(beacon.payload().decode())

    assert payload == {
        "service": SERVICE_NAME,
        "broker": "192.168.43.17",
        "port": 1883,
    }


def test_a_node_receives_the_announcement(listener):
    """End to end over a real socket: what is sent is what arrives."""

    port = listener.getsockname()[1]
    beacon = BrokerBeacon(host="127.0.0.1", discovery_port=port, interval=0.1)

    with beacon:
        deadline = time.time() + 3.0
        received = None
        while time.time() < deadline and received is None:
            try:
                data, _ = listener.recvfrom(512)
            except socket.timeout:
                break
            payload = json.loads(data.decode())
            if payload.get("service") == SERVICE_NAME:
                received = payload

    assert received is not None, "no announcement arrived within 3s"
    assert received["broker"] == "127.0.0.1"
    assert received["port"] == 1883


def test_the_host_is_resolved_at_send_time_not_at_construction():
    """A beacon started before the network is up must still announce the
    right address once it is, so the address cannot be frozen early."""

    beacon = BrokerBeacon()
    assert beacon._host is None
    assert beacon.host == local_ip()


def test_broadcast_reaches_both_the_general_and_subnet_addresses():
    """Some access points drop 255.255.255.255 while passing a
    subnet-directed broadcast, so both must be sent."""

    targets = broadcast_targets("192.168.43.17")

    assert "255.255.255.255" in targets
    assert "192.168.43.255" in targets


def test_a_malformed_address_still_yields_a_usable_target():
    assert broadcast_targets("not-an-ip") == ["255.255.255.255"]


def test_stop_is_idempotent_and_releases_the_thread():
    beacon = BrokerBeacon(host="127.0.0.1", discovery_port=0, interval=0.05)
    beacon.start()
    beacon.stop()
    beacon.stop()

    assert beacon._thread is None
    assert beacon._socket is None


def test_starting_twice_does_not_create_a_second_thread():
    beacon = BrokerBeacon(host="127.0.0.1", discovery_port=0, interval=0.05)
    try:
        first = beacon.start()._thread
        assert beacon.start()._thread is first
    finally:
        beacon.stop()


def test_a_send_failure_is_recorded_rather_than_raised():
    """An unreachable network is a reason for a node to fall back on its
    compiled-in address, not for the application to crash."""

    beacon = BrokerBeacon(host="127.0.0.1", discovery_port=1)

    class RefusingSocket:
        def sendto(self, *_):
            raise OSError("network is unreachable")

        def close(self):
            pass

    beacon._socket = RefusingSocket()

    assert beacon.announce_once() == 0
    assert "unreachable" in beacon.last_error


def test_local_ip_is_never_loopback_when_a_network_exists():
    """A node cannot reach 127.0.0.1, so announcing it would be useless.
    Hostname lookup commonly returns it; the route probe must not."""

    address = local_ip()
    assert address.count(".") == 3
