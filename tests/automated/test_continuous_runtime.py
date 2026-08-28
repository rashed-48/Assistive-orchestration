"""The continuous runtime: state survives from one command to the next.

Before Phase 9 the only console path (tests/test_voice_orchestration.py)
built a fresh ContextManager, ran one command, and exited. Every command
therefore started from OUTSIDE, so "I want to sleep" twice in a row
walked the user through the front door twice.

These tests drive ConsoleAssistant with synthetic recognition results
and an injected confirmation, so no microphone, model or broker is
needed. The dependency reasoning under test belongs to the Orchestrator
and WorkflowEngine; what is verified here is that the driver keeps
handing them the state the previous command committed.
"""

import pytest

from app.console import ConsoleAssistant
from app.orchestration.state import (
    DoorState,
    LocationStatus,
    Mode,
    PowerState,
    PreparationState,
    Room,
)
from app.runtime import ApplicationRuntime

from tests.automated.support import quiet


class RecordingExecutor:
    """Stands in for MQTTDeviceExecutor. Records and acknowledges."""

    def __init__(self, fail_devices=()):
        self.actions = []
        self.fail_devices = set(fail_devices)

    def execute(self, action):
        self.actions.append(action)

        return {
            "status": (
                "error" if action.device_id in self.fail_devices else "success"
            ),
            "device": action.device_id,
            "action": action.action_type.value,
        }

    def since(self, mark):
        return [
            (a.action_type.value, a.device_id) for a in self.actions[mark:]
        ]


class CountingMQTT:
    """Counts connect/disconnect so the lifecycle can be asserted."""

    def __init__(self):
        self.connects = 0
        self.disconnects = 0

    def connect(self):
        self.connects += 1

    def disconnect(self):
        self.disconnects += 1


def predicted(intent):
    return {"decision": "PREDICTED", "intent": intent, "similarity_score": 0.9}


UNKNOWN = {"decision": "UNKNOWN", "intent": None, "similarity_score": 0.2}


def build(fail_devices=(), confirm=True, mqtt_client=None):
    executor = RecordingExecutor(fail_devices=fail_devices)

    runtime = ApplicationRuntime(
        device_executor=executor,
        mqtt_client=mqtt_client,
    )

    assistant = ConsoleAssistant(
        runtime=runtime,
        controller=object(),          # never touched: no speech in these tests
        confirm=lambda result: confirm,
    )

    return assistant, runtime, executor


def send(assistant, intent):
    with quiet():
        return assistant.handle_result(predicted(intent))


# ==============================================================
# TEST 1 - STATE PERSISTS BETWEEN COMMANDS
# ==============================================================


def test_state_persists_from_one_command_to_the_next():
    assistant, runtime, executor = build()

    assert runtime.context.get_current_room() == Room.OUTSIDE
    assert runtime.context.get_current_mode() == Mode.NONE

    first = send(assistant, "PREPARE_FOR_SLEEP")

    assert first["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.SLEEP

    mark = len(executor.actions)

    second = send(assistant, "WAKE_UP")

    assert second["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.NONE
    assert runtime.context.get_state().sleep.bed == PreparationState.NORMAL

    # The whole point: waking up did not re-enter the house.
    assert executor.since(mark) == [("RESET_BED", "sleep_bed")]


def test_the_second_command_does_not_repeat_the_entry_workflow():
    assistant, runtime, executor = build()

    send(assistant, "PREPARE_FOR_SLEEP")
    first_command = len(executor.actions)
    assert first_command == 8

    send(assistant, "WAKE_UP")

    mark = len(executor.actions)
    send(assistant, "PREPARE_FOR_SLEEP")
    repeat = executor.since(mark)

    # Already in the sleep room, so only preparation is required.
    assert repeat == [
        ("LIGHT_ON", "sleep_light"),
        ("PREPARE_BED", "sleep_bed"),
    ]

    assert "exit_door" not in [device for _, device in repeat]
    assert "drawing_light" not in [device for _, device in repeat]


# ==============================================================
# TEST 2 - THE NEXT COMMAND PLANS FROM THE CURRENT ROOM
# ==============================================================


def test_a_later_command_plans_from_the_room_the_user_is_in():
    assistant, runtime, executor = build()

    send(assistant, "PREPARE_FOR_SLEEP")
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM

    mark = len(executor.actions)
    send(assistant, "RELAX_MODE")
    plan = executor.since(mark)

    # It left the sleep room rather than the front door.
    assert ("LIGHT_OFF", "sleep_light") in plan
    assert ("OPEN_DOOR", "sleep_door") in plan
    assert ("OPEN_DOOR", "relax_door") in plan
    assert "exit_door" not in [device for _, device in plan]

    assert runtime.context.get_current_room() == Room.RELAX_ROOM
    assert runtime.context.get_return_target() == Room.SLEEP_ROOM


# ==============================================================
# TEST 3 - A MULTI-COMMAND SESSION
# ==============================================================


def test_a_whole_session_chains_state_between_commands():
    assistant, runtime, executor = build()

    journey = []
    for intent in [
        "PREPARE_FOR_SLEEP",
        "WAKE_UP",
        "RELAX_MODE",
        "STUDY_MODE",
    ]:
        mark = len(executor.actions)
        outcome = send(assistant, intent)

        assert outcome["outcome"] == "executed", intent

        journey.append(
            (
                intent,
                runtime.context.get_current_room(),
                runtime.context.get_current_mode(),
                len(executor.actions) - mark,
            )
        )

    assert journey == [
        ("PREPARE_FOR_SLEEP", Room.SLEEP_ROOM, Mode.SLEEP, 8),
        ("WAKE_UP", Room.SLEEP_ROOM, Mode.NONE, 1),
        ("RELAX_MODE", Room.RELAX_ROOM, Mode.RELAX, 9),
        ("STUDY_MODE", Room.STUDY_ROOM, Mode.STUDY, 10),
    ]

    # Only the first command used the front door.
    entries = [a for a in executor.actions if a.device_id == "exit_door"]
    assert len(entries) == 2  # open + close, once

    assert assistant.commands_handled == 4


# ==============================================================
# TEST 4 - AN UNRECOGNISED COMMAND CHANGES NOTHING
# ==============================================================


def test_an_unrecognised_command_does_not_reset_the_world():
    assistant, runtime, executor = build()

    send(assistant, "PREPARE_FOR_SLEEP")
    before = runtime.state_snapshot()["environment"]
    mark = len(executor.actions)

    with quiet():
        outcome = assistant.handle_result(UNKNOWN)

    assert outcome["outcome"] == "unrecognised"
    assert outcome["intent"] is None

    assert executor.actions[mark:] == []
    assert runtime.state_snapshot()["environment"] == before
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM


# ==============================================================
# TEST 5 - DECLINING CONFIRMATION CHANGES NOTHING
# ==============================================================


def test_declining_a_command_does_not_reset_the_world():
    assistant, runtime, executor = build(confirm=False)

    # Nothing runs while confirmation is refused.
    outcome = send(assistant, "PREPARE_FOR_SLEEP")

    assert outcome["outcome"] == "declined"
    assert executor.actions == []
    assert runtime.context.get_current_room() == Room.OUTSIDE

    # Accepting afterwards works normally, from the same world.
    assistant._confirm = lambda result: True
    assert send(assistant, "PREPARE_FOR_SLEEP")["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM


# ==============================================================
# TEST 6 - A FAILED WORKFLOW DOES NOT MOVE THE USER
# ==============================================================


def test_a_failed_workflow_leaves_the_state_uncommitted_and_the_loop_alive():
    assistant, runtime, executor = build(fail_devices={"sleep_door"})

    outcome = send(assistant, "PREPARE_FOR_SLEEP")

    assert outcome["outcome"] == "failed"
    assert outcome["error"]

    # Orchestrator's commit rules are untouched: no room or mode move.
    assert runtime.context.get_current_room() == Room.OUTSIDE
    assert runtime.context.get_current_mode() == Mode.NONE
    assert runtime.context.get_state().sleep.door == DoorState.CLOSED

    # The front door had already opened before the sleep door failed, so
    # the person may be anywhere along the route. The system says so
    # instead of guessing, and refuses to plan movement from a guess.
    assert runtime.context.get_location_status() == LocationStatus.UNKNOWN

    assistant.runtime.device_executor.fail_devices = set()
    assert send(assistant, "PREPARE_FOR_SLEEP")["outcome"] == "location_unknown"

    # Once a human says where they are, the session carries on normally.
    runtime.context.confirm_location(Room.OUTSIDE)
    assert send(assistant, "PREPARE_FOR_SLEEP")["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_location_status() == LocationStatus.KNOWN


def test_an_unsupported_intent_is_reported_without_ending_the_session():
    assistant, runtime, executor = build()

    outcome = send(assistant, "MAKE_COFFEE")

    assert outcome["outcome"] == "unsupported"
    assert executor.actions == []

    assert send(assistant, "PREPARE_FOR_SLEEP")["outcome"] == "executed"


# ==============================================================
# TEST 7 - EMERGENCY STAYS LATCHED ACROSS COMMANDS
# ==============================================================


def test_emergency_latches_blocks_and_then_clears_within_one_session():
    assistant, runtime, executor = build()

    send(assistant, "PREPARE_FOR_SLEEP")
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM

    assert send(assistant, "EMERGENCY")["outcome"] == "executed"
    assert runtime.emergency_active()
    assert runtime.context.get_state().buzzer == PowerState.ON
    assert runtime.context.get_state().exit_door == DoorState.OPEN

    # A normal command is refused, and the runtime keeps going.
    mark = len(executor.actions)
    blocked = send(assistant, "RELAX_MODE")

    assert blocked["outcome"] == "blocked"
    assert executor.actions[mark:] == []
    assert runtime.emergency_active()
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM

    # The clear is still available in the same session.
    assert send(assistant, "EMERGENCY_CLEAR")["outcome"] == "executed"
    assert not runtime.emergency_active()
    assert runtime.context.get_current_mode() == Mode.NONE
    assert runtime.context.get_state().buzzer == PowerState.OFF

    # Normal operation resumes from the state that survived it all.
    resumed = send(assistant, "RELAX_MODE")
    assert resumed["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.RELAX_ROOM


def test_a_blocked_command_is_never_offered_for_confirmation():
    asked = []

    executor = RecordingExecutor()
    runtime = ApplicationRuntime(device_executor=executor)
    assistant = ConsoleAssistant(
        runtime=runtime,
        controller=object(),
        confirm=lambda result: asked.append(result["intent"]) or True,
    )

    send(assistant, "EMERGENCY")
    asked.clear()

    send(assistant, "PREPARE_FOR_SLEEP")

    # The user is told it is blocked rather than asked to confirm
    # something the environment will refuse.
    assert asked == []


# ==============================================================
# TEST 8 - THE SESSION ENDS CLEANLY
# ==============================================================


@pytest.mark.parametrize("word", ["q", "quit", "exit", "STOP", " Quit "])
def test_the_session_ends_on_an_exit_word(word):
    mqtt = CountingMQTT()
    assistant, runtime, _ = build(mqtt_client=mqtt)
    runtime.connect()

    assistant._prompt = lambda _: word

    with quiet():
        assistant.run()

    assert mqtt.disconnects == 1


def test_the_session_ends_on_end_of_input():
    mqtt = CountingMQTT()
    assistant, runtime, _ = build(mqtt_client=mqtt)
    runtime.connect()

    def stdin_closed(_):
        raise EOFError

    assistant._prompt = stdin_closed

    with quiet():
        assistant.run()

    assert mqtt.disconnects == 1


def test_mqtt_connects_once_and_disconnects_once_per_session():
    mqtt = CountingMQTT()
    assistant, runtime, _ = build(mqtt_client=mqtt)

    runtime.connect()
    runtime.connect()          # a second call must be a no-op

    lines = iter(["", "", "q"])
    assistant._prompt = lambda _: next(lines)
    assistant.run_once = lambda: send(assistant, "PREPARE_FOR_SLEEP")

    with quiet():
        assistant.run()

    assert mqtt.connects == 1
    assert mqtt.disconnects == 1

    # Two commands were served by one connection.
    assert assistant.commands_handled == 2
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM


def test_a_command_that_raises_does_not_end_the_session():
    mqtt = CountingMQTT()
    assistant, runtime, _ = build(mqtt_client=mqtt)
    runtime.connect()

    lines = iter(["", "q"])
    assistant._prompt = lambda _: next(lines)

    def explode():
        raise RuntimeError("microphone fell over")

    assistant.run_once = explode

    with quiet():
        assistant.run()

    # The loop absorbed it and shut down normally afterwards.
    assert mqtt.disconnects == 1


# ==============================================================
# SHUTDOWN_ENVIRONMENT IS A WORKFLOW, NOT A PROCESS EXIT
# ==============================================================


def test_shutdown_environment_powers_the_house_down_without_ending_the_session():
    assistant, runtime, executor = build()

    send(assistant, "PREPARE_FOR_SLEEP")

    outcome = send(assistant, "SHUTDOWN_ENVIRONMENT")

    assert outcome["outcome"] == "executed"

    state = runtime.context.get_state()
    assert runtime.context.get_current_room() == Room.OUTSIDE
    assert runtime.context.get_current_mode() == Mode.NONE
    assert state.sleep.light == PowerState.OFF
    assert state.study.light == PowerState.OFF

    # The assistant is still listening, and still holds the same world.
    assert send(assistant, "STUDY_MODE")["outcome"] == "executed"
    assert runtime.context.get_current_room() == Room.STUDY_ROOM
