from app.orchestration.actions import Action, ActionType
from app.orchestration.state import DoorState, PowerState, Room
from app.orchestration.transitions import TransitionBuilder


class WorkflowEngine:

    def __init__(self, context):
        self.context = context
        self.transitions = TransitionBuilder(context)

    def create_study_workflow(self):

        actions = []

        # Ask the transition layer whether the corridor is actually
        # traversed. It owns the topology; this workflow only needs to
        # know whether to release the corridor light afterwards.
        leaves_via_drawing_room = (
            self.transitions.uses_drawing_room(
                Room.STUDY_ROOM
            )
        )

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

        # Release the corridor, but only if it was actually traversed.
        # Standing still must not switch off a light nobody turned on.
        if leaves_via_drawing_room:
            actions.append(
                Action(
                    ActionType.LIGHT_OFF,
                    "drawing_light"
                )
            )

        return actions

    def create_relax_workflow(self):

        actions = []

        # Ask the transition layer whether the corridor is actually
        # traversed. It owns the topology; this workflow only needs to
        # know whether to release the corridor light afterwards.
        leaves_via_drawing_room = (
            self.transitions.uses_drawing_room(
                Room.RELAX_ROOM
            )
        )

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

        # Release the corridor, but only if it was actually traversed.
        # Standing still must not switch off a light nobody turned on.
        if leaves_via_drawing_room:
            actions.append(
                Action(
                    ActionType.LIGHT_OFF,
                    "drawing_light"
                )
            )

        return actions

    def create_sleep_workflow(self):

        actions = []

        # Ask the transition layer whether the corridor is actually
        # traversed. It owns the topology; this workflow only needs to
        # know whether to release the corridor light afterwards.
        leaves_via_drawing_room = (
            self.transitions.uses_drawing_room(
                Room.SLEEP_ROOM
            )
        )

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

        # Release the corridor, but only if it was actually traversed.
        # Standing still must not switch off a light nobody turned on.
        if leaves_via_drawing_room:
            actions.append(
                Action(
                    ActionType.LIGHT_OFF,
                    "drawing_light"
                )
            )

        return actions

    def create_meal_workflow(self):

        actions = []

        # Ask the transition layer whether the corridor is actually
        # traversed. It owns the topology; this workflow only needs to
        # know whether to release the corridor light afterwards.
        leaves_via_drawing_room = (
            self.transitions.uses_drawing_room(
                Room.MEAL_ROOM
            )
        )

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

        # Release the corridor, but only if it was actually traversed.
        # Standing still must not switch off a light nobody turned on.
        if leaves_via_drawing_room:
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

        # Ask the transition layer whether the corridor is actually
        # traversed. It owns the topology; this workflow only needs to
        # know whether to release the corridor light afterwards.
        leaves_via_drawing_room = (
            self.transitions.uses_drawing_room(
                return_target
            )
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

        # Release the corridor, but only if it was actually traversed.
        # Standing still must not switch off a light nobody turned on.
        if leaves_via_drawing_room:
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
    # Doors that make up the escape route, in the order they are
    # attempted. The shared exit comes first: if execution degrades,
    # the one door everybody needs should already have been tried.
    ESCAPE_DOORS = (
        "exit_door",
        "study_door",
        "relax_door",
        "sleep_door",
        "meal_door",
    )

    def _door_state(self, device):

        state = self.context.get_state()

        if device == "exit_door":
            return state.exit_door

        return {
            "study_door": state.study,
            "relax_door": state.relax,
            "sleep_door": state.sleep,
            "meal_door": state.meal,
        }[device].door

    def create_emergency_workflow(self):
        """Open the escape route and raise the alarm.

        This workflow does NOT close anything. The route stays open
        until a confirmed EMERGENCY_CLEAR closes it, because the
        software has no way to know whether anyone has got out.

        It is state aware like every other workflow, so re-issuing
        EMERGENCY asks only for whatever is not already true. That
        makes a repeat command a safe retry of a partial emergency
        rather than a second full actuation.

        The Drawing Room light is deliberately untouched: an
        evacuation is not a room-to-room transition, and the corridor
        rules do not apply to it.
        """

        actions = []

        # Raise the alarm first: it is what tells the person to move.
        if self.context.get_state().buzzer != PowerState.ON:

            actions.append(
                Action(
                    ActionType.BUZZER_ON,
                    "buzzer"
                )
            )

        for door in self.ESCAPE_DOORS:

            if self._door_state(door) != DoorState.OPEN:

                actions.append(
                    Action(
                        ActionType.OPEN_DOOR,
                        door
                    )
                )

        return actions

    def create_emergency_clear_workflow(self):
        """Silence the alarm and close the escape route again.

        Only reached through a confirmed EMERGENCY_CLEAR. Like entry,
        it is state aware, so retrying after a partial failure asks
        only for the outstanding work.

        The internal doors are closed before the exit, so the house is
        secured from the inside outwards.
        """

        actions = []

        if self.context.get_state().buzzer == PowerState.ON:

            actions.append(
                Action(
                    ActionType.BUZZER_OFF,
                    "buzzer"
                )
            )

        for door in reversed(self.ESCAPE_DOORS):

            if self._door_state(door) == DoorState.OPEN:

                actions.append(
                    Action(
                        ActionType.CLOSE_DOOR,
                        door
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
    FUNCTIONAL_ROOMS = (
        Room.STUDY_ROOM,
        Room.RELAX_ROOM,
        Room.SLEEP_ROOM,
        Room.MEAL_ROOM,
    )

    # Appliances that must be powered off along with a room's light.
    SHUTDOWN_APPLIANCES = {
        Room.RELAX_ROOM: [
            (ActionType.TV_OFF, "relax_tv"),
        ],
    }

    # Prepared surfaces that must return to their resting state.
    SHUTDOWN_RESETS = {
        Room.STUDY_ROOM: [
            (ActionType.RESET_TABLE, "study_table"),
        ],
        Room.SLEEP_ROOM: [
            (ActionType.RESET_BED, "sleep_bed"),
        ],
        Room.MEAL_ROOM: [
            (ActionType.RESET_TABLE, "meal_table"),
        ],
    }

    def create_shutdown_workflow(self):

        actions = []

        current = self.context.get_current_room()

        # ==============================================
        # DEACTIVATE THE WHOLE ENVIRONMENT
        #
        # Shutdown is more than leaving: every functional
        # room is powered down, not only the one the user
        # happens to be standing in.
        # ==============================================

        for room in self.FUNCTIONAL_ROOMS:

            # The transition below already turns off the light and
            # the TV of the room being left, so don't command those
            # a second time here.
            if room != current:

                actions.append(
                    Action(
                        ActionType.LIGHT_OFF,
                        self.transitions.ROOM_LIGHTS[room]
                    )
                )

                for action_type, device in (
                    self.SHUTDOWN_APPLIANCES.get(room, [])
                ):
                    actions.append(
                        Action(action_type, device)
                    )

            # A transition never touches furniture, so prepared
            # surfaces are reset for every room, including the one
            # being left.
            for action_type, device in (
                self.SHUTDOWN_RESETS.get(room, [])
            ):
                actions.append(
                    Action(action_type, device)
                )

        # ==============================================
        # LEAVE THE HOUSE
        #
        # The transition system already handles:
        # current room -> drawing room -> outside
        # ==============================================

        actions.extend(
            self.transitions.transition_to(
                Room.OUTSIDE
            )
        )

        return actions