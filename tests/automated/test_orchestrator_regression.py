import io
from contextlib import redirect_stdout

import pytest

from app.orchestration.actions import ActionType
from app.orchestration.context_manager import ContextManager
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.state import (
    DoorState,
    Mode,
    PowerState,
    PreparationState,
    Room,
)


class RecordingExecutor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        return {
            "status": "success",
            "device": action.device_id,
            "action": action.action_type.value,
        }


class FailingExecutor(RecordingExecutor):
    def __init__(self, fail_at):
        super().__init__()
        self.fail_at = fail_at

    def execute(self, action):
        self.actions.append(action)

        if len(self.actions) == self.fail_at:
            raise RuntimeError(
                f"Injected failure at action {self.fail_at}"
            )

        return {
            "status": "success",
            "device": action.device_id,
            "action": action.action_type.value,
        }


EXPECTED_RELAX_TO_SLEEP_ACTIONS = [
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


def action_signature(actions):
    return [
        (action.action_type, action.device_id)
        for action in actions
    ]


def create_relax_context():
    context = ContextManager()

    context.set_current_room(Room.RELAX_ROOM)
    context.set_return_target(Room.STUDY_ROOM)
    context.set_mode(Mode.RELAX)

    context.state.relax.light = PowerState.ON
    context.state.relax.tv = PowerState.ON

    return context


def execute_without_console_output(orchestrator, intent):
    with redirect_stdout(io.StringIO()):
        return orchestrator.execute_intent(intent)


def test_prepare_for_sleep_from_relax_updates_logical_state_after_success():
    context = create_relax_context()
    executor = RecordingExecutor()
    orchestrator = Orchestrator(
        context=context,
        device_executor=executor,
    )

    results = execute_without_console_output(
        orchestrator,
        "PREPARE_FOR_SLEEP",
    )

    assert len(results) == len(EXPECTED_RELAX_TO_SLEEP_ACTIONS)
    assert action_signature(executor.actions) == EXPECTED_RELAX_TO_SLEEP_ACTIONS

    assert context.get_current_room() == Room.SLEEP_ROOM
    assert context.get_current_mode() == Mode.SLEEP

    assert context.state.relax.light == PowerState.OFF
    assert context.state.relax.tv == PowerState.OFF
    assert context.state.relax.door == DoorState.CLOSED

    assert context.state.sleep.light == PowerState.ON
    assert context.state.sleep.bed == PreparationState.READY
    assert context.state.sleep.door == DoorState.CLOSED

    assert context.state.drawing_light == PowerState.OFF
    assert context.state.exit_door == DoorState.CLOSED


def test_prepare_for_sleep_failure_keeps_room_and_mode_at_previous_values():
    context = create_relax_context()
    executor = FailingExecutor(fail_at=6)
    orchestrator = Orchestrator(
        context=context,
        device_executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="Injected failure at action 6",
    ):
        execute_without_console_output(
            orchestrator,
            "PREPARE_FOR_SLEEP",
        )

    assert action_signature(executor.actions) == EXPECTED_RELAX_TO_SLEEP_ACTIONS[:6]

    assert context.get_current_room() == Room.RELAX_ROOM
    assert context.get_current_mode() == Mode.RELAX

    assert context.state.relax.light == PowerState.OFF
    assert context.state.relax.tv == PowerState.OFF
    assert context.state.relax.door == DoorState.CLOSED

    assert context.state.drawing_light == PowerState.ON

    assert context.state.sleep.light == PowerState.OFF
    assert context.state.sleep.bed == PreparationState.NORMAL
    assert context.state.sleep.door == DoorState.CLOSED
