from app.orchestration.actions import ActionType
from app.orchestration.state import Room, Mode


class MockDeviceExecutor:

    def __init__(self, context):
        self.context = context

    # ==================================================
    # WORKFLOW EXECUTION
    # ==================================================

    def execute_workflow(
        self,
        actions,
        destination: Room,
        mode: Mode
    ):
        """
        Execute all physical/device actions in the workflow.

        After execution, update the logical environment state.
        """

        previous_room = self.context.get_current_room()

        # Execute every physical action
        for action in actions:
            self.execute(action)

        # Update current room
        self.context.set_current_room(destination)

        functional_rooms = {
            Room.STUDY_ROOM,
            Room.RELAX_ROOM,
            Room.SLEEP_ROOM,
            Room.MEAL_ROOM,
        }

        # --------------------------------------------------
        # User has left the house
        # --------------------------------------------------

        if destination == Room.OUTSIDE:

            self.context.clear_return_target()

        # --------------------------------------------------
        # Moving between functional rooms
        # --------------------------------------------------

        elif (
            previous_room in functional_rooms
            and destination in functional_rooms
            and previous_room != destination
        ):

            self.context.set_return_target(
                previous_room
            )

        # --------------------------------------------------
        # Entering a functional room from outside
        # --------------------------------------------------

        elif previous_room == Room.OUTSIDE:

            self.context.clear_return_target()

        # --------------------------------------------------
        # Update current mode
        # --------------------------------------------------

        self.context.set_mode(mode)

    # ==================================================
    # SINGLE ACTION EXECUTION
    # ==================================================

    def execute(self, action):

        print(
            f"[DEVICE] "
            f"{action.action_type.value:<20}"
            f"{action.device_id}"
        )

        if action.action_type == ActionType.LIGHT_ON:
            self._light_on(action.device_id)

        elif action.action_type == ActionType.LIGHT_OFF:
            self._light_off(action.device_id)

        elif action.action_type == ActionType.OPEN_DOOR:
            self._open_door(action.device_id)

        elif action.action_type == ActionType.CLOSE_DOOR:
            self._close_door(action.device_id)

        elif action.action_type == ActionType.PREPARE_TABLE:
            self._prepare_table(action.device_id)

        elif action.action_type == ActionType.RESET_TABLE:
            self._reset_table(action.device_id)

        elif action.action_type == ActionType.PREPARE_BED:
            self._prepare_bed(action.device_id)

        elif action.action_type == ActionType.RESET_BED:
            self._reset_bed(action.device_id)

        elif action.action_type == ActionType.TV_ON:
            self._tv_on(action.device_id)

        elif action.action_type == ActionType.TV_OFF:
            self._tv_off(action.device_id)

        elif action.action_type == ActionType.ACTIVATE_MEDICATION:
            self._activate_medication()

        elif action.action_type == ActionType.BUZZER_ON:
            self._buzzer_on()

        elif action.action_type == ActionType.BUZZER_OFF:
            self._buzzer_off()

        else:
            raise ValueError(
                f"Unsupported action: {action.action_type}"
            )

    # ==================================================
    # LIGHTS
    # ==================================================

    def _light_on(self, device_id):

        from app.orchestration.state import PowerState

        if device_id == "drawing_light":

            self.context.set_drawing_light(
                PowerState.ON
            )

        elif device_id == "study_light":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "light",
                PowerState.ON
            )

        elif device_id == "relax_light":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "light",
                PowerState.ON
            )

        elif device_id == "sleep_light":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "light",
                PowerState.ON
            )

        elif device_id == "meal_light":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "light",
                PowerState.ON
            )

    def _light_off(self, device_id):

        from app.orchestration.state import PowerState

        if device_id == "drawing_light":

            self.context.set_drawing_light(
                PowerState.OFF
            )

        elif device_id == "study_light":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "light",
                PowerState.OFF
            )

        elif device_id == "relax_light":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "light",
                PowerState.OFF
            )

        elif device_id == "sleep_light":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "light",
                PowerState.OFF
            )

        elif device_id == "meal_light":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "light",
                PowerState.OFF
            )

    # ==================================================
    # DOORS
    # ==================================================

    def _open_door(self, device_id):

        from app.orchestration.state import DoorState

        if device_id == "study_door":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "door",
                DoorState.OPEN
            )

        elif device_id == "relax_door":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "door",
                DoorState.OPEN
            )

        elif device_id == "sleep_door":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "door",
                DoorState.OPEN
            )

        elif device_id == "meal_door":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "door",
                DoorState.OPEN
            )

        elif device_id == "exit_door":

            self.context.set_exit_door(
                DoorState.OPEN
            )

    def _close_door(self, device_id):

        from app.orchestration.state import DoorState

        if device_id == "study_door":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "door",
                DoorState.CLOSED
            )

        elif device_id == "relax_door":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "door",
                DoorState.CLOSED
            )

        elif device_id == "sleep_door":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "door",
                DoorState.CLOSED
            )

        elif device_id == "meal_door":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "door",
                DoorState.CLOSED
            )

        elif device_id == "exit_door":

            self.context.set_exit_door(
                DoorState.CLOSED
            )

    # ==================================================
    # TABLE
    # ==================================================

    def _prepare_table(self, device_id):

        from app.orchestration.state import PreparationState

        if device_id == "study_table":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "table",
                PreparationState.READY
            )

        elif device_id == "meal_table":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "table",
                PreparationState.READY
            )

    def _reset_table(self, device_id):

        from app.orchestration.state import PreparationState

        if device_id == "study_table":

            self.context.set_device_state(
                Room.STUDY_ROOM,
                "table",
                PreparationState.NORMAL
            )

        elif device_id == "meal_table":

            self.context.set_device_state(
                Room.MEAL_ROOM,
                "table",
                PreparationState.NORMAL
            )

    # ==================================================
    # BED
    # ==================================================

    def _prepare_bed(self, device_id):

        from app.orchestration.state import PreparationState

        if device_id == "sleep_bed":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "bed",
                PreparationState.READY
            )

    def _reset_bed(self, device_id):

        from app.orchestration.state import PreparationState

        if device_id == "sleep_bed":

            self.context.set_device_state(
                Room.SLEEP_ROOM,
                "bed",
                PreparationState.NORMAL
            )

    # ==================================================
    # TV
    # ==================================================

    def _tv_on(self, device_id):

        from app.orchestration.state import PowerState

        if device_id == "relax_tv":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "tv",
                PowerState.ON
            )

    def _tv_off(self, device_id):

        from app.orchestration.state import PowerState

        if device_id == "relax_tv":

            self.context.set_device_state(
                Room.RELAX_ROOM,
                "tv",
                PowerState.OFF
            )

    # ==================================================
    # MEDICATION
    # ==================================================

    def _activate_medication(self):

        from app.orchestration.state import PowerState

        self.context.state.sleep.medication_servo = (
            PowerState.ON
        )

    # ==================================================
    # BUZZER
    # ==================================================

    def _buzzer_on(self):

        from app.orchestration.state import PowerState

        self.context.set_buzzer(
            PowerState.ON
        )

    def _buzzer_off(self):

        from app.orchestration.state import PowerState

        self.context.set_buzzer(
            PowerState.OFF
        )