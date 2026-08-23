import json

from app.devices.json_protocol import JSONProtocol
from app.orchestration.actions import Action, ActionType
from app.orchestration.context_manager import ContextManager
from app.orchestration.state import Mode, PowerState, Room
from app.orchestration.workflow_engine import WorkflowEngine


def action_signature(actions):
    return [
        (action.action_type, action.device_id)
        for action in actions
    ]


def test_context_manager_tracks_core_logical_state():
    context = ContextManager()

    assert context.get_current_room() == Room.OUTSIDE
    assert context.get_return_target() is None
    assert context.get_current_mode() == Mode.NONE

    context.set_current_room(Room.STUDY_ROOM)
    context.set_return_target(Room.RELAX_ROOM)
    context.set_mode(Mode.STUDY)
    context.set_drawing_light(PowerState.ON)

    assert context.get_current_room() == Room.STUDY_ROOM
    assert context.get_return_target() == Room.RELAX_ROOM
    assert context.get_current_mode() == Mode.STUDY
    assert context.state.drawing_light == PowerState.ON

    context.clear_return_target()

    assert context.get_return_target() is None


def test_workflow_engine_generates_current_relax_to_sleep_plan():
    context = ContextManager()
    context.set_current_room(Room.RELAX_ROOM)
    context.state.relax.light = PowerState.ON
    context.state.relax.tv = PowerState.ON

    workflow = WorkflowEngine(context).create_sleep_workflow()

    assert action_signature(workflow) == [
        (ActionType.LIGHT_OFF, "relax_light"),
        (ActionType.TV_OFF, "relax_tv"),
        (ActionType.OPEN_DOOR, "relax_door"),
        (ActionType.CLOSE_DOOR, "relax_door"),
        (ActionType.LIGHT_ON, "drawing_light"),
        (ActionType.OPEN_DOOR, "sleep_door"),
        (ActionType.CLOSE_DOOR, "sleep_door"),
        (ActionType.LIGHT_ON, "sleep_light"),
        (ActionType.PREPARE_BED, "sleep_bed"),
        (ActionType.LIGHT_OFF, "drawing_light"),
    ]


def test_json_protocol_serializes_single_action():
    action = Action(
        ActionType.LIGHT_ON,
        "study_light",
        parameters={"brightness": 80},
    )

    assert JSONProtocol.action_to_dict(action) == {
        "device": "study_light",
        "action": "LIGHT_ON",
        "parameters": {"brightness": 80},
    }

    assert json.loads(JSONProtocol.action_to_json(action)) == {
        "device": "study_light",
        "action": "LIGHT_ON",
        "parameters": {"brightness": 80},
    }


def test_json_protocol_serializes_action_lists():
    actions = [
        Action(ActionType.OPEN_DOOR, "sleep_door"),
        Action(ActionType.CLOSE_DOOR, "sleep_door"),
    ]

    assert JSONProtocol.actions_to_dict(actions) == [
        {
            "device": "sleep_door",
            "action": "OPEN_DOOR",
            "parameters": {},
        },
        {
            "device": "sleep_door",
            "action": "CLOSE_DOOR",
            "parameters": {},
        },
    ]

    assert json.loads(JSONProtocol.actions_to_json(actions)) == [
        {
            "device": "sleep_door",
            "action": "OPEN_DOOR",
            "parameters": {},
        },
        {
            "device": "sleep_door",
            "action": "CLOSE_DOOR",
            "parameters": {},
        },
    ]
