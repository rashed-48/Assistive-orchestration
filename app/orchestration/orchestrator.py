from app.orchestration.workflow_engine import WorkflowEngine
from app.orchestration.actions import ActionType
from app.orchestration.state import (
    Room,
    Mode,
    DoorState,
    PowerState,
    PreparationState,
)


class Orchestrator:

    def __init__(
        self,
        context,
        device_executor
    ):
        self.context = context

        self.workflow_engine = WorkflowEngine(
            context
        )

        self.device_executor = device_executor

        self.workflow_map = {
            "STUDY_MODE":
                self.workflow_engine.create_study_workflow,

            "RELAX_MODE":
                self.workflow_engine.create_relax_workflow,

            "PREPARE_FOR_SLEEP":
                self.workflow_engine.create_sleep_workflow,

            "PREPARE_FOR_MEAL":
                self.workflow_engine.create_meal_workflow,

            "MEDICATION":
                self.workflow_engine.create_medication_workflow,

            "WAKE_UP":
                self.workflow_engine.create_wake_up_workflow,

            "LEAVE_ROOM":
                self.workflow_engine.create_leave_workflow,

            "RETURN_TO_ROOM":
                self.workflow_engine.create_return_workflow,

            "EMERGENCY":
                self.workflow_engine.create_emergency_workflow,

            "SHUTDOWN_ENVIRONMENT":
                self.workflow_engine.create_shutdown_workflow,
        }

    # ==========================================================
    # EXECUTE INTENT
    # ==========================================================

    def execute_intent(self, intent):

        if intent not in self.workflow_map:
            raise ValueError(
                f"Unsupported intent: {intent}"
            )

        print("\n" + "=" * 70)
        print("ORCHESTRATION")
        print("=" * 70)

        print(
            f"Intent → {intent}"
        )

        # ------------------------------------------------------
        # Remember where the user was BEFORE the workflow
        # ------------------------------------------------------

        previous_room = (
            self.context.get_current_room()
        )

        previous_mode = (
            self.context.get_current_mode()
        )

        # ------------------------------------------------------
        # Generate workflow
        # ------------------------------------------------------

        workflow_builder = self.workflow_map[intent]

        actions = workflow_builder()

        print(
            f"Generated {len(actions)} actions."
        )

        print("\nActions:")

        for index, action in enumerate(
            actions,
            start=1
        ):
            print(
                f"{index:02d}. "
                f"{action.action_type.value:<20}"
                f"{action.device_id}"
            )

        # ------------------------------------------------------
        # Execute actions ONE BY ONE
        #
        # action succeeds
        #       ↓
        # update physical/logical device state
        #       ↓
        # next action
        #
        # If any action fails, execution stops and
        # current_room/current_mode are NOT changed.
        # ------------------------------------------------------

        results = []

        print("\n" + "=" * 70)
        print("EXECUTING WORKFLOW")
        print("=" * 70)

        for action in actions:

            result = self.device_executor.execute(
                action
            )

            results.append(result)

            # Update device state only after successful ACK
            self._apply_successful_action(
                action
            )

        # ------------------------------------------------------
        # ALL actions succeeded.
        #
        # Now update the user's logical location and mode.
        # ------------------------------------------------------

        self._update_location_and_mode(
            intent=intent,
            previous_room=previous_room,
            previous_mode=previous_mode
        )

        # ------------------------------------------------------
        # Workflow completed
        # ------------------------------------------------------

        print("\n" + "=" * 70)
        print("WORKFLOW COMPLETED")
        print("=" * 70)

        print(
            f"Executed {len(results)} actions successfully."
        )

        print("\n" + "=" * 70)
        print("UPDATED LOGICAL STATE")
        print("=" * 70)

        self.context.print_state()

        return results

    # ==========================================================
    # UPDATE LOCATION + MODE
    # ==========================================================

    def _update_location_and_mode(
        self,
        intent,
        previous_room,
        previous_mode
    ):

        # ------------------------------------------------------
        # Normal room-based intents
        # ------------------------------------------------------

        destination_map = {

            "STUDY_MODE":
                Room.STUDY_ROOM,

            "RELAX_MODE":
                Room.RELAX_ROOM,

            "PREPARE_FOR_SLEEP":
                Room.SLEEP_ROOM,

            "PREPARE_FOR_MEAL":
                Room.MEAL_ROOM,

            "MEDICATION":
                Room.SLEEP_ROOM,
        }

        if intent in destination_map:

            destination = destination_map[intent]

            self.context.set_current_room(
                destination
            )

            # Set corresponding mode
            mode_map = {

                "STUDY_MODE":
                    Mode.STUDY,

                "RELAX_MODE":
                    Mode.RELAX,

                "PREPARE_FOR_SLEEP":
                    Mode.SLEEP,

                "PREPARE_FOR_MEAL":
                    Mode.MEAL,

                "MEDICATION":
                    Mode.SLEEP,
            }

            self.context.set_mode(
                mode_map[intent]
            )

            return

        # ------------------------------------------------------
        # RETURN TO PREVIOUS ROOM
        # ------------------------------------------------------

        if intent == "RETURN_TO_ROOM":

            return_target = (
                self.context.get_return_target()
            )

            if return_target is not None:

                self.context.set_current_room(
                    return_target
                )

                self.context.clear_return_target()

                # Restore the mode according to room
                room_mode_map = {

                    Room.STUDY_ROOM:
                        Mode.STUDY,

                    Room.RELAX_ROOM:
                        Mode.RELAX,

                    Room.SLEEP_ROOM:
                        Mode.SLEEP,

                    Room.MEAL_ROOM:
                        Mode.MEAL,
                }

                self.context.set_mode(
                    room_mode_map.get(
                        return_target,
                        Mode.NONE
                    )
                )

            return

        # ------------------------------------------------------
        # LEAVE HOUSE
        # ------------------------------------------------------

        if intent == "LEAVE_ROOM":

            # Remember where the user was so they can return.
            if previous_room not in (
                Room.OUTSIDE,
                Room.DRAWING_ROOM
            ):
                self.context.set_return_target(
                    previous_room
                )

            self.context.set_current_room(
                Room.OUTSIDE
            )

            self.context.set_mode(
                Mode.NONE
            )

            return

        # ------------------------------------------------------
        # SHUTDOWN
        # ------------------------------------------------------

        if intent == "SHUTDOWN_ENVIRONMENT":

            if previous_room not in (
                Room.OUTSIDE,
                Room.DRAWING_ROOM
            ):
                self.context.set_return_target(
                    previous_room
                )

            self.context.set_current_room(
                Room.OUTSIDE
            )

            self.context.set_mode(
                Mode.NONE
            )

            return

        # ------------------------------------------------------
        # WAKE UP
        #
        # User remains in the same room.
        # Only the mode changes if they are in Sleep Room.
        # ------------------------------------------------------

        if intent == "WAKE_UP":

    # The person wakes up inside the sleep room.
    # They do NOT leave the room.
         if previous_room == Room.SLEEP_ROOM:

          self.context.set_current_room(
            Room.SLEEP_ROOM
        )

        self.context.set_mode(
            Mode.NONE
        )

        return

        # ------------------------------------------------------
        # EMERGENCY
        #
        # Your emergency workflow opens the exit and then
        # closes it. We therefore don't automatically assume
        # the user changed location here.
        # ------------------------------------------------------

        if intent == "EMERGENCY":

            return

    # ==========================================================
    # APPLY SUCCESSFUL ACTION TO LOGICAL STATE
    # ==========================================================

    def _apply_successful_action(self, action):

        action_type = action.action_type
        device = action.device_id

        print(
            f"[STATE] Applying → "
            f"{action_type.value} → {device}"
        )

        # ------------------------------------------------------
        # LIGHTS
        # ------------------------------------------------------

        if action_type == ActionType.LIGHT_ON:

            self._set_light(
                device,
                PowerState.ON
            )

        elif action_type == ActionType.LIGHT_OFF:

            self._set_light(
                device,
                PowerState.OFF
            )

        # ------------------------------------------------------
        # TV
        # ------------------------------------------------------

        elif action_type == ActionType.TV_ON:

            if device == "relax_tv":
                self.context.state.relax.tv = (
                    PowerState.ON
                )

        elif action_type == ActionType.TV_OFF:

            if device == "relax_tv":
                self.context.state.relax.tv = (
                    PowerState.OFF
                )

        # ------------------------------------------------------
        # DOORS
        # ------------------------------------------------------

        elif action_type == ActionType.OPEN_DOOR:

            self._set_door(
                device,
                DoorState.OPEN
            )

        elif action_type == ActionType.CLOSE_DOOR:

            self._set_door(
                device,
                DoorState.CLOSED
            )

        # ------------------------------------------------------
        # TABLE
        # ------------------------------------------------------

        elif action_type == ActionType.PREPARE_TABLE:

            self._set_table(
                device,
                PreparationState.READY
            )

        elif action_type == ActionType.RESET_TABLE:

            self._set_table(
                device,
                PreparationState.NORMAL
            )

        # ------------------------------------------------------
        # BED
        # ------------------------------------------------------

        elif action_type == ActionType.PREPARE_BED:

            if device == "sleep_bed":

                self.context.state.sleep.bed = (
                    PreparationState.READY
                )

        elif action_type == ActionType.RESET_BED:

            if device == "sleep_bed":

                self.context.state.sleep.bed = (
                    PreparationState.NORMAL
                )

        # ------------------------------------------------------
        # MEDICATION
        # ------------------------------------------------------

        elif action_type == ActionType.ACTIVATE_MEDICATION:

            if device == "medication_servo":

                self.context.state.sleep.medication_servo = (
                    PowerState.ON
                )

        # ------------------------------------------------------
        # BUZZER
        # ------------------------------------------------------

        elif action_type == ActionType.BUZZER_ON:

            if device == "buzzer":

                self.context.set_buzzer(
                    PowerState.ON
                )

        elif action_type == ActionType.BUZZER_OFF:

            if device == "buzzer":

                self.context.set_buzzer(
                    PowerState.OFF
                )

    # ==========================================================
    # LIGHT STATE HELPER
    # ==========================================================

    def _set_light(
        self,
        device,
        state
    ):

        if device == "drawing_light":

            self.context.set_drawing_light(
                state
            )

        elif device == "study_light":

            self.context.state.study.light = (
                state
            )

        elif device == "relax_light":

            self.context.state.relax.light = (
                state
            )

        elif device == "sleep_light":

            self.context.state.sleep.light = (
                state
            )

        elif device == "meal_light":

            self.context.state.meal.light = (
                state
            )

    # ==========================================================
    # DOOR STATE HELPER
    # ==========================================================

    def _set_door(
        self,
        device,
        state
    ):

        if device == "study_door":

            self.context.state.study.door = (
                state
            )

        elif device == "relax_door":

            self.context.state.relax.door = (
                state
            )

        elif device == "sleep_door":

            self.context.state.sleep.door = (
                state
            )

        elif device == "meal_door":

            self.context.state.meal.door = (
                state
            )

        elif device == "exit_door":

            self.context.set_exit_door(
                state
            )

    # ==========================================================
    # TABLE STATE HELPER
    # ==========================================================

    def _set_table(
        self,
        device,
        state
    ):

        if device == "study_table":

            self.context.state.study.table = (
                state
            )

        elif device == "meal_table":

            self.context.state.meal.table = (
                state
            )