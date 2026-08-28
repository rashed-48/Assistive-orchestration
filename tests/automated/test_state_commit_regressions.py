"""Regression tests for confirmed workflow-level state-commitment bugs.

Audit findings covered here:

  E1  EMERGENCY never reaches Mode.EMERGENCY
  E2  WAKE_UP clears the mode from rooms where nothing happened
  E4  return_target goes stale on room-changing intents
  E6  SHUTDOWN_ENVIRONMENT only transitions outside, shutting nothing down

Each test states intended behaviour. Orchestrator remains the sole authority
for workflow-level state; these tests assert through it, never around it.
"""

from app.orchestration.actions import ActionType
from app.orchestration.state import (
    DoorState,
    Mode,
    PowerState,
    PreparationState,
    Room,
)

from tests.automated.support import (
    action_signature,
    build_context,
    execute,
)


# ==============================================================
# E1 — EMERGENCY MODE
# ==============================================================


def test_emergency_puts_the_environment_into_emergency_mode():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    execute(context, "EMERGENCY")

    assert context.get_current_mode() == Mode.EMERGENCY

    # The emergency workflow does not claim the user moved.
    assert context.get_current_room() == Room.RELAX_ROOM

    # The alarm is still sounding when the workflow completes.
    assert context.get_state().buzzer == PowerState.ON


def test_emergency_mode_is_reachable_from_every_functional_room():
    for room in (
        Room.STUDY_ROOM,
        Room.RELAX_ROOM,
        Room.SLEEP_ROOM,
        Room.MEAL_ROOM,
    ):
        context = build_context(room, Mode.NONE)

        execute(context, "EMERGENCY")

        assert context.get_current_mode() == Mode.EMERGENCY
        assert context.get_current_room() == room


# ==============================================================
# E2 — WAKE_UP OUTSIDE THE SLEEP ROOM
# ==============================================================


def test_wake_up_outside_the_sleep_room_is_a_complete_no_op():
    context = build_context(Room.STUDY_ROOM, Mode.STUDY)

    executor, results = execute(context, "WAKE_UP")

    # No physical action may be generated or executed.
    assert executor.actions == []
    assert results == []

    # A workflow that did nothing must not mutate logical state.
    assert context.get_current_mode() == Mode.STUDY
    assert context.get_current_room() == Room.STUDY_ROOM


def test_wake_up_in_the_sleep_room_resets_the_bed_and_clears_sleep_mode():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)
    context.state.sleep.bed = PreparationState.READY

    executor, _ = execute(context, "WAKE_UP")

    assert action_signature(executor.actions) == [
        (ActionType.RESET_BED, "sleep_bed"),
    ]

    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.NONE
    assert context.state.sleep.bed == PreparationState.NORMAL


# ==============================================================
# E4 — return_target TRACKS THE PREVIOUS FUNCTIONAL ROOM
# ==============================================================


def test_return_target_records_previous_functional_room_study_to_relax():
    context = build_context(Room.STUDY_ROOM, Mode.STUDY)

    execute(context, "RELAX_MODE")

    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_return_target() == Room.STUDY_ROOM


def test_return_target_records_previous_functional_room_relax_to_sleep():
    # A stale target from an earlier workflow must be replaced, not kept.
    context = build_context(
        Room.RELAX_ROOM,
        Mode.RELAX,
        return_target=Room.STUDY_ROOM,
    )

    execute(context, "PREPARE_FOR_SLEEP")

    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_return_target() == Room.RELAX_ROOM


def test_return_target_tracks_a_chain_of_functional_room_moves():
    context = build_context(Room.STUDY_ROOM, Mode.STUDY)

    execute(context, "RELAX_MODE")
    assert (
        context.get_current_room(),
        context.get_return_target(),
    ) == (Room.RELAX_ROOM, Room.STUDY_ROOM)

    execute(context, "PREPARE_FOR_SLEEP")
    assert (
        context.get_current_room(),
        context.get_return_target(),
    ) == (Room.SLEEP_ROOM, Room.RELAX_ROOM)

    execute(context, "PREPARE_FOR_MEAL")
    assert (
        context.get_current_room(),
        context.get_return_target(),
    ) == (Room.MEAL_ROOM, Room.SLEEP_ROOM)


def test_return_target_is_not_self_referential_when_the_room_does_not_change():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)

    execute(context, "PREPARE_FOR_SLEEP")

    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_return_target() is None


def test_entering_from_outside_leaves_return_target_untouched():
    # OUTSIDE is not a returnable location. This mirrors the guard the
    # existing LEAVE_ROOM/SHUTDOWN branches already establish.
    context = build_context(Room.OUTSIDE, Mode.NONE)

    execute(context, "STUDY_MODE")

    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_return_target() is None


def test_medication_from_another_room_records_that_room_as_the_return_target():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    execute(context, "MEDICATION")

    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_return_target() == Room.RELAX_ROOM


# ==============================================================
# E6 — SHUTDOWN_ENVIRONMENT PERFORMS SHUTDOWN SEMANTICS
# ==============================================================


def fully_active_context(room, mode):
    context = build_context(room, mode)

    state = context.get_state()

    state.study.light = PowerState.ON
    state.study.table = PreparationState.READY

    state.relax.light = PowerState.ON
    state.relax.tv = PowerState.ON

    state.sleep.light = PowerState.ON
    state.sleep.bed = PreparationState.READY

    state.meal.light = PowerState.ON
    state.meal.table = PreparationState.READY

    return context


def test_shutdown_environment_deactivates_every_room():
    context = fully_active_context(Room.MEAL_ROOM, Mode.MEAL)

    execute(context, "SHUTDOWN_ENVIRONMENT")

    state = context.get_state()

    # Every light off, including the drawing-room corridor light.
    assert state.study.light == PowerState.OFF
    assert state.relax.light == PowerState.OFF
    assert state.sleep.light == PowerState.OFF
    assert state.meal.light == PowerState.OFF
    assert state.drawing_light == PowerState.OFF

    # Every appliance off.
    assert state.relax.tv == PowerState.OFF

    # Every prepared surface returned to its resting state.
    assert state.study.table == PreparationState.NORMAL
    assert state.meal.table == PreparationState.NORMAL
    assert state.sleep.bed == PreparationState.NORMAL

    # The house is closed up behind the user.
    assert state.study.door == DoorState.CLOSED
    assert state.relax.door == DoorState.CLOSED
    assert state.sleep.door == DoorState.CLOSED
    assert state.meal.door == DoorState.CLOSED
    assert state.exit_door == DoorState.CLOSED

    assert context.get_current_room() == Room.OUTSIDE
    assert context.get_current_mode() == Mode.NONE
    assert context.get_return_target() == Room.MEAL_ROOM


def test_shutdown_environment_works_from_every_functional_room():
    for room in (
        Room.STUDY_ROOM,
        Room.RELAX_ROOM,
        Room.SLEEP_ROOM,
        Room.MEAL_ROOM,
    ):
        context = fully_active_context(room, Mode.NONE)

        execute(context, "SHUTDOWN_ENVIRONMENT")

        state = context.get_state()

        assert state.study.light == PowerState.OFF, room
        assert state.relax.light == PowerState.OFF, room
        assert state.sleep.light == PowerState.OFF, room
        assert state.meal.light == PowerState.OFF, room
        assert state.relax.tv == PowerState.OFF, room
        assert state.study.table == PreparationState.NORMAL, room
        assert state.meal.table == PreparationState.NORMAL, room
        assert state.sleep.bed == PreparationState.NORMAL, room
        assert state.drawing_light == PowerState.OFF, room

        assert context.get_current_room() == Room.OUTSIDE, room


def test_leave_room_remains_a_departure_and_not_a_shutdown():
    # LEAVE_ROOM and SHUTDOWN_ENVIRONMENT must be distinguishable: leaving
    # does not deactivate rooms the user was not in.
    context = fully_active_context(Room.MEAL_ROOM, Mode.MEAL)

    execute(context, "LEAVE_ROOM")

    state = context.get_state()

    assert context.get_current_room() == Room.OUTSIDE
    assert context.get_return_target() == Room.MEAL_ROOM

    # The room the user left is closed down by the transition itself.
    assert state.meal.light == PowerState.OFF

    # Untouched rooms stay exactly as they were.
    assert state.study.light == PowerState.ON
    assert state.study.table == PreparationState.READY
    assert state.relax.tv == PowerState.ON
    assert state.sleep.bed == PreparationState.READY
