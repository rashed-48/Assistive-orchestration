"""Emergency lifecycle: latched entry, blocking, and explicit clear.

Approved Phase 6 design:

    NORMAL --EMERGENCY--> EMERGENCY --EMERGENCY_CLEAR--> NORMAL

Emergency is latched. There is no timer and no automatic clearing. Entry
opens the escape route and leaves it open; only a confirmed
EMERGENCY_CLEAR closes it again.

Also pinned here is F5: logical state changes only on an accepted,
correlated, successful acknowledgement.
"""

import pytest

from app.orchestration.actions import ActionType
from app.orchestration.orchestrator import (
    ActionNotAcknowledged,
    EmergencyActive,
    Orchestrator,
)
from app.orchestration.state import (
    DoorState,
    Mode,
    PowerState,
    PreparationState,
    Room,
)
from app.orchestration.workflow_engine import WorkflowEngine

from tests.automated.support import (
    action_signature,
    build_context,
    execute,
    quiet,
)


NORMAL_INTENTS = [
    "PREPARE_FOR_SLEEP",
    "STUDY_MODE",
    "RELAX_MODE",
    "PREPARE_FOR_MEAL",
    "WAKE_UP",
    "LEAVE_ROOM",
    "RETURN_TO_ROOM",
    "SHUTDOWN_ENVIRONMENT",
    "MEDICATION",
]

ALL_DOORS = ["exit_door", "study_door", "relax_door", "sleep_door", "meal_door"]


class ScriptedExecutor:
    """Acknowledges every action, except the devices told to fail."""

    def __init__(self, fail_devices=(), raise_devices=()):
        self.actions = []
        self.fail_devices = set(fail_devices)
        self.raise_devices = set(raise_devices)

    def execute(self, action):
        self.actions.append(action)

        if action.device_id in self.raise_devices:
            raise RuntimeError(f"transport lost for {action.device_id}")

        return {
            "status": (
                "error"
                if action.device_id in self.fail_devices
                else "success"
            ),
            "device": action.device_id,
            "action": action.action_type.value,
        }


def run(context, intent, executor=None):
    executor = executor or ScriptedExecutor()
    with quiet():
        try:
            results = Orchestrator(context, executor).execute_intent(intent)
            error = None
        except Exception as raised:
            results = []
            error = raised
    return executor, results, error


def emergency_context(room=Room.RELAX_ROOM, mode=Mode.RELAX):
    context = build_context(room, mode)
    executor, _, error = run(context, "EMERGENCY")
    assert error is None
    assert context.get_current_mode() == Mode.EMERGENCY
    return context, executor


# ==============================================================
# TEST 1 - EMERGENCY ENTRY
# ==============================================================


def test_emergency_entry_latches_the_mode():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    executor, results, error = run(context, "EMERGENCY")

    assert error is None
    assert context.get_current_mode() == Mode.EMERGENCY
    assert executor.actions


@pytest.mark.parametrize(
    "room",
    [Room.OUTSIDE, Room.DRAWING_ROOM, Room.STUDY_ROOM, Room.RELAX_ROOM,
     Room.SLEEP_ROOM, Room.MEAL_ROOM],
    ids=lambda r: r.value,
)
def test_emergency_can_be_entered_from_anywhere(room):
    context = build_context(room, Mode.NONE)

    run(context, "EMERGENCY")

    assert context.get_current_mode() == Mode.EMERGENCY

    # Emergency makes no claim about where the person is.
    assert context.get_current_room() == room


def test_emergency_does_not_disturb_location_bookkeeping():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX, Room.STUDY_ROOM)

    run(context, "EMERGENCY")

    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_return_target() == Room.STUDY_ROOM


# ==============================================================
# TEST 2 - BUZZER
# ==============================================================


def test_entry_sounds_the_buzzer_and_records_it_after_the_ack():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    executor, _, _ = run(context, "EMERGENCY")

    assert (ActionType.BUZZER_ON, "buzzer") in action_signature(executor.actions)
    assert context.get_state().buzzer == PowerState.ON


def test_a_failed_buzzer_command_does_not_claim_the_alarm_is_sounding():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    _, _, error = run(
        context, "EMERGENCY", ScriptedExecutor(fail_devices={"buzzer"})
    )

    assert context.get_state().buzzer == PowerState.OFF

    # But the emergency is still latched.
    assert context.get_current_mode() == Mode.EMERGENCY


# ==============================================================
# TEST 3 - EXIT DOOR
# ==============================================================


def test_entry_opens_the_exit_door():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)

    executor, _, _ = run(context, "EMERGENCY")

    assert (ActionType.OPEN_DOOR, "exit_door") in action_signature(executor.actions)
    assert context.get_state().exit_door == DoorState.OPEN


def test_entry_opens_every_internal_door():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)

    run(context, "EMERGENCY")

    state = context.get_state()
    assert state.study.door == DoorState.OPEN
    assert state.relax.door == DoorState.OPEN
    assert state.sleep.door == DoorState.OPEN
    assert state.meal.door == DoorState.OPEN


# ==============================================================
# TEST 4 - NO DOOR CLOSING ON ENTRY  (critical)
# ==============================================================


def test_entry_never_closes_an_escape_door():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    plan = action_signature(WorkflowEngine(context).create_emergency_workflow())

    assert not [
        entry for entry in plan if entry[0] == ActionType.CLOSE_DOOR
    ], plan


def test_the_escape_route_is_still_open_when_entry_finishes():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    run(context, "EMERGENCY")

    state = context.get_state()
    assert state.exit_door == DoorState.OPEN
    assert state.study.door == DoorState.OPEN
    assert state.relax.door == DoorState.OPEN
    assert state.sleep.door == DoorState.OPEN
    assert state.meal.door == DoorState.OPEN


def test_entry_does_not_touch_the_corridor_light():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    context.set_drawing_light(PowerState.OFF)

    executor, _, _ = run(context, "EMERGENCY")

    devices = [action.device_id for action in executor.actions]
    assert "drawing_light" not in devices
    assert context.get_state().drawing_light == PowerState.OFF


# ==============================================================
# TEST 5 - NORMAL COMMANDS ARE BLOCKED
# ==============================================================


@pytest.mark.parametrize("intent", NORMAL_INTENTS)
def test_normal_commands_are_rejected_during_emergency(intent):
    context, _ = emergency_context()
    context.set_return_target(Room.STUDY_ROOM)

    before_room = context.get_current_room()
    before_buzzer = context.get_state().buzzer

    executor, _, error = run(context, intent)

    assert isinstance(error, EmergencyActive), (intent, error)

    # Nothing was planned, nothing was sent.
    assert executor.actions == []

    # The latch and the alarm survive the attempt.
    assert context.get_current_mode() == Mode.EMERGENCY
    assert context.get_current_room() == before_room
    assert context.get_state().buzzer == before_buzzer


def test_a_blocked_command_names_the_intent_it_refused():
    context, _ = emergency_context()

    _, _, error = run(context, "PREPARE_FOR_SLEEP")

    assert "PREPARE_FOR_SLEEP" in str(error)


def test_normal_commands_work_again_once_the_emergency_is_cleared():
    context, _ = emergency_context()

    run(context, "EMERGENCY_CLEAR")
    assert context.get_current_mode() == Mode.NONE

    executor, _, error = run(context, "PREPARE_FOR_SLEEP")

    assert error is None
    assert executor.actions
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.SLEEP


# ==============================================================
# TEST 6 - REPEATED EMERGENCY
# ==============================================================


def test_repeating_emergency_after_a_clean_entry_does_nothing_physical():
    context, first = emergency_context()

    second, _, error = run(context, "EMERGENCY")

    assert error is None

    # Everything it would ask for is already true.
    assert second.actions == []

    assert context.get_current_mode() == Mode.EMERGENCY
    assert context.get_state().buzzer == PowerState.ON
    assert context.get_state().exit_door == DoorState.OPEN


def test_repeating_emergency_retries_only_what_failed():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    run(context, "EMERGENCY", ScriptedExecutor(fail_devices={"buzzer"}))
    assert context.get_state().buzzer == PowerState.OFF

    # The retry asks for the buzzer again, and nothing else.
    retry, _, _ = run(context, "EMERGENCY")

    assert action_signature(retry.actions) == [(ActionType.BUZZER_ON, "buzzer")]
    assert context.get_state().buzzer == PowerState.ON


# ==============================================================
# TEST 7 - EMERGENCY CLEAR
# ==============================================================


def test_clear_silences_the_alarm_closes_up_and_returns_to_normal():
    context, _ = emergency_context()

    executor, _, error = run(context, "EMERGENCY_CLEAR")

    assert error is None

    plan = action_signature(executor.actions)
    assert (ActionType.BUZZER_OFF, "buzzer") in plan
    for door in ALL_DOORS:
        assert (ActionType.CLOSE_DOOR, door) in plan, door

    state = context.get_state()
    assert state.buzzer == PowerState.OFF
    assert state.exit_door == DoorState.CLOSED
    assert state.study.door == DoorState.CLOSED
    assert state.relax.door == DoorState.CLOSED
    assert state.sleep.door == DoorState.CLOSED
    assert state.meal.door == DoorState.CLOSED

    assert context.get_current_mode() == Mode.NONE


def test_clear_does_not_pretend_the_person_went_home():
    context, _ = emergency_context(room=Room.SLEEP_ROOM, mode=Mode.SLEEP)
    context.set_return_target(Room.STUDY_ROOM)

    run(context, "EMERGENCY_CLEAR")

    # Location is untouched: the system cannot know where they are.
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_return_target() == Room.STUDY_ROOM

    # The previous mode is deliberately not restored.
    assert context.get_current_mode() == Mode.NONE


def test_clear_is_rejected_when_there_is_no_emergency():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    executor, _, error = run(context, "EMERGENCY_CLEAR")

    assert error is not None
    assert executor.actions == []
    assert context.get_current_mode() == Mode.RELAX


# ==============================================================
# TEST 8 - CLEAR MUST NOT REQUIRE OUTSIDE
# ==============================================================


@pytest.mark.parametrize(
    "room",
    [Room.OUTSIDE, Room.DRAWING_ROOM, Room.STUDY_ROOM, Room.RELAX_ROOM,
     Room.SLEEP_ROOM, Room.MEAL_ROOM],
    ids=lambda r: r.value,
)
def test_clear_is_allowed_from_any_recorded_location(room):
    # current_room is unreliable after an evacuation, so it must never
    # gate recovery.
    context, _ = emergency_context(room=room, mode=Mode.NONE)

    _, _, error = run(context, "EMERGENCY_CLEAR")

    assert error is None
    assert context.get_current_mode() == Mode.NONE
    assert context.get_current_room() == room


# ==============================================================
# TEST 9 - CLEAR FAILURE
# ==============================================================


def test_a_failed_clear_stays_in_emergency():
    context, _ = emergency_context()

    executor, results, error = run(
        context, "EMERGENCY_CLEAR", ScriptedExecutor(fail_devices={"exit_door"})
    )

    # The latch holds: recovery was not completed.
    assert context.get_current_mode() == Mode.EMERGENCY

    # The door that failed is still recorded as open.
    assert context.get_state().exit_door == DoorState.OPEN

    # The rest of the clear still happened.
    assert context.get_state().buzzer == PowerState.OFF
    assert context.get_state().sleep.door == DoorState.CLOSED

    assert any(result.get("status") != "success" for result in results)


def test_a_failed_clear_can_be_retried():
    context, _ = emergency_context()

    run(context, "EMERGENCY_CLEAR", ScriptedExecutor(fail_devices={"exit_door"}))
    assert context.get_current_mode() == Mode.EMERGENCY

    retry, _, _ = run(context, "EMERGENCY_CLEAR")

    # Only the outstanding work is retried.
    assert action_signature(retry.actions) == [
        (ActionType.CLOSE_DOOR, "exit_door")
    ]
    assert context.get_state().exit_door == DoorState.CLOSED
    assert context.get_current_mode() == Mode.NONE


def test_a_lost_transport_during_clear_keeps_the_latch():
    context, _ = emergency_context()

    _, results, error = run(
        context, "EMERGENCY_CLEAR", ScriptedExecutor(raise_devices={"buzzer"})
    )

    assert context.get_current_mode() == Mode.EMERGENCY
    assert context.get_state().buzzer == PowerState.ON
    assert any(result.get("status") != "success" for result in results)


# ==============================================================
# TEST 10 - ENTRY FAILURE
# ==============================================================


def test_a_failed_entry_action_does_not_abandon_the_rest():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    executor, results, error = run(
        context, "EMERGENCY", ScriptedExecutor(fail_devices={"exit_door"})
    )

    # Best effort: every action was still attempted.
    assert len(executor.actions) == 6

    # The alarm and the internal doors still worked.
    assert context.get_state().buzzer == PowerState.ON
    assert context.get_state().sleep.door == DoorState.OPEN

    # The one that failed is not recorded as done.
    assert context.get_state().exit_door == DoorState.CLOSED

    # The emergency is latched regardless.
    assert context.get_current_mode() == Mode.EMERGENCY

    failed = [r for r in results if r.get("status") != "success"]
    assert len(failed) == 1
    assert failed[0]["device"] == "exit_door"


def test_a_raising_transport_during_entry_still_latches():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    executor, results, error = run(
        context, "EMERGENCY", ScriptedExecutor(raise_devices={"buzzer"})
    )

    assert context.get_current_mode() == Mode.EMERGENCY
    assert context.get_state().buzzer == PowerState.OFF

    # The doors were still attempted after the buzzer blew up.
    assert context.get_state().exit_door == DoorState.OPEN
    assert len(executor.actions) == 6


def test_a_total_transport_failure_still_latches_the_emergency():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    everything = {"buzzer", *ALL_DOORS}
    _, results, error = run(
        context, "EMERGENCY", ScriptedExecutor(raise_devices=everything)
    )

    # Nothing physical worked, but the system knows it is in emergency.
    assert context.get_current_mode() == Mode.EMERGENCY
    assert context.get_state().buzzer == PowerState.OFF
    assert context.get_state().exit_door == DoorState.CLOSED

    assert all(result.get("status") != "success" for result in results)


# ==============================================================
# TESTS 11 & 12 - F5 STATE-COMMIT CORRECTNESS
# ==============================================================


def test_a_failed_acknowledgement_does_not_mutate_state():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)

    executor = ScriptedExecutor(fail_devices={"sleep_light"})

    with quiet():
        with pytest.raises(ActionNotAcknowledged):
            Orchestrator(context, executor).execute_intent("PREPARE_FOR_SLEEP")

    # The light was commanded and refused; the state must not claim it is on.
    assert context.get_state().sleep.light == PowerState.OFF
    assert context.get_current_mode() == Mode.NONE


def test_a_successful_acknowledgement_mutates_state_exactly_once():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)

    executor, results, error = run(context, "PREPARE_FOR_SLEEP")

    assert error is None
    assert all(result["status"] == "success" for result in results)

    assert context.get_state().sleep.light == PowerState.ON
    assert context.get_state().sleep.bed == PreparationState.READY
    assert context.get_current_mode() == Mode.SLEEP


def test_an_acknowledgement_for_a_different_device_is_not_accepted():
    class MisdirectedExecutor:
        def __init__(self):
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            # Correct status, wrong device.
            return {
                "status": "success",
                "device": "meal_light",
                "action": action.action_type.value,
            }

    context = build_context(Room.SLEEP_ROOM, Mode.NONE)

    with quiet():
        with pytest.raises(ActionNotAcknowledged):
            Orchestrator(context, MisdirectedExecutor()).execute_intent(
                "PREPARE_FOR_SLEEP"
            )

    assert context.get_state().sleep.light == PowerState.OFF
    assert context.get_state().meal.light == PowerState.OFF


def test_a_malformed_acknowledgement_is_not_accepted():
    class MalformedExecutor:
        def __init__(self):
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            return "OK"

    context = build_context(Room.SLEEP_ROOM, Mode.NONE)

    with quiet():
        with pytest.raises(ActionNotAcknowledged):
            Orchestrator(context, MalformedExecutor()).execute_intent(
                "PREPARE_FOR_SLEEP"
            )

    assert context.get_state().sleep.light == PowerState.OFF


# ==============================================================
# PLAN SHAPE
# ==============================================================


def test_the_entry_plan_is_state_aware():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    full = action_signature(WorkflowEngine(context).create_emergency_workflow())
    assert len(full) == 6

    # With the alarm already sounding and one door already open, those
    # are not commanded again.
    context.set_buzzer(PowerState.ON)
    context.state.sleep.door = DoorState.OPEN

    reduced = action_signature(
        WorkflowEngine(context).create_emergency_workflow()
    )

    assert (ActionType.BUZZER_ON, "buzzer") not in reduced
    assert (ActionType.OPEN_DOOR, "sleep_door") not in reduced
    assert len(reduced) == 4


def test_the_clear_plan_is_state_aware():
    context, _ = emergency_context()

    full = action_signature(
        WorkflowEngine(context).create_emergency_clear_workflow()
    )
    assert len(full) == 6

    context.set_buzzer(PowerState.OFF)
    context.state.meal.door = DoorState.CLOSED

    reduced = action_signature(
        WorkflowEngine(context).create_emergency_clear_workflow()
    )

    assert (ActionType.BUZZER_OFF, "buzzer") not in reduced
    assert (ActionType.CLOSE_DOOR, "meal_door") not in reduced
    assert len(reduced) == 4


def test_emergency_clear_is_a_supported_workflow():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    orchestrator = Orchestrator(context, ScriptedExecutor())

    assert "EMERGENCY_CLEAR" in orchestrator.workflow_map
    assert "EMERGENCY_CLEAR" in Orchestrator.EMERGENCY_INTENTS
    assert "EMERGENCY" in Orchestrator.EMERGENCY_INTENTS
