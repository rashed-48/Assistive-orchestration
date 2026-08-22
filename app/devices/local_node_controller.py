from app.orchestration.actions import Action, ActionType


class LocalNodeController:

    def __init__(self, node_id: str, devices: set[str]):
        self.node_id = node_id
        self.devices = devices

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

        elif action_type == ActionType.PREPARE_BED:
            self._prepare_bed(device)

        elif action_type == ActionType.RESET_BED:
            self._reset_bed(device)

        elif action_type == ActionType.ACTIVATE_MEDICATION:
            self._activate_medication(device)

        elif action_type == ActionType.BUZZER_ON:
            self._buzzer_on(device)

        else:
            raise ValueError(
                f"Unsupported action: {action_type}"
            )

    def _light_on(self, device):
        print(f"[HARDWARE] LIGHT ON → {device}")

    def _light_off(self, device):
        print(f"[HARDWARE] LIGHT OFF → {device}")

    def _open_door(self, device):
        print(f"[HARDWARE] OPEN DOOR → {device}")

    def _close_door(self, device):
        print(f"[HARDWARE] CLOSE DOOR → {device}")

    def _tv_on(self, device):
        print(f"[HARDWARE] TV ON → {device}")

    def _tv_off(self, device):
        print(f"[HARDWARE] TV OFF → {device}")

    def _prepare_table(self, device):
        print(f"[HARDWARE] PREPARE TABLE → {device}")

    def _prepare_bed(self, device):
        print(f"[HARDWARE] PREPARE BED → {device}")

    def _reset_bed(self, device):
        print(f"[HARDWARE] RESET BED → {device}")

    def _activate_medication(self, device):
        print(f"[HARDWARE] ACTIVATE MEDICATION → {device}")

    def _buzzer_on(self, device):
        print(f"[HARDWARE] BUZZER ON → {device}")