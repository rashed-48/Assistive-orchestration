"""Drawing Room transition invariants.

The house topology routes every functional room through the Drawing Room,
which acts as the central transition area:

                     DRAWING_ROOM
                     /    |    \\
                STUDY   RELAX   SLEEP
                          \\
                           MEAL

The invariant this module pins:

    while the Drawing Room is being used to get somewhere, its light is ON
    once the person has arrived in the destination, its light is OFF
    if no Drawing Room traversal happens, its light is never touched

Plans come from WorkflowEngine and TransitionBuilder. Nothing here
reproduces an expected action list by hand: the assertions are about
properties of the plan and the committed state.
"""

import pytest

from app.orchestration.actions import ActionType
from app.orchestration.state import (
    DoorState,
    Mode,
    PowerState,
    PreparationState,
    Room,
)
from app.orchestration.transitions import TransitionBuilder
from app.orchestration.workflow_engine import WorkflowEngine

from tests.automated.support import (
    action_signature,
    build_context,
    execute,
)


FUNCTIONAL_ROOMS = [
    Room.STUDY_ROOM,
    Room.RELAX_ROOM,
    Room.SLEEP_ROOM,
    Room.MEAL_ROOM,
]

ALL_SOURCES = [Room.OUTSIDE, Room.DRAWING_ROOM] + FUNCTIONAL_ROOMS

INTENT_FOR_ROOM = {
    Room.STUDY_ROOM: "STUDY_MODE",
    Room.RELAX_ROOM: "RELAX_MODE",
    Room.SLEEP_ROOM: "PREPARE_FOR_SLEEP",
    Room.MEAL_ROOM: "PREPARE_FOR_MEAL",
}

ROOM_DOORS = TransitionBuilder.ROOM_DOORS

TRANSITIONS = [
    (source, destination)
    for source in ALL_SOURCES
    for destination in FUNCTIONAL_ROOMS
]

TRAVERSALS = [
    (source, destination)
    for source, destination in TRANSITIONS
    if source != destination
]

ids = lambda pairs: [f"{s.value}-to-{d.value}" for s, d in pairs]


def plan_for(source, destination, drawing_light=PowerState.OFF):
    context = build_context(source, Mode.NONE)
    context.set_drawing_light(drawing_light)

    workflow = WorkflowEngine(context)
    builder = {
        Room.STUDY_ROOM: workflow.create_study_workflow,
        Room.RELAX_ROOM: workflow.create_relax_workflow,
        Room.SLEEP_ROOM: workflow.create_sleep_workflow,
        Room.MEAL_ROOM: workflow.create_meal_workflow,
    }[destination]

    return action_signature(builder())


def drawing_actions(plan):
    return [
        action_type
        for action_type, device in plan
        if device == "drawing_light"
    ]


def index_of(plan, action_type, device):
    return plan.index((action_type, device))


# ==============================================================
# EVERY TRANSITION ARRIVES
# ==============================================================


@pytest.mark.parametrize("source,destination", TRANSITIONS, ids=ids(TRANSITIONS))
def test_transition_commits_the_destination_room(source, destination):
    context = build_context(source, Mode.NONE)
    if source == Room.DRAWING_ROOM:
        context.set_drawing_light(PowerState.ON)

    execute(context, INTENT_FOR_ROOM[destination])

    assert context.get_current_room() == destination
    assert context.get_current_room() != source or source == destination

    # The person is in the destination, not the corridor.
    assert context.get_state().drawing_light == PowerState.OFF

    # Every door the plan opened was closed again behind them.
    state = context.get_state()
    assert state.exit_door == DoorState.CLOSED
    for room_door in ("study", "relax", "sleep", "meal"):
        assert getattr(state, room_door).door == DoorState.CLOSED


# ==============================================================
# NO FAKE DETOUR WHEN ALREADY IN THE DESTINATION
# ==============================================================


@pytest.mark.parametrize("room", FUNCTIONAL_ROOMS, ids=[r.value for r in FUNCTIONAL_ROOMS])
def test_no_drawing_room_detour_when_already_in_the_destination(room):
    plan = plan_for(room, room)

    # The Drawing Room is not involved at all.
    assert drawing_actions(plan) == []

    # And no door is opened, because nobody moves.
    assert not [
        action_type
        for action_type, _ in plan
        if action_type in {ActionType.OPEN_DOOR, ActionType.CLOSE_DOOR}
    ], plan


@pytest.mark.parametrize("room", FUNCTIONAL_ROOMS, ids=[r.value for r in FUNCTIONAL_ROOMS])
def test_staying_put_never_switches_off_a_light_it_did_not_switch_on(room):
    context = build_context(room, Mode.NONE)
    context.set_drawing_light(PowerState.ON)

    execute(context, INTENT_FOR_ROOM[room])

    # Nothing traversed the Drawing Room, so its light is left alone.
    assert context.get_state().drawing_light == PowerState.ON


# ==============================================================
# THE LIGHT IS ON WHILE THE CORRIDOR IS IN USE
# ==============================================================


@pytest.mark.parametrize("source,destination", TRAVERSALS, ids=ids(TRAVERSALS))
def test_drawing_light_is_on_for_the_traversal_and_off_on_arrival(source, destination):
    plan = plan_for(source, destination)

    assert drawing_actions(plan) == [ActionType.LIGHT_ON, ActionType.LIGHT_OFF], plan

    lit = index_of(plan, ActionType.LIGHT_ON, "drawing_light")
    entered = index_of(plan, ActionType.OPEN_DOOR, ROOM_DOORS[destination])
    unlit = index_of(plan, ActionType.LIGHT_OFF, "drawing_light")

    # Lit before the destination door opens, dark only after arrival.
    assert lit < entered < unlit, plan


@pytest.mark.parametrize("destination", FUNCTIONAL_ROOMS, ids=[r.value for r in FUNCTIONAL_ROOMS])
def test_leaving_the_drawing_room_does_not_relight_it(destination):
    plan = plan_for(Room.DRAWING_ROOM, destination, drawing_light=PowerState.ON)

    # The person is standing in a lit room; do not command it lit again.
    assert drawing_actions(plan) == [ActionType.LIGHT_OFF], plan


@pytest.mark.parametrize("destination", FUNCTIONAL_ROOMS, ids=[r.value for r in FUNCTIONAL_ROOMS])
def test_leaving_a_dark_drawing_room_lights_it_first(destination):
    plan = plan_for(Room.DRAWING_ROOM, destination, drawing_light=PowerState.OFF)

    assert drawing_actions(plan) == [ActionType.LIGHT_ON, ActionType.LIGHT_OFF], plan


# ==============================================================
# TOPOLOGY: THE ENTRANCE IS ONLY USED FROM OUTSIDE
# ==============================================================


@pytest.mark.parametrize("destination", FUNCTIONAL_ROOMS, ids=[r.value for r in FUNCTIONAL_ROOMS])
def test_entering_from_outside_uses_the_entrance_then_the_corridor(destination):
    plan = plan_for(Room.OUTSIDE, destination)

    devices = [device for _, device in plan]
    assert "exit_door" in devices

    # Entrance first, then the corridor, then the destination door.
    assert index_of(plan, ActionType.OPEN_DOOR, "exit_door") < index_of(
        plan, ActionType.LIGHT_ON, "drawing_light"
    ) < index_of(plan, ActionType.OPEN_DOOR, ROOM_DOORS[destination])


@pytest.mark.parametrize(
    "source,destination",
    [(s, d) for s, d in TRAVERSALS if s in FUNCTIONAL_ROOMS + [Room.DRAWING_ROOM]],
    ids=ids([(s, d) for s, d in TRAVERSALS if s in FUNCTIONAL_ROOMS + [Room.DRAWING_ROOM]]),
)
def test_moving_inside_the_house_never_opens_the_entrance(source, destination):
    plan = plan_for(source, destination)

    assert "exit_door" not in [device for _, device in plan], plan


@pytest.mark.parametrize(
    "source,destination",
    [(s, d) for s, d in TRAVERSALS if s in FUNCTIONAL_ROOMS],
    ids=ids([(s, d) for s, d in TRAVERSALS if s in FUNCTIONAL_ROOMS]),
)
def test_the_source_room_is_shut_down_before_it_is_left(source, destination):
    plan = plan_for(source, destination)

    source_light = TransitionBuilder.ROOM_LIGHTS[source]

    assert (ActionType.LIGHT_OFF, source_light) in plan

    # And the room is left before the corridor is lit.
    assert index_of(plan, ActionType.LIGHT_OFF, source_light) < index_of(
        plan, ActionType.LIGHT_ON, "drawing_light"
    )

    if source == Room.RELAX_ROOM:
        assert (ActionType.TV_OFF, "relax_tv") in plan


# ==============================================================
# THE DRAWING ROOM AS A DESTINATION
# ==============================================================


def test_outside_to_drawing_room_enters_and_stays_lit():
    context = build_context(Room.OUTSIDE, Mode.NONE)

    plan = action_signature(
        TransitionBuilder(context).transition_to(Room.DRAWING_ROOM)
    )

    assert (ActionType.OPEN_DOOR, "exit_door") in plan
    assert (ActionType.LIGHT_ON, "drawing_light") in plan

    # The person stops here, so the corridor light stays on.
    assert (ActionType.LIGHT_OFF, "drawing_light") not in plan


def test_functional_room_to_drawing_room_lights_the_corridor():
    context = build_context(Room.RELAX_ROOM, Mode.RELAX)

    plan = action_signature(
        TransitionBuilder(context).transition_to(Room.DRAWING_ROOM)
    )

    assert (ActionType.LIGHT_OFF, "relax_light") in plan
    assert (ActionType.LIGHT_ON, "drawing_light") in plan
    assert (ActionType.LIGHT_OFF, "drawing_light") not in plan


def test_leaving_the_house_turns_the_corridor_light_off():
    context = build_context(Room.SLEEP_ROOM, Mode.SLEEP)

    execute(context, "LEAVE_ROOM")

    assert context.get_current_room() == Room.OUTSIDE
    assert context.get_state().drawing_light == PowerState.OFF
    assert context.get_state().exit_door == DoorState.CLOSED


# ==============================================================
# MODE SEMANTICS ARE UNCHANGED BY THIS PHASE
# ==============================================================


@pytest.mark.parametrize("source,destination", TRANSITIONS, ids=ids(TRANSITIONS))
def test_mode_follows_the_destination_room(source, destination):
    context = build_context(source, Mode.NONE)
    if source == Room.DRAWING_ROOM:
        context.set_drawing_light(PowerState.ON)

    execute(context, INTENT_FOR_ROOM[destination])

    expected = {
        Room.STUDY_ROOM: Mode.STUDY,
        Room.RELAX_ROOM: Mode.RELAX,
        Room.SLEEP_ROOM: Mode.SLEEP,
        Room.MEAL_ROOM: Mode.MEAL,
    }[destination]

    assert context.get_current_mode() == expected


def test_the_destination_room_is_actually_prepared():
    context = build_context(Room.OUTSIDE, Mode.NONE)

    execute(context, "PREPARE_FOR_SLEEP")

    state = context.get_state()
    assert state.sleep.light == PowerState.ON
    assert state.sleep.bed == PreparationState.READY
