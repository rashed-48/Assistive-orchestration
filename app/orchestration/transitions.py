from app.orchestration.actions import Action, ActionType
from app.orchestration.state import Room


class TransitionBuilder:

    ROOM_DOORS = {
        Room.STUDY_ROOM: "study_door",
        Room.RELAX_ROOM: "relax_door",
        Room.SLEEP_ROOM: "sleep_door",
        Room.MEAL_ROOM: "meal_door",
    }

    ROOM_LIGHTS = {
        Room.STUDY_ROOM: "study_light",
        Room.RELAX_ROOM: "relax_light",
        Room.SLEEP_ROOM: "sleep_light",
        Room.MEAL_ROOM: "meal_light",
    }

    def __init__(self, context):
        self.context = context

    # ==========================================================
    # MAIN TRANSITION
    # ==========================================================

    def transition_to(self, destination: Room):

        current = self.context.get_current_room()

        # Already there
        if current == destination:
            return []

        # ------------------------------------------------------
        # ANYWHERE -> OUTSIDE
        # ------------------------------------------------------

        if destination == Room.OUTSIDE:

            if current == Room.OUTSIDE:
                return []

            if current == Room.DRAWING_ROOM:
                return self._transition_to_outside()

            # Functional room -> Drawing -> Outside
            actions = []

            actions.extend(
                self._transition_to_drawing()
            )

            actions.extend(
                self._transition_to_outside()
            )

            return actions

        # ------------------------------------------------------
        # ANYWHERE -> DRAWING ROOM
        # ------------------------------------------------------

        if destination == Room.DRAWING_ROOM:

            return self._transition_to_drawing()

        # ------------------------------------------------------
        # OUTSIDE -> FUNCTIONAL ROOM
        # ------------------------------------------------------

        if current == Room.OUTSIDE:

            return self._outside_to_functional(
                destination
            )

        # ------------------------------------------------------
        # DRAWING ROOM -> FUNCTIONAL ROOM
        # ------------------------------------------------------

        if current == Room.DRAWING_ROOM:

            return self._drawing_to_functional(
                destination
            )

        # ------------------------------------------------------
        # FUNCTIONAL ROOM -> FUNCTIONAL ROOM
        # ------------------------------------------------------

        if current in self.ROOM_DOORS:

            return self._functional_to_functional(
                current,
                destination
            )

        raise ValueError(
            f"Unsupported transition: "
            f"{current} -> {destination}"
        )

    # ==========================================================
    # OUTSIDE -> FUNCTIONAL ROOM
    # ==========================================================

    def _outside_to_functional(self, destination):

        actions = []

        # ------------------------------------------------------
        # Outside -> Drawing Room
        #
        # The exit door is the same physical door used to
        # enter/leave the house.
        # ------------------------------------------------------

        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                "exit_door"
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                "exit_door"
            )
        )

        # Drawing room is the transition area
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "drawing_light"
            )
        )

        # Drawing Room -> Destination
        actions.extend(
            self._enter_functional_room(
                destination
            )
        )

        return actions

    # ==========================================================
    # DRAWING ROOM -> FUNCTIONAL ROOM
    # ==========================================================

    def _drawing_to_functional(self, destination):

        return self._enter_functional_room(
            destination
        )

    # ==========================================================
    # FUNCTIONAL ROOM -> FUNCTIONAL ROOM
    # ==========================================================

    def _functional_to_functional(
        self,
        current,
        destination
    ):

        actions = []

        current_door = self.ROOM_DOORS[current]
        current_light = self.ROOM_LIGHTS[current]

        # ------------------------------------------------------
        # Turn off current room light
        # ------------------------------------------------------

        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                current_light
            )
        )

        # ------------------------------------------------------
        # Turn off room-specific devices
        # ------------------------------------------------------

        if current == Room.RELAX_ROOM:

            actions.append(
                Action(
                    ActionType.TV_OFF,
                    "relax_tv"
                )
            )

        # ------------------------------------------------------
        # Leave current room
        # ------------------------------------------------------

        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                current_door
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                current_door
            )
        )

        # ------------------------------------------------------
        # Turn on drawing room light
        # ------------------------------------------------------

        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "drawing_light"
            )
        )

        # ------------------------------------------------------
        # Enter destination room
        # ------------------------------------------------------

        actions.extend(
            self._enter_functional_room(
                destination
            )
        )

        return actions

    # ==========================================================
    # FUNCTIONAL ROOM -> DRAWING ROOM
    # ==========================================================

    def _transition_to_drawing(self):

        current = self.context.get_current_room()

        # Already in drawing room
        if current == Room.DRAWING_ROOM:
            return []

        # Outside -> Drawing Room
        if current == Room.OUTSIDE:

            return [
                Action(
                    ActionType.OPEN_DOOR,
                    "exit_door"
                ),
                Action(
                    ActionType.CLOSE_DOOR,
                    "exit_door"
                ),
                Action(
                    ActionType.LIGHT_ON,
                    "drawing_light"
                ),
            ]

        # Functional room -> Drawing Room
        current_door = self.ROOM_DOORS[current]
        current_light = self.ROOM_LIGHTS[current]

        actions = []

        # Turn off current room light
        actions.append(
            Action(
                ActionType.LIGHT_OFF,
                current_light
            )
        )

        # Relax room has TV
        if current == Room.RELAX_ROOM:

            actions.append(
                Action(
                    ActionType.TV_OFF,
                    "relax_tv"
                )
            )

        # Leave current room
        actions.append(
            Action(
                ActionType.OPEN_DOOR,
                current_door
            )
        )

        actions.append(
            Action(
                ActionType.CLOSE_DOOR,
                current_door
            )
        )

        # Turn on drawing room light
        actions.append(
            Action(
                ActionType.LIGHT_ON,
                "drawing_light"
            )
        )

        return actions

    # ==========================================================
    # DRAWING ROOM -> OUTSIDE
    # ==========================================================

    def _transition_to_outside(self):

        return [
            Action(
                ActionType.LIGHT_OFF,
                "drawing_light"
            ),
            Action(
                ActionType.OPEN_DOOR,
                "exit_door"
            ),
            Action(
                ActionType.CLOSE_DOOR,
                "exit_door"
            ),
        ]

    # ==========================================================
    # ENTER FUNCTIONAL ROOM
    # ==========================================================

    def _enter_functional_room(self, destination):

        door = self.ROOM_DOORS[destination]

        return [
            Action(
                ActionType.OPEN_DOOR,
                door
            ),
            Action(
                ActionType.CLOSE_DOOR,
                door
            ),
        ]