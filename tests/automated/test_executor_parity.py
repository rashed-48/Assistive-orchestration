"""Executor equivalence and MQTT-path state commitment.

Audit finding E3/§18: workflow-level state commitment once lived inside
MockDeviceExecutor, so the mock path committed room/mode and the MQTT path
silently did not. These tests pin the invariant that the same intent, from the
same starting state, produces the same logical outcome regardless of which
executor carried it out.

MQTTDeviceExecutor is exercised through an in-memory transport stub. No
broker, no network, no hardware.
"""

import pytest

from app.devices.device_registry import DEVICE_NODE_MAP
from app.devices.mock_device import MockDeviceExecutor
from app.devices.mqtt_device import ActionExecutionError, MQTTDeviceExecutor
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.state import (
    Mode,
    PowerState,
    PreparationState,
    Room,
)

from tests.automated.support import (
    FakeMQTTTransport,
    build_context,
    logical_snapshot,
    quiet,
)


# (intent, starting room, starting mode, starting return target)
PARITY_SCENARIOS = [
    ("STUDY_MODE", Room.OUTSIDE, Mode.NONE, None),
    ("STUDY_MODE", Room.RELAX_ROOM, Mode.RELAX, None),
    ("RELAX_MODE", Room.STUDY_ROOM, Mode.STUDY, None),
    ("PREPARE_FOR_SLEEP", Room.RELAX_ROOM, Mode.RELAX, Room.STUDY_ROOM),
    ("PREPARE_FOR_MEAL", Room.SLEEP_ROOM, Mode.SLEEP, None),
    ("MEDICATION", Room.RELAX_ROOM, Mode.RELAX, None),
    ("MEDICATION", Room.SLEEP_ROOM, Mode.SLEEP, None),
    ("WAKE_UP", Room.SLEEP_ROOM, Mode.SLEEP, None),
    ("WAKE_UP", Room.STUDY_ROOM, Mode.STUDY, None),
    ("LEAVE_ROOM", Room.STUDY_ROOM, Mode.STUDY, None),
    ("RETURN_TO_ROOM", Room.OUTSIDE, Mode.NONE, Room.STUDY_ROOM),
    ("SHUTDOWN_ENVIRONMENT", Room.MEAL_ROOM, Mode.MEAL, None),
    ("EMERGENCY", Room.RELAX_ROOM, Mode.RELAX, None),
]


@pytest.mark.parametrize(
    "intent,room,mode,return_target",
    PARITY_SCENARIOS,
    ids=[f"{s[0]}-from-{s[1].value}" for s in PARITY_SCENARIOS],
)
def test_mock_and_mqtt_executors_reach_identical_logical_state(
    intent,
    room,
    mode,
    return_target,
):
    mock_context = build_context(room, mode, return_target)
    mock_executor = MockDeviceExecutor(mock_context)

    with quiet():
        Orchestrator(mock_context, mock_executor).execute_intent(intent)

    mqtt_context = build_context(room, mode, return_target)
    transport = FakeMQTTTransport()

    with quiet():
        Orchestrator(
            mqtt_context,
            MQTTDeviceExecutor(transport),
        ).execute_intent(intent)

    assert logical_snapshot(mock_context) == logical_snapshot(mqtt_context)

    # Both executors must have been handed the same number of actions.
    assert len(transport.published) == len(mock_executor.actions)


# ==============================================================
# AUTHORITATIVE MQTT PATH COMMITS ROOM AND MODE
# ==============================================================


EXPECTED_RELAX_TO_SLEEP_COMMANDS = [
    ("LIGHT_OFF", "relax_light"),
    ("TV_OFF", "relax_tv"),
    ("OPEN_DOOR", "relax_door"),
    ("CLOSE_DOOR", "relax_door"),
    ("LIGHT_ON", "drawing_light"),
    ("OPEN_DOOR", "sleep_door"),
    ("CLOSE_DOOR", "sleep_door"),
    ("LIGHT_ON", "sleep_light"),
    ("PREPARE_BED", "sleep_bed"),
    ("LIGHT_OFF", "drawing_light"),
]


def test_orchestrator_commits_room_and_mode_after_successful_mqtt_execution():
    context = build_context(
        Room.RELAX_ROOM,
        Mode.RELAX,
        return_target=Room.STUDY_ROOM,
    )
    context.state.relax.light = PowerState.ON
    context.state.relax.tv = PowerState.ON

    transport = FakeMQTTTransport()

    with quiet():
        results = Orchestrator(
            context,
            MQTTDeviceExecutor(transport),
        ).execute_intent("PREPARE_FOR_SLEEP")

    # Every action was acknowledged.
    assert len(results) == len(EXPECTED_RELAX_TO_SLEEP_COMMANDS)
    assert all(result["status"] == "success" for result in results)

    # Every action reached the wire, in order, addressed to its owning node
    # and carrying a correlation id.
    sent = [
        (message["payload"]["action"], message["payload"]["device"])
        for message in transport.published
    ]
    assert sent == EXPECTED_RELAX_TO_SLEEP_COMMANDS

    for message in transport.published:
        payload = message["payload"]
        node = DEVICE_NODE_MAP[payload["device"]]

        assert message["topic"] == f"assistive/command/{node}"
        assert payload["command_id"]

    # Logical state followed the confirmed physical execution.
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.SLEEP
    assert context.state.sleep.light == PowerState.ON
    assert context.state.sleep.bed == PreparationState.READY
    assert context.state.relax.light == PowerState.OFF
    assert context.state.relax.tv == PowerState.OFF


def test_mqtt_device_error_leaves_room_and_mode_uncommitted():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    # The sixth command (OPEN_DOOR sleep_door) is rejected by its node.
    transport = FakeMQTTTransport(fail_on={6})

    with pytest.raises(ActionExecutionError):
        with quiet():
            Orchestrator(
                context,
                MQTTDeviceExecutor(transport),
            ).execute_intent("PREPARE_FOR_SLEEP")

    assert len(transport.published) == 6

    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_current_mode() == Mode.RELAX
    assert context.state.sleep.light == PowerState.OFF
    assert context.state.sleep.bed == PreparationState.NORMAL


def test_no_script_bypasses_the_authoritative_execution_path():
    """Audit finding E3.

    execute_workflow() runs actions over a transport without committing any
    workflow-level state. Scripts that called it reported successful
    execution and then printed a stale environment state as if it were
    authoritative. Orchestrator.execute_intent() is the only path allowed
    to represent logical state.
    """

    import ast
    from pathlib import Path

    tests_root = Path(__file__).resolve().parents[1]

    def calls_execute_workflow(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        return any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute_workflow"
            for node in ast.walk(tree)
        )

    offenders = sorted(
        path.relative_to(tests_root).as_posix()
        for path in tests_root.rglob("*.py")
        if calls_execute_workflow(path)
    )

    assert offenders == []


def test_mqtt_ack_timeout_retries_then_leaves_room_and_mode_uncommitted():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    # The first command is never acknowledged on any of its three attempts.
    transport = FakeMQTTTransport(timeout_on={1, 2, 3})

    with pytest.raises(ActionExecutionError):
        with quiet():
            Orchestrator(
                context,
                MQTTDeviceExecutor(transport),
            ).execute_intent("PREPARE_FOR_SLEEP")

    # One logical action, three transport attempts, then permanent failure.
    assert len(transport.published) == 3

    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_current_mode() == Mode.RELAX
