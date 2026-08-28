"""End-to-end: confirmed intent -> real MQTT -> three mock ESP32 nodes.

This is the Phase 4 acceptance test. Nothing here is faked below the
Orchestrator:

    ApplicationRuntime
        Orchestrator            real
        WorkflowEngine          real (state-aware planning)
        MQTTDeviceExecutor      real
        MQTTClient              real paho client
        broker                  real mosquitto, isolated on a test port
        esp32_a/b/c             real SimulatedESP32 MQTT clients

MockDeviceExecutor is deliberately not used.

The test starts its own mosquitto on TEST_BROKER_PORT with a temporary
config, so it never touches the project's default broker on 1883 or
anything connected to it. If the mosquitto binary is not installed, the
whole module skips.
"""

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from app.devices.local_node_controller import resting_state
from app.devices.node_devices import (
    ESP32_A_DEVICES,
    ESP32_B_DEVICES,
    ESP32_C_DEVICES,
)
from app.devices.simulated_node import SimulatedESP32
from app.orchestration.state import Mode, PowerState, Room
from app.runtime import ApplicationRuntime


TEST_BROKER_PORT = 21883

NODE_IDS = ("esp32_a", "esp32_b", "esp32_c")

NODE_DEVICE_SETS = {
    "esp32_a": ESP32_A_DEVICES,
    "esp32_b": ESP32_B_DEVICES,
    "esp32_c": ESP32_C_DEVICES,
}


WINDOWS_INSTALL = Path(r"C:\Program Files\mosquitto\mosquitto.exe")


def find_mosquitto():
    found = shutil.which("mosquitto")
    if found:
        return found
    if WINDOWS_INSTALL.exists():
        return str(WINDOWS_INSTALL)
    return None


MOSQUITTO = find_mosquitto()

pytestmark = pytest.mark.skipif(
    MOSQUITTO is None,
    reason="mosquitto is not installed; the MQTT end-to-end test needs a broker",
)


def port_is_open(port, host="127.0.0.1", timeout=0.25):
    with socket.socket() as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


@pytest.fixture(scope="module")
def broker(tmp_path_factory):
    """An isolated mosquitto instance, separate from the project's own."""

    config = tmp_path_factory.mktemp("mosquitto") / "test.conf"
    config.write_text(
        f"listener {TEST_BROKER_PORT} 127.0.0.1\nallow_anonymous true\n",
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [MOSQUITTO, "-c", str(config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 10
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode(errors="replace")
            pytest.skip(f"test broker did not start: {output.strip()}")
        if port_is_open(TEST_BROKER_PORT):
            break
        time.sleep(0.1)
    else:
        process.terminate()
        pytest.skip("test broker did not open its port in time")

    yield ("127.0.0.1", TEST_BROKER_PORT)

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="module")
def nodes(broker):
    """Three independent mock ESP32 MQTT clients, all listening at once."""

    host, port = broker

    running = {}

    for node_id in NODE_IDS:
        node = SimulatedESP32(node_id, broker_host=host, broker_port=port)
        node.connect()
        running[node_id] = node

    for node_id, node in running.items():
        assert node.wait_until_ready(timeout=10), (
            f"{node_id} never subscribed to its command topic"
        )

    yield running

    for node in running.values():
        node.disconnect()


@pytest.fixture
def runtime(broker, nodes):
    """A real ApplicationRuntime wired to the test broker."""

    host, port = broker

    runtime = ApplicationRuntime(
        broker_host=host,
        broker_port=port,
        client_id=f"assistive_e2e_{time.time_ns()}",
    )

    assert runtime.connect(), (
        f"runtime could not reach the test broker: {runtime.connection_error}"
    )

    # Every node starts each test from its resting hardware state.
    for node in nodes.values():
        node.controller.device_states = {
            device: resting_state(device)
            for device in node.controller.devices
        }

    yield runtime

    runtime.shutdown()


def devices_touched(results):
    return [result["device"] for result in results]


def actions_taken(results):
    return [(result["action"], result["device"]) for result in results]


def wait_until(predicate, timeout=5):
    """Poll a condition that completes on the broker's own thread."""

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def hardware(nodes):
    """Merged simulated hardware state across all three nodes."""

    merged = {}
    for node in nodes.values():
        merged.update(node.get_device_states())
    return merged


# ==============================================================
# THE THREE NODES ARE REALLY THERE
# ==============================================================


def test_three_independent_nodes_are_connected(nodes):
    assert set(nodes) == set(NODE_IDS)

    for node_id, node in nodes.items():
        assert node.client.is_connected(), node_id
        assert node.command_topic == f"assistive/command/{node_id}"
        assert node.status_topic == f"assistive/status/{node_id}"

    # No physical device is owned by two nodes.
    owned = [d for node in nodes.values() for d in node.controller.devices]
    assert len(owned) == len(set(owned))


# ==============================================================
# SCENARIO 1 - FROM OUTSIDE
# ==============================================================


def test_scenario_1_prepare_for_sleep_from_outside(runtime, nodes):
    runtime.context.set_current_room(Room.OUTSIDE)
    runtime.context.set_mode(Mode.NONE)

    results = runtime.execute_intent("PREPARE_FOR_SLEEP")

    assert all(result["status"] == "success" for result in results)
    assert all(result["command_id"] for result in results)

    touched = devices_touched(results)

    # The planner routed through the entrance, because the user was outside.
    assert "exit_door" in touched
    assert "drawing_light" in touched
    assert "sleep_door" in touched

    # Every command was answered by the node that owns the device.
    for result in results:
        owner = next(
            node_id
            for node_id, devices in NODE_DEVICE_SETS.items()
            if result["device"] in devices
        )
        assert result["node"] == owner

    # Authoritative logical state followed the confirmed execution.
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.SLEEP

    # Simulated hardware moved too, and agrees with the logical view.
    pins = hardware(nodes)
    assert pins["sleep_light"] == "ON"
    assert pins["sleep_bed"] == "READY"
    assert pins["sleep_door"] == "CLOSED"
    assert pins["exit_door"] == "CLOSED"
    assert pins["drawing_light"] == "OFF"

    assert runtime.context.get_state().sleep.light == PowerState.ON


# ==============================================================
# SCENARIO 2 - ALREADY IN THE SLEEP ROOM
# ==============================================================


def test_scenario_2_prepare_for_sleep_already_in_the_sleep_room(runtime, nodes):
    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.NONE)

    results = runtime.execute_intent("PREPARE_FOR_SLEEP")

    assert all(result["status"] == "success" for result in results)

    taken = actions_taken(results)

    # State-aware planning: the user is already there, so no room is
    # entered or left. No door moves at all.
    assert not [
        action
        for action, _ in taken
        if action in {"OPEN_DOOR", "CLOSE_DOOR"}
    ], taken

    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.SLEEP

    pins = hardware(nodes)
    assert pins["sleep_light"] == "ON"
    assert pins["sleep_bed"] == "READY"
    assert pins["sleep_door"] == "CLOSED"


def test_scenario_2_plans_fewer_actions_than_scenario_1(runtime):
    runtime.context.set_current_room(Room.OUTSIDE)
    runtime.context.set_mode(Mode.NONE)
    from_outside = len(runtime.execute_intent("PREPARE_FOR_SLEEP"))

    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.NONE)
    already_there = len(runtime.execute_intent("PREPARE_FOR_SLEEP"))

    assert already_there < from_outside


# ==============================================================
# SCENARIO 3 - FROM THE RELAX ROOM
# ==============================================================


def test_scenario_3_prepare_for_sleep_from_the_relax_room(runtime, nodes):
    runtime.context.set_current_room(Room.RELAX_ROOM)
    runtime.context.set_mode(Mode.RELAX)
    runtime.context.state.relax.light = PowerState.ON
    runtime.context.state.relax.tv = PowerState.ON

    # Bring the simulated hardware in line with that starting point.
    nodes["esp32_a"].controller.device_states["relax_light"] = "ON"
    nodes["esp32_a"].controller.device_states["relax_tv"] = "ON"

    results = runtime.execute_intent("PREPARE_FOR_SLEEP")

    assert all(result["status"] == "success" for result in results)

    taken = actions_taken(results)

    # The relax room was shut down before leaving it.
    assert ("LIGHT_OFF", "relax_light") in taken
    assert ("TV_OFF", "relax_tv") in taken

    # The user moved via the drawing room into the sleep room.
    assert ("OPEN_DOOR", "relax_door") in taken
    assert ("OPEN_DOOR", "sleep_door") in taken

    # No entrance transition: the user never went outside.
    assert "exit_door" not in devices_touched(results)

    # Nothing unrelated was actuated.
    assert "study_table" not in devices_touched(results)
    assert "meal_light" not in devices_touched(results)

    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.SLEEP
    assert runtime.context.get_return_target() == Room.RELAX_ROOM

    pins = hardware(nodes)
    assert pins["relax_light"] == "OFF"
    assert pins["relax_tv"] == "OFF"
    assert pins["relax_door"] == "CLOSED"
    assert pins["sleep_light"] == "ON"
    assert pins["sleep_bed"] == "READY"


# ==============================================================
# CONSECUTIVE COMMANDS SHARE ONE RUNTIME
# ==============================================================


def test_a_second_command_plans_against_the_state_the_first_committed(runtime):
    runtime.context.set_current_room(Room.OUTSIDE)
    runtime.context.set_mode(Mode.NONE)

    runtime.execute_intent("PREPARE_FOR_SLEEP")
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM

    # WAKE_UP only does anything because the first command committed the
    # move into the sleep room.
    results = runtime.execute_intent("WAKE_UP")

    assert actions_taken(results) == [("RESET_BED", "sleep_bed")]
    assert runtime.context.get_current_mode() == Mode.NONE
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM


# ==============================================================
# A LOST ACKNOWLEDGEMENT OVER THE REAL BROKER
# ==============================================================


def test_a_lost_ack_retries_without_the_node_acting_twice(runtime, nodes):
    """The E5 scenario, end to end.

    The node carries out the action and answers. The answer is dropped
    before the executor sees it, so the executor retries with the same
    command id. The node must recognise the retry, re-acknowledge, and
    leave the hardware alone.
    """

    from app.orchestration.actions import Action, ActionType

    node = nodes["esp32_b"]

    executed_before = node.executed_count
    duplicates_before = node.duplicate_count

    real_wait = runtime.mqtt_client.wait_for_status
    dropped = []

    def drop_the_first_answer(command_id, timeout=5):
        status = real_wait(command_id, timeout=timeout)

        if status is not None and not dropped:
            dropped.append(command_id)
            return None

        return status

    runtime.mqtt_client.wait_for_status = drop_the_first_answer

    try:
        result = runtime.device_executor.execute(
            Action(ActionType.OPEN_DOOR, "sleep_door"),
            timeout=3,
        )
    finally:
        runtime.mqtt_client.wait_for_status = real_wait

    # The acknowledgement really was dropped, so a retry really happened.
    assert dropped

    # The executor still succeeded: the retained acknowledgement from the
    # first attempt satisfied the retry.
    assert result["status"] == "success"

    # The retry reaches the node over the broker on its own thread, so
    # wait for it rather than racing it.
    assert wait_until(
        lambda: node.duplicate_count == duplicates_before + 1
    ), "the node never saw the retry"

    # The safety property: the door was opened exactly once.
    assert node.executed_count == executed_before + 1

    assert node.get_device_states()["sleep_door"] == "OPEN"

    # Both attempts carried one identity.
    assert len(set(dropped)) == 1
    assert result["command_id"] == dropped[0]


def test_a_full_workflow_survives_a_lost_ack(runtime, nodes):
    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.NONE)

    executed_before = sum(node.executed_count for node in nodes.values())

    real_wait = runtime.mqtt_client.wait_for_status
    dropped = []

    def drop_the_first_answer(command_id, timeout=5):
        status = real_wait(command_id, timeout=timeout)
        if status is not None and not dropped:
            dropped.append(command_id)
            return None
        return status

    runtime.mqtt_client.wait_for_status = drop_the_first_answer

    try:
        results = runtime.execute_intent("PREPARE_FOR_SLEEP")
    finally:
        runtime.mqtt_client.wait_for_status = real_wait

    assert dropped
    assert all(result["status"] == "success" for result in results)

    executed_after = sum(node.executed_count for node in nodes.values())

    # One physical execution per planned action, despite the retry.
    assert executed_after - executed_before == len(results)

    # And the logical state was applied once.
    assert runtime.context.get_current_mode() == Mode.SLEEP
    assert runtime.context.get_state().sleep.light == PowerState.ON


# ==============================================================
# THE NODES ARE HARDWARE ONLY
# ==============================================================


def test_mock_nodes_never_touch_the_authoritative_state(nodes):
    """Architectural rule 5.

    A node knows about its own pins and MQTT. It must not know about
    ContextManager, Orchestrator, WorkflowEngine, or intents.
    """

    import ast

    forbidden_modules = {
        "app.orchestration.context_manager",
        "app.orchestration.state",
        "app.orchestration.orchestrator",
        "app.orchestration.workflow_engine",
    }

    forbidden_names = {
        "ContextManager",
        "Orchestrator",
        "WorkflowEngine",
        "EnvironmentState",
    }

    node_source_dir = Path("app/devices")

    for filename in ("simulated_node.py", "local_node_controller.py"):
        tree = ast.parse(
            (node_source_dir / filename).read_text(encoding="utf-8")
        )

        imported = set()
        referenced = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)

        assert imported & forbidden_modules == set(), filename
        assert referenced & forbidden_names == set(), filename

    for node in nodes.values():
        assert not hasattr(node, "context")
        assert not hasattr(node.controller, "context")


# ==============================================================
# EMERGENCY LIFECYCLE OVER THE REAL BROKER
# ==============================================================


def test_emergency_entry_over_real_mqtt_leaves_the_escape_route_open(runtime, nodes):
    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.SLEEP)

    results = runtime.execute_intent("EMERGENCY")

    assert all(result["status"] == "success" for result in results)
    assert runtime.context.get_current_mode() == Mode.EMERGENCY

    # Nothing was closed.
    assert not [
        result for result in results if result["action"] == "CLOSE_DOOR"
    ]

    pins = hardware(nodes)
    assert pins["buzzer"] == "ON"
    assert pins["exit_door"] == "OPEN"
    for door in ("study_door", "relax_door", "sleep_door", "meal_door"):
        assert pins[door] == "OPEN", door

    # Logical state agrees with the hardware.
    environment = runtime.context.to_dict()
    assert environment["buzzer"] == "ON"
    assert environment["exit_door"] == "OPEN"


def test_normal_commands_are_blocked_over_real_mqtt(runtime, nodes):
    from app.runtime import EmergencyActive

    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.NONE)
    runtime.execute_intent("EMERGENCY")

    executed_before = sum(node.executed_count for node in nodes.values())

    with pytest.raises(EmergencyActive):
        runtime.execute_intent("PREPARE_FOR_SLEEP")

    # Not a single command reached the nodes.
    assert sum(node.executed_count for node in nodes.values()) == executed_before
    assert runtime.context.get_current_mode() == Mode.EMERGENCY


def test_emergency_clear_over_real_mqtt_restores_the_house(runtime, nodes):
    runtime.context.set_current_room(Room.SLEEP_ROOM)
    runtime.context.set_mode(Mode.SLEEP)

    runtime.execute_intent("EMERGENCY")
    assert hardware(nodes)["exit_door"] == "OPEN"

    results = runtime.execute_intent("EMERGENCY_CLEAR")

    assert all(result["status"] == "success" for result in results)

    pins = hardware(nodes)
    assert pins["buzzer"] == "OFF"
    assert pins["exit_door"] == "CLOSED"
    for door in ("study_door", "relax_door", "sleep_door", "meal_door"):
        assert pins[door] == "CLOSED", door

    assert runtime.context.get_current_mode() == Mode.NONE

    # Clearing did not invent a location.
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM


def test_repeated_emergency_over_real_mqtt_sends_nothing_the_second_time(runtime, nodes):
    runtime.context.set_current_room(Room.RELAX_ROOM)
    runtime.context.set_mode(Mode.RELAX)

    runtime.execute_intent("EMERGENCY")
    executed_after_first = sum(node.executed_count for node in nodes.values())

    second = runtime.execute_intent("EMERGENCY")

    assert second == []
    assert sum(node.executed_count for node in nodes.values()) == executed_after_first


def test_a_lost_ack_during_emergency_does_not_double_actuate(runtime, nodes):
    runtime.context.set_current_room(Room.RELAX_ROOM)
    runtime.context.set_mode(Mode.RELAX)

    node = nodes["esp32_a"]
    executed_before = node.executed_count
    duplicates_before = node.duplicate_count

    real_wait = runtime.mqtt_client.wait_for_status
    dropped = []

    def drop_the_first_answer(command_id, timeout=5):
        status = real_wait(command_id, timeout=timeout)
        if status is not None and not dropped:
            dropped.append(command_id)
            return None
        return status

    runtime.mqtt_client.wait_for_status = drop_the_first_answer
    try:
        results = runtime.execute_intent("EMERGENCY")
    finally:
        runtime.mqtt_client.wait_for_status = real_wait

    assert dropped
    assert all(result["status"] == "success" for result in results)

    assert wait_until(
        lambda: node.duplicate_count == duplicates_before + 1
    ), "the node never saw the emergency retry"

    # The buzzer sounded once, not twice.
    assert hardware(nodes)["buzzer"] == "ON"
    assert runtime.context.get_current_mode() == Mode.EMERGENCY
