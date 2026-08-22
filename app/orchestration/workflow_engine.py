from app.orchestration.actions import Action, ActionType
from app.orchestration.state import Room
from app.orchestration.transitions import TransitionBuilder


class WorkflowEngine:

    def __init__(self, context):
        self.context = context
        self.transitions = TransitionBuilder(context)

    def create_study_workflow(self):

        actions = []

        # Move user to Study Room
        actions.extend(
            self.transitions.transition_to(
                Room.STUDY_ROOM
            )
        )

        # Prepare study environment
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "study_light"
            )
        )

        actions.append(
            Action(
                ActionType.PREPARE_TABLE,
                "study_table"
            )
        )

        # Drawing room is no longer needed
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            )
        )

        return actions

    def create_relax_workflow(self):

        actions = []

        # Move user to Relax Room
        actions.extend(
            self.transitions.transition_to(
                Room.RELAX_ROOM
            )
        )

        # Prepare Relax environment
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "relax_light"
            )
        )

        actions.append(
            Action(
                ActionType.TV_ON,
                "relax_tv"
            )
        )

        # Drawing room is no longer needed
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            )
        )

        return actions

    def create_sleep_workflow(self):

        actions = []

        # Move user to Sleep Room
        actions.extend(
            self.transitions.transition_to(
                Room.SLEEP_ROOM
            )
        )

        # Prepare Sleep environment
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "sleep_light"
            )
        )

        actions.append(
            Action(
                ActionType.PREPARE_BED,
                "sleep_bed"
            )
        )

        # Drawing room is no longer needed
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            )
        )

        return actions

    def create_meal_workflow(self):

        actions = []

        # Move user to Meal Room
        actions.extend(
            self.transitions.transition_to(
                Room.MEAL_ROOM
            )
        )

        # Prepare meal environment
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "meal_light"
            )
        )

        actions.append(
            Action(
                ActionType.PREPARE_TABLE,
                "meal_table"
            )
        )

        # Drawing room is no longer needed
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            )
        )

        return actions
    def create_return_workflow(self):

        actions = []

        # Get the room the user should return to
        return_target = self.context.get_return_target()

        if return_target is None:
            raise ValueError(
                "No return target is available."
            )

        # Move to the previous functional room
        actions.extend(
            self.transitions.transition_to(
                return_target
            )
        )

        # Prepare destination environment
        if return_target == Room.STUDY_ROOM:

            actions.append(
                Action(
                    ActionType.LIGHT_ON,
                    "study_light"
                )
            )

            actions.append(
                Action(
                    ActionType.PREPARE_TABLE,
                    "study_table"
                )
            )

        elif return_target == Room.RELAX_ROOM:

            actions.append(
                Action(
                    ActionType.LIGHT_ON,
                    "relax_light"
                )
            )

            actions.append(
                Action(
                    ActionType.TV_ON,
                    "relax_tv"
                )
            )

        elif return_target == Room.SLEEP_ROOM:

            actions.append(
                Action(
                    ActionType.LIGHT_ON,
                    "sleep_light"
                )
            )

            actions.append(
                Action(
                    ActionType.PREPARE_BED,
                    "sleep_bed"
                )
            )

        elif return_target == Room.MEAL_ROOM:

            actions.append(
                Action(
                    ActionType.LIGHT_ON,
                    "meal_light"
                )
            )

            actions.append(
                Action(
                    ActionType.PREPARE_TABLE,
                    "meal_table"
                )
            )

        # Drawing room is no longer needed
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            )
        )

        return actions
    def create_leave_workflow(self):

        actions = []

        # Move from current room to outside
        actions.extend(
            self.transitions.transition_to(
                Room.OUTSIDE
            )
        )

        return actions
    def create_emergency_workflow(self):

        actions = []

        # ==============================================
        # EMERGENCY ESCAPE
        # ==============================================

        # Open all functional-room doors immediately
        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "study_door"
            )
        )

        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "relax_door"
            )
        )

        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "sleep_door"
            )
        )

        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "meal_door"
            )
        )

        # Open house exit
        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "exit_door"
            )
        )

        # Activate emergency buzzer
        actions.append(
            Action(
                ActionType.BUZZER_ON,
                "buzzer"
            )
        )

        # ==============================================
        # AFTER USER HAS ESCAPED
        # ==============================================

        # Close all functional-room doors
        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "study_door"
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "relax_door"
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "sleep_door"
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "meal_door"
            )
        )

        # Close house exit
        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "exit_door"
            )
        )

        return actions
    def create_medication_workflow(self):

        actions = []

        current = self.context.get_current_room()

        # If the user is not already in the Sleep Room,
        # move there using the normal transition system.
        if current != Room.SLEEP_ROOM:

            actions.extend(
                self.transitions.transition_to(
                    Room.SLEEP_ROOM
                )
            )

            # Prepare the Sleep environment
            actions.append(
                Action(
                    ActionType.LIGHT_ON,
                    "sleep_light"
                )
            )

            actions.append(
                Action(
                    ActionType.PREPARE_BED,
                    "sleep_bed"
                )
            )

            actions.append(
                Action(
                    ActionType.LIGHT_OFF,
                    "drawing_light"
                )
            )

        # Activate medication servo
        actions.append(
            Action(
                ActionType.ACTIVATE_MEDICATION,
                "medication_servo"
            )
        )

        return actions
    def create_wake_up_workflow(self):

        actions = []

        current = self.context.get_current_room()

        # Wake-up affects the bed only when the user
        # is currently in the Sleep Room.
        if current == Room.SLEEP_ROOM:

            actions.append(
                Action(
                    ActionType.RESET_BED,
                    "sleep_bed"
                )
            )

        return actions
    def create_shutdown_workflow(self):

        actions = []

        # Shutdown and leave the house.
        # The transition system already handles:
        # current room -> drawing room -> outside

        actions.extend(
            self.transitions.transition_to(
                Room.OUTSIDE
            )
        )

        return actions