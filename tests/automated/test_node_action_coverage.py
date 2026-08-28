"""Node-side action coverage.

Audit finding E7: LocalNodeController has no branch for BUZZER_OFF or
RESET_TABLE, so a simulated ESP32 raises and publishes status "error" for
them. Latent today, but it blocks any reset or alarm-silencing workflow.

A node must be able to execute every action the planner is capable of
producing, which is every member of ActionType.
"""

import pytest

from app.devices.local_node_controller import LocalNodeController
from app.devices.node_devices import (
    ESP32_A_DEVICES,
    ESP32_B_DEVICES,
    ESP32_C_DEVICES,
)
from app.orchestration.actions import Action, ActionType

from tests.automated.support import quiet


ALL_NODE_DEVICES = ESP32_A_DEVICES | ESP32_B_DEVICES | ESP32_C_DEVICES


# A representative real device for each action type.
DEVICE_FOR_ACTION = {
    ActionType.OPEN_DOOR: "relax_door",
    ActionType.CLOSE_DOOR: "relax_door",
    ActionType.LIGHT_ON: "relax_light",
    ActionType.LIGHT_OFF: "relax_light",
    ActionType.TV_ON: "relax_tv",
    ActionType.TV_OFF: "relax_tv",
    ActionType.PREPARE_TABLE: "study_table",
    ActionType.RESET_TABLE: "study_table",
    ActionType.PREPARE_BED: "sleep_bed",
    ActionType.RESET_BED: "sleep_bed",
    ActionType.ACTIVATE_MEDICATION: "medication_servo",
    ActionType.BUZZER_ON: "buzzer",
    ActionType.BUZZER_OFF: "buzzer",
}


def test_every_action_type_has_a_device_in_this_test_matrix():
    # Guards the matrix itself: a new ActionType must not slip through
    # untested.
    assert set(DEVICE_FOR_ACTION) == set(ActionType)


@pytest.mark.parametrize(
    "action_type",
    list(ActionType),
    ids=[action_type.value for action_type in ActionType],
)
def test_local_node_controller_executes_every_action_type(action_type):
    controller = LocalNodeController(
        node_id="test_node",
        devices=ALL_NODE_DEVICES,
    )

    action = Action(action_type, DEVICE_FOR_ACTION[action_type])

    with quiet():
        controller.execute(action)


def test_local_node_controller_still_rejects_a_device_it_does_not_own():
    controller = LocalNodeController(
        node_id="esp32_b",
        devices=ESP32_B_DEVICES,
    )

    with pytest.raises(ValueError):
        with quiet():
            controller.execute(Action(ActionType.LIGHT_ON, "relax_light"))
