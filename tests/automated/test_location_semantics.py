"""Location certainty: KNOWN, IN_TRANSIT, UNKNOWN.

Phase 10's persistence audit found that `current_room` was the only
answer the state model could give, so it had to answer even when the
system did not know. A snapshot taken nine actions into a ten-action
move asserted the person was still in the room they had left.

The model now separates the reading from its reliability:

    current_room      the last committed location
    location_status   how much that is worth right now

Uncertainty is deliberately NOT a Room member. Room is a dictionary key
in the transition tables and is pattern-matched by if/elif chains with
no fallback branch, so an "UNKNOWN room" would be silently unroutable.
It is a property of the reading, not a place.
"""

import pytest

from app.orchestration.context_manager import ContextManager
from app.orchestration.orchestrator import (
    ActionNotAcknowledged,
    LocationUnknown,
    Orchestrator,
)
from app.orchestration.state import LocationStatus, Mode, Room

from tests.automated.support import build_context, quiet


MOVEMENT_INTENTS = [
    "PREPARE_FOR_SLEEP",
    "STUDY_MODE",
    "RELAX_MODE",
    "PREPARE_FOR_MEAL",
    "MEDICATION",
    "LEAVE_ROOM",
    "SHUTDOWN_ENVIRONMENT",
    "RETURN_TO_ROOM",
    "WAKE_UP",
]


class Executor:
    """Acknowledges everything, or refuses one named device."""

    def __init__(self, fail_device=None):
        self.actions = []
        self.fail_device = fail_device

    def execute(self, action):
        self.actions.append(action)

        return {
            "status": (
                "error" if action.device_id == self.fail_device else "success"
            ),
            "device": action.device_id,
            "action": action.action_type.value,
        }


class TransitWatcher(Executor):
    """Records the location status observed during the workflow."""

    def __init__(self, context, fail_device=None):
        super().__init__(fail_device)
        self.context = context
        self.seen = []

    def execute(self, action):
        self.seen.append(
            (
                self.context.get_location_status(),
                self.context.get_current_room(),
                self.context.get_location_destination(),
            )
        )
        return super().execute(action)


def run(context, intent, executor=None):
    executor = executor or Executor()
    with quiet():
        try:
            Orchestrator(context, executor).execute_intent(intent)
            error = None
        except Exception as raised:
            error = raised
    return executor, error


# ==============================================================
# 1 - THE DEFAULT IS A KNOWN LOCATION
# ==============================================================


def test_a_new_environment_starts_known_and_outside():
    context = ContextManager()

    assert context.get_current_room() == Room.OUTSIDE
    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.location_is_known()
    assert context.get_location_destination() is None
    assert context.get_location_reason() is None


def test_uncertainty_is_not_a_room():
    """Room must keep exactly the six places a person can be."""

    assert {room.value for room in Room} == {
        "OUTSIDE",
        "DRAWING_ROOM",
        "STUDY_ROOM",
        "RELAX_ROOM",
        "SLEEP_ROOM",
        "MEAL_ROOM",
    }

    assert not hasattr(Room, "UNKNOWN")
    assert not hasattr(Room, "IN_TRANSIT")


# ==============================================================
# 2 & 3 - A COMPLETED MOVE COMMITS A KNOWN LOCATION
# ==============================================================


def test_a_completed_move_from_outside_ends_known():
    context = build_context(Room.OUTSIDE, Mode.NONE)

    _, error = run(context, "PREPARE_FOR_SLEEP")

    assert error is None
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.get_location_destination() is None


def test_a_completed_move_between_rooms_ends_known():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)

    _, error = run(context, "RELAX_MODE")

    assert error is None
    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_location_status() == LocationStatus.KNOWN


@pytest.mark.parametrize("intent", MOVEMENT_INTENTS)
def test_every_intent_leaves_the_location_known_when_it_succeeds(intent):
    context = build_context(Room.RELAX_ROOM, Mode.RELAX, Room.STUDY_ROOM)

    _, error = run(context, intent)

    assert error is None, intent
    assert context.get_location_status() == LocationStatus.KNOWN


# ==============================================================
# 4 - STAYING PUT IS NOT A TRANSIT
# ==============================================================


def test_a_same_room_command_never_enters_transit():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)
    watcher = TransitWatcher(context)

    run(context, "PREPARE_FOR_SLEEP", watcher)

    assert watcher.actions, "the workflow should still do something"
    assert {status for status, _, _ in watcher.seen} == {LocationStatus.KNOWN}
    assert context.get_location_status() == LocationStatus.KNOWN


def test_wake_up_does_not_enter_transit():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)
    watcher = TransitWatcher(context)

    run(context, "WAKE_UP", watcher)

    assert {status for status, _, _ in watcher.seen} == {LocationStatus.KNOWN}


# ==============================================================
# 5 - THE DESTINATION IS NOT CLAIMED EARLY
# ==============================================================


def test_the_destination_is_not_committed_during_the_move():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    watcher = TransitWatcher(context)

    run(context, "PREPARE_FOR_SLEEP", watcher)

    # Throughout the whole journey the reading stayed IN_TRANSIT, the
    # committed room stayed at the source, and the destination was
    # recorded separately.
    assert {status for status, _, _ in watcher.seen} == {
        LocationStatus.IN_TRANSIT
    }
    assert {room for _, room, _ in watcher.seen} == {Room.RELAX_ROOM}
    assert {destination for _, _, destination in watcher.seen} == {
        Room.SLEEP_ROOM
    }

    # Only once every action was acknowledged does it become a fact.
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_location_status() == LocationStatus.KNOWN


def test_transit_records_both_ends_of_the_journey():
    context = build_context(Room.STUDY_ROOM, Mode.STUDY)

    context.begin_transit(Room.MEAL_ROOM, reason="worked example")

    assert context.get_location_status() == LocationStatus.IN_TRANSIT
    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_location_destination() == Room.MEAL_ROOM
    assert context.get_location_reason() == "worked example"


# ==============================================================
# 6 - AN INTERRUPTED MOVE NEVER CLAIMS THE DESTINATION
# ==============================================================


def test_a_move_interrupted_after_a_door_opened_becomes_unknown():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    # Fails at OPEN_DOOR sleep_door, by which point relax_door has
    # already opened and closed: the person may be anywhere.
    _, error = run(context, "PREPARE_FOR_SLEEP", Executor("sleep_door"))

    assert isinstance(error, ActionNotAcknowledged)

    assert context.get_location_status() == LocationStatus.UNKNOWN
    assert context.get_location_destination() is None
    assert "interrupted" in context.get_location_reason()

    # The destination was never claimed, and the mode never moved.
    assert context.get_current_room() != Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.RELAX


def test_a_move_interrupted_before_any_door_opened_stays_known():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    # relax_light is the first action, long before any door moves, so
    # the person cannot have gone anywhere.
    _, error = run(context, "PREPARE_FOR_SLEEP", Executor("relax_light"))

    assert isinstance(error, ActionNotAcknowledged)

    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_current_mode() == Mode.RELAX


def test_an_interrupted_non_movement_workflow_stays_known():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)

    _, error = run(context, "PREPARE_FOR_SLEEP", Executor("sleep_light"))

    assert error is not None
    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.get_current_room() == Room.SLEEP_ROOM


# ==============================================================
# 7 & 8 - UNCERTAINTY IS NOT A PLACE
# ==============================================================


def test_unknown_is_not_treated_as_outside():
    context = build_context(Room.SLEEP_ROOM, Mode.NONE)
    context.mark_location_unknown(reason="worked example")

    # current_room still records where they were last seen; it is the
    # status that withdraws the claim.
    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_room() != Room.OUTSIDE
    assert not context.location_is_known()

    # And nothing plans an entry through the front door on the strength
    # of it.
    executor, error = run(context, "PREPARE_FOR_SLEEP")

    assert isinstance(error, LocationUnknown)
    assert executor.actions == []


def test_in_transit_is_not_treated_as_a_room():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    context.begin_transit(Room.SLEEP_ROOM, reason="worked example")

    executor, error = run(context, "STUDY_MODE")

    assert isinstance(error, LocationUnknown)
    assert error.status == LocationStatus.IN_TRANSIT
    assert executor.actions == []


# ==============================================================
# 9 - COMMANDS THAT NEED A LOCATION ARE REFUSED SAFELY
# ==============================================================


@pytest.mark.parametrize("intent", MOVEMENT_INTENTS)
def test_location_dependent_intents_are_refused_when_the_location_is_unknown(intent):
    context = build_context(Room.RELAX_ROOM, Mode.RELAX, Room.STUDY_ROOM)
    context.mark_location_unknown(reason="worked example")

    before = context.to_dict()
    executor, error = run(context, intent)

    assert isinstance(error, LocationUnknown), intent

    # Refused outright: nothing planned, nothing sent, nothing changed.
    assert executor.actions == []
    assert context.to_dict() == before


def test_the_refusal_names_the_intent_and_the_last_known_room():
    context = build_context(Room.MEAL_ROOM, Mode.MEAL)
    context.mark_location_unknown(reason="worked example")

    _, error = run(context, "STUDY_MODE")

    assert error.intent == "STUDY_MODE"
    assert error.status == LocationStatus.UNKNOWN
    assert error.last_known == Room.MEAL_ROOM
    assert "MEAL_ROOM" in str(error)


def test_confirming_the_location_restores_normal_operation():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    context.mark_location_unknown(reason="worked example")

    context.confirm_location(Room.STUDY_ROOM)

    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_location_reason() is None

    executor, error = run(context, "PREPARE_FOR_SLEEP")

    assert error is None
    assert executor.actions
    assert context.get_current_room() == Room.SLEEP_ROOM


# ==============================================================
# 10 - RETURN_TO_ROOM
# ==============================================================


def test_return_to_room_is_refused_when_the_location_is_unknown():
    context = build_context(Room.OUTSIDE, Mode.NONE, Room.STUDY_ROOM)
    context.mark_location_unknown(reason="worked example")

    executor, error = run(context, "RETURN_TO_ROOM")

    assert isinstance(error, LocationUnknown)
    assert executor.actions == []

    # The bookmark itself is untouched, so it still works afterwards.
    assert context.get_return_target() == Room.STUDY_ROOM

    context.confirm_location(Room.OUTSIDE)
    _, error = run(context, "RETURN_TO_ROOM")

    assert error is None
    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_location_status() == LocationStatus.KNOWN


def test_return_to_room_without_a_target_does_not_start_a_transit():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    _, error = run(context, "RETURN_TO_ROOM")

    assert isinstance(error, ValueError)

    # The workflow refused before anything moved, so the location is
    # still a plain fact.
    assert context.get_location_status() == LocationStatus.KNOWN
    assert context.get_current_room() == Room.RELAX_ROOM


# ==============================================================
# EMERGENCY REMAINS USABLE WITHOUT A LOCATION
# ==============================================================


def test_emergency_works_when_the_location_is_unknown():
    """The one thing that must never depend on knowing where anyone is."""

    context = build_context(Room.SLEEP_ROOM, Mode.NONE)
    context.mark_location_unknown(reason="worked example")

    executor, error = run(context, "EMERGENCY")

    assert error is None
    assert executor.actions
    assert context.get_current_mode() == Mode.EMERGENCY

    # And clearing it is available too.
    _, error = run(context, "EMERGENCY_CLEAR")

    assert error is None
    assert context.get_current_mode() == Mode.NONE


def test_emergency_does_not_change_the_location_reading():
    """Phase 7 deliberately makes no claim about where the person went.

    Emergency still leaves current_room and the status exactly as it
    found them. Whether an evacuation should *withdraw* the location
    claim is a deliberate open question recorded in the Phase 10A
    report, not an accident.
    """

    context = build_context(Room.STUDY_ROOM, Mode.STUDY)

    run(context, "EMERGENCY")

    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_location_status() == LocationStatus.KNOWN


# ==============================================================
# SERIALISATION - WHAT THE PERSISTENCE PHASE WILL SAVE
# ==============================================================


def test_the_location_reading_is_serialised():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)
    context.begin_transit(Room.SLEEP_ROOM, reason="PREPARE_FOR_SLEEP in progress")

    snapshot = context.to_dict()

    assert snapshot["current_room"] == "RELAX_ROOM"
    assert snapshot["location_status"] == "IN_TRANSIT"
    assert snapshot["location_destination"] == "SLEEP_ROOM"
    assert snapshot["location_reason"] == "PREPARE_FOR_SLEEP in progress"


def test_a_known_location_serialises_without_noise():
    snapshot = ContextManager().to_dict()

    assert snapshot["location_status"] == "KNOWN"
    assert snapshot["location_destination"] is None
    assert snapshot["location_reason"] is None
