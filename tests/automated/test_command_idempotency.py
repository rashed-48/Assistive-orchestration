"""command_id idempotency across MQTT retries.

Audit finding E5. A retry exists because an acknowledgement did not arrive,
not because the action did not happen. If the node cannot tell a retry from
a fresh command, a lost ACK opens the same door twice.

Two halves are pinned here:

    the executor  keeps one command_id for one logical action, so a retry
                  is recognisable as a retry
    the node      remembers command ids it has already carried out, and
                  re-acknowledges a duplicate instead of re-executing it

The end-to-end version of this, over a real broker, lives in
test_mqtt_end_to_end.py.
"""

import json

import pytest

from app.devices.mqtt_device import ActionExecutionError, MQTTDeviceExecutor
from app.devices.simulated_node import SimulatedESP32
from app.orchestration.actions import Action, ActionType
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.state import Mode, PowerState, PreparationState, Room

from tests.automated.support import (
    FakeMQTTTransport,
    build_context,
    quiet,
)


# ==============================================================
# NODE-SIDE DEDUPLICATION
# ==============================================================


class CapturingNode(SimulatedESP32):
    """A mock node whose MQTT publishing is captured, not sent."""

    def __init__(self, node_id="esp32_b"):
        super().__init__(node_id)
        self.published = []

    def publish_status(self, device, action, status, command_id=None, **extra):
        self.published.append(
            {
                "command_id": command_id,
                "node": self.node_id,
                "device": device,
                "action": action,
                "status": status,
                **extra,
            }
        )


class FakeMessage:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()


def command(device, action, command_id):
    return FakeMessage(
        {
            "device": device,
            "action": action,
            "parameters": {},
            "command_id": command_id,
        }
    )


@pytest.fixture
def node():
    with quiet():
        yield CapturingNode()


def test_a_command_is_carried_out_once_and_acknowledged(node):
    with quiet():
        node.on_message(None, None, command("sleep_light", "LIGHT_ON", "ABC"))

    assert node.executed_count == 1
    assert node.get_device_states()["sleep_light"] == "ON"

    assert len(node.published) == 1
    assert node.published[0]["status"] == "success"
    assert node.published[0]["command_id"] == "ABC"


def test_a_duplicate_command_id_is_acknowledged_but_not_re_executed(node):
    with quiet():
        node.on_message(None, None, command("sleep_door", "OPEN_DOOR", "ABC"))
        node.on_message(None, None, command("sleep_door", "OPEN_DOOR", "ABC"))

    # Received twice.
    assert len(node.published) == 2

    # Physically carried out once.
    assert node.executed_count == 1
    assert node.duplicate_count == 1

    # The retry still gets an answer, so the executor can move on.
    duplicate = node.published[1]
    assert duplicate["status"] == "success"
    assert duplicate["command_id"] == "ABC"
    assert duplicate["duplicate"] is True


def test_a_duplicate_does_not_move_the_hardware_again(node):
    """The dangerous case: a door must not reopen on a retry."""

    with quiet():
        node.on_message(None, None, command("sleep_door", "OPEN_DOOR", "X1"))
        assert node.get_device_states()["sleep_door"] == "OPEN"

        # A different logical command closes it.
        node.on_message(None, None, command("sleep_door", "CLOSE_DOOR", "X2"))
        assert node.get_device_states()["sleep_door"] == "CLOSED"

        # A retry of the first command must not reopen it.
        node.on_message(None, None, command("sleep_door", "OPEN_DOOR", "X1"))

    assert node.get_device_states()["sleep_door"] == "CLOSED"
    assert node.executed_count == 2
    assert node.duplicate_count == 1


def test_distinct_command_ids_are_each_executed(node):
    with quiet():
        node.on_message(None, None, command("sleep_light", "LIGHT_ON", "A"))
        node.on_message(None, None, command("sleep_light", "LIGHT_OFF", "B"))

    assert node.executed_count == 2
    assert node.duplicate_count == 0
    assert node.get_device_states()["sleep_light"] == "OFF"


def test_a_rejected_command_is_not_remembered_as_done(node):
    """A command that failed must stay retryable."""

    with quiet():
        # relax_light belongs to esp32_a, not to this node.
        node.on_message(None, None, command("relax_light", "LIGHT_ON", "ERR"))

    assert node.published[0]["status"] == "error"
    assert node.executed_count == 0

    with quiet():
        node.on_message(None, None, command("sleep_light", "LIGHT_ON", "ERR"))

    # The id was never completed, so this is a fresh command, not a duplicate.
    assert node.duplicate_count == 0
    assert node.executed_count == 1


def test_the_deduplication_memory_is_bounded(node):
    with quiet():
        for index in range(SimulatedESP32.COMMAND_HISTORY_LIMIT + 25):
            node.on_message(
                None,
                None,
                command("sleep_light", "LIGHT_ON", f"id-{index}"),
            )

    assert len(node.processed_commands) <= SimulatedESP32.COMMAND_HISTORY_LIMIT

    # The most recent ids are still recognised as duplicates.
    before = node.executed_count
    with quiet():
        node.on_message(
            None,
            None,
            command(
                "sleep_light",
                "LIGHT_ON",
                f"id-{SimulatedESP32.COMMAND_HISTORY_LIMIT + 24}",
            ),
        )

    assert node.executed_count == before


def test_a_command_without_an_id_is_still_executed(node):
    with quiet():
        node.on_message(
            None,
            None,
            FakeMessage(
                {
                    "device": "sleep_light",
                    "action": "LIGHT_ON",
                    "parameters": {},
                }
            ),
        )

    assert node.executed_count == 1
    assert node.published[0]["status"] == "success"


# ==============================================================
# EXECUTOR-SIDE COMMAND IDENTITY
# ==============================================================


def test_every_retry_of_one_action_reuses_the_same_command_id():
    # The first two attempts get no acknowledgement.
    transport = FakeMQTTTransport(timeout_on={1, 2})

    with quiet():
        MQTTDeviceExecutor(transport).execute(
            Action(ActionType.LIGHT_ON, "sleep_light")
        )

    assert len(transport.published) == 3

    ids = {message["payload"]["command_id"] for message in transport.published}

    # One logical action, one identity - that is what lets a node
    # recognise the retry.
    assert len(ids) == 1


def test_different_actions_get_different_command_ids():
    transport = FakeMQTTTransport()
    executor = MQTTDeviceExecutor(transport)

    with quiet():
        executor.execute(Action(ActionType.LIGHT_ON, "sleep_light"))
        executor.execute(Action(ActionType.LIGHT_OFF, "sleep_light"))

    ids = [message["payload"]["command_id"] for message in transport.published]

    assert len(set(ids)) == 2


def test_a_whole_workflow_uses_one_command_id_per_action():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    transport = FakeMQTTTransport()

    with quiet():
        results = Orchestrator(
            context, MQTTDeviceExecutor(transport)
        ).execute_intent("PREPARE_FOR_SLEEP")

    ids = [message["payload"]["command_id"] for message in transport.published]

    assert len(ids) == len(results)
    assert len(set(ids)) == len(results)


# ==============================================================
# A LOST ACKNOWLEDGEMENT MUST NOT DOUBLE-APPLY STATE
# ==============================================================


class LosingTransport(FakeMQTTTransport):
    """Delivers every command, but swallows the first N acknowledgements.

    This is the lost-ACK case: the hardware acted, the answer never
    arrived, and the executor retries.
    """

    def __init__(self, lose_first=1):
        super().__init__()
        self.lose_first = lose_first
        self.delivered = []

    def wait_for_status(self, command_id, timeout=5):
        status = super().wait_for_status(command_id, timeout=timeout)

        # Record what the hardware would actually have carried out.
        payload = self.published[-1]["payload"]
        if payload["command_id"] not in [
            item["command_id"] for item in self.delivered
        ]:
            self.delivered.append(payload)

        if self.lose_first > 0:
            self.lose_first -= 1
            return None

        return status


def test_a_lost_acknowledgement_applies_the_state_change_once():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)
    transport = LosingTransport(lose_first=1)

    with quiet():
        results = Orchestrator(
            context, MQTTDeviceExecutor(transport)
        ).execute_intent("PREPARE_FOR_SLEEP")

    # The first action was published twice: once lost, once acknowledged.
    assert len(transport.published) > len(results)

    # But it was one logical command throughout.
    assert len(transport.delivered) == len(results)

    # And the workflow completed with state applied exactly once.
    state = context.get_state()
    assert state.sleep.light == PowerState.ON
    assert state.sleep.bed == PreparationState.READY
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.SLEEP


def test_an_exhausted_retry_still_fails_the_workflow():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)
    transport = FakeMQTTTransport(timeout_on={1, 2, 3})

    with pytest.raises(ActionExecutionError):
        with quiet():
            Orchestrator(
                context, MQTTDeviceExecutor(transport)
            ).execute_intent("PREPARE_FOR_SLEEP")

    # Retrying is not the same as succeeding.
    assert context.get_current_mode() == Mode.NONE
    assert context.get_state().sleep.light == PowerState.OFF
