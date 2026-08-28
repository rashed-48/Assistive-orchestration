from app.orchestration.actions import Action, ActionType


# Resting state of a device kind, keyed by the last word of its id.
# This is simulated *hardware* state, deliberately separate from the
# authoritative EnvironmentState the Orchestrator owns.
RESTING_STATE = {
    "door": "CLOSED",
    "light": "OFF",
    "tv": "OFF",
    "table": "NORMAL",
    "bed": "NORMAL",
    "servo": "OFF",
    "buzzer": "OFF",
}


# State a device lands in once an action has been applied to it.
RESULTING_STATE = {
    ActionType.OPEN_DOOR: "OPEN",
    ActionType.CLOSE_DOOR: "CLOSED",
    ActionType.LIGHT_ON: "ON",
    ActionType.LIGHT_OFF: "OFF",
    ActionType.TV_ON: "ON",
    ActionType.TV_OFF: "OFF",
    ActionType.PREPARE_TABLE: "READY",
    ActionType.RESET_TABLE: "NORMAL",
    ActionType.PREPARE_BED: "READY",
    ActionType.RESET_BED: "NORMAL",
    ActionType.ACTIVATE_MEDICATION: "ON",
    ActionType.BUZZER_ON: "ON",
    ActionType.BUZZER_OFF: "OFF",
}


def resting_state(device_id: str) -> str:
    return RESTING_STATE.get(
        device_id.rsplit("_", 1)[-1],
        "OFF"
    )


class LocalNodeController:

    def __init__(self, node_id: str, devices: set[str]):
        self.node_id = node_id
        self.devices = devices

        # Simulated hardware state for the devices this node owns.
        self.device_states = {
            device: resting_state(device)
            for device in devices
        }

    def get_device_states(self) -> dict:
        return dict(self.device_states)

    def execute(self, action: Action):

        if action.device_id not in self.devices:
            raise ValueError(
                f"{action.device_id} is not controlled "
                f"by {self.node_id}"
            )

        print(
            f"[{self.node_id}] "
            f"LOCAL EXECUTION"
        )

        print(
            f"Device : {action.device_id}"
        )

        print(
            f"Action : {action.action_type.value}"
        )

        self._execute_hardware(action)

        # The simulated hardware has now moved. This is the node's own
        # view of its pins, not the application's logical state.
        self.device_states[action.device_id] = RESULTING_STATE[
            action.action_type
        ]

        print(
            f"State  : {action.device_id} = "
            f"{self.device_states[action.device_id]}"
        )

    def _execute_hardware(self, action: Action):

        action_type = action.action_type
        device = action.device_id

        if action_type == ActionType.LIGHT_ON:
            self._light_on(device)

        elif action_type == ActionType.LIGHT_OFF:
            self._light_off(device)

        elif action_type == ActionType.OPEN_DOOR:
            self._open_door(device)

        elif action_type == ActionType.CLOSE_DOOR:
            self._close_door(device)

        elif action_type == ActionType.TV_ON:
            self._tv_on(device)

        elif action_type == ActionType.TV_OFF:
            self._tv_off(device)

        elif action_type == ActionType.PREPARE_TABLE:
            self._prepare_table(device)

        elif action_type == ActionType.RESET_TABLE:
            self._reset_table(device)

        elif action_type == ActionType.PREPARE_BED:
            self._prepare_bed(device)

        elif action_type == ActionType.RESET_BED:
            self._reset_bed(device)

        elif action_type == ActionType.ACTIVATE_MEDICATION:
            self._activate_medication(device)

        elif action_type == ActionType.BUZZER_ON:
            self._buzzer_on(device)

        elif action_type == ActionType.BUZZER_OFF:
            self._buzzer_off(device)

        else:
            raise ValueError(
                f"Unsupported action: {action_type}"
            )

    def _light_on(self, device):
        print(f"[HARDWARE] LIGHT ON -> {device}")

    def _light_off(self, device):
        print(f"[HARDWARE] LIGHT OFF -> {device}")

    def _open_door(self, device):
        print(f"[HARDWARE] OPEN DOOR -> {device}")

    def _close_door(self, device):
        print(f"[HARDWARE] CLOSE DOOR -> {device}")

    def _tv_on(self, device):
        print(f"[HARDWARE] TV ON -> {device}")

    def _tv_off(self, device):
        print(f"[HARDWARE] TV OFF -> {device}")

    def _prepare_table(self, device):
        print(f"[HARDWARE] PREPARE TABLE -> {device}")

    def _reset_table(self, device):
        print(f"[HARDWARE] RESET TABLE -> {device}")

    def _prepare_bed(self, device):
        print(f"[HARDWARE] PREPARE BED -> {device}")

    def _reset_bed(self, device):
        print(f"[HARDWARE] RESET BED -> {device}")

    def _activate_medication(self, device):
        print(f"[HARDWARE] ACTIVATE MEDICATION -> {device}")

    def _buzzer_on(self, device):
        print(f"[HARDWARE] BUZZER ON -> {device}")

    def _buzzer_off(self, device):
        print(f"[HARDWARE] BUZZER OFF -> {device}")