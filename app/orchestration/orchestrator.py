from app.orchestration.workflow_engine import WorkflowEngine
from app.orchestration.actions import ActionType
from app.orchestration.state import (
    Room,
    Mode,
    DoorState,
    PowerState,
    PreparationState,
)


class EmergencyActive(Exception):
    """A normal workflow was requested while the environment is in emergency."""

    def __init__(self, intent):
        self.intent = intent

        super().__init__(
            f"{intent} is blocked: the environment is in emergency. "
            f"Clear the emergency first."
        )


class LocationUnknown(Exception):
    """A workflow needs to know where the person is, and the system does not."""

    def __init__(self, intent, status, last_known=None):
        self.intent = intent
        self.status = status
        self.last_known = last_known

        super().__init__(
            f"{intent} needs a known location, but the location is "
            f"{status.value}"
            + (f" (last known: {last_known.value})" if last_known else "")
            + ". Confirm where the person is before continuing."
        )


class ActionNotAcknowledged(Exception):
    """A device did not confirm an action, so no state was committed."""

    def __init__(self, action, result):
        self.action = action
        self.result = result

        super().__init__(
            f"No successful acknowledgement for "
            f"{action.action_type.value} {action.device_id}: {result!r}"
        )


class Orchestrator:

    # Intents that stay available once the emergency latch is set.
    EMERGENCY_INTENTS = frozenset({"EMERGENCY", "EMERGENCY_CLEAR"})

    # Safety workflows attempt every action even if one fails. An alarm
    # must not be abandoned because a single door did not answer.
    BEST_EFFORT_INTENTS = frozenset({"EMERGENCY", "EMERGENCY_CLEAR"})

    # Everything else plans from the person's current room, so it needs
    # that room to be a fact. Emergency handling deliberately does not:
    # it opens every door and sounds the alarm regardless of where
    # anyone is, which is exactly what makes it usable when the location
    # is in doubt.
    LOCATION_INDEPENDENT_INTENTS = frozenset({"EMERGENCY", "EMERGENCY_CLEAR"})

    def __init__(
        self,
        context,
        device_executor,
        action_observer=None
    ):
        self.context = context

        # Called after an action has been acknowledged AND its logical
        # commit has happened. The Orchestrator knows nothing about what
        # the observer does with it; persistence lives in the runtime.
        self.action_observer = action_observer

        # Called once with the full ordered plan, before the first
        # action is dispatched. Lets an interface show what is about to
        # happen and then tick actions off as they complete. Same
        # contract as action_observer: purely informational, never
        # allowed to affect the workflow.
        self.plan_observer = None

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

            "EMERGENCY_CLEAR":
                self.workflow_engine.create_emergency_clear_workflow,

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

        # ------------------------------------------------------
        # EMERGENCY LATCH
        #
        # While the environment is in emergency, only emergency
        # handling and emergency recovery may run. Blocked commands
        # are refused outright: nothing is queued, nothing is
        # partially executed, and the latch is untouched.
        # ------------------------------------------------------

        emergency_is_active = (
            self.context.get_current_mode() == Mode.EMERGENCY
        )

        if (
            emergency_is_active
            and intent not in self.EMERGENCY_INTENTS
        ):
            raise EmergencyActive(intent)

        if (
            intent == "EMERGENCY_CLEAR"
            and not emergency_is_active
        ):
            raise ValueError(
                "There is no active emergency to clear."
            )

        # ------------------------------------------------------
        # LOCATION CERTAINTY
        #
        # Planning from a location the system is not sure about
        # would send the person through doors based on a guess.
        # Refuse instead, and say what needs resolving.
        # ------------------------------------------------------

        if (
            not self.context.location_is_known()
            and intent not in self.LOCATION_INDEPENDENT_INTENTS
        ):
            raise LocationUnknown(
                intent,
                self.context.get_location_status(),
                self.context.get_current_room(),
            )

        print("\n" + "=" * 70)
        print("ORCHESTRATION")
        print("=" * 70)

        print(
            f"Intent -> {intent}"
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

        # ------------------------------------------------------
        # Latch the emergency before touching any hardware.
        #
        # Emergency mode is a system posture, not a claim about the
        # physical world, so it must not wait for devices to
        # cooperate. A partly-failed alarm is still an emergency.
        # Device and location state continue to follow
        # acknowledgements as normal.
        # ------------------------------------------------------

        if intent == "EMERGENCY":
            self.context.set_mode(
                Mode.EMERGENCY
            )

            # Durable evidence of the declaration, so a restart can
            # restore the latch instead of inheriting a fresh Mode.NONE.
            self.context.declare_emergency()

        workflow_builder = self.workflow_map[intent]

        actions = workflow_builder()

        # ------------------------------------------------------
        # Is this workflow going to move the person?
        #
        # Worked out before execution so an interrupted move can
        # record both ends of the journey.
        # ------------------------------------------------------

        destination = self._destination_for(intent)

        is_movement = (
            destination is not None
            and destination != previous_room
        )

        if is_movement:
            self.context.begin_transit(
                destination,
                reason=f"{intent} in progress",
            )

        print(
            f"Generated {len(actions)} actions."
        )

        self._observe_plan(intent, actions)

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
        #       v
        # update physical/logical device state
        #       v
        # next action
        #
        # If any action fails, execution stops and
        # current_room/current_mode are NOT changed.
        # ------------------------------------------------------

        results = []

        print("\n" + "=" * 70)
        print("EXECUTING WORKFLOW")
        print("=" * 70)

        best_effort = intent in self.BEST_EFFORT_INTENTS

        # A person can only leave a room through a door. If no door was
        # opened, an interrupted workflow cannot have moved them, and
        # the source room is still an honest answer.
        doors_opened = False

        for action in actions:

            try:
                result = self.device_executor.execute(
                    action
                )

            except Exception as error:

                if not best_effort:
                    self._abandon_transit(
                        is_movement, doors_opened, previous_room, intent
                    )
                    raise

                # A safety workflow keeps going: the next door may
                # still be reachable.
                print(
                    f"[STATE] Action failed -> "
                    f"{action.action_type.value} -> "
                    f"{action.device_id}: {error}"
                )

                results.append(
                    self._failure_result(action, error)
                )

                continue

            results.append(result)

            # ----------------------------------------------
            # F5: commit only what the device confirmed.
            # ----------------------------------------------

            if self._is_acknowledged(result, action):

                if action.action_type == ActionType.OPEN_DOOR:
                    doors_opened = True

                self._apply_successful_action(
                    action
                )

                self._observe(intent, action, result)

                continue

            if not best_effort:
                self._abandon_transit(
                    is_movement, doors_opened, previous_room, intent
                )
                raise ActionNotAcknowledged(action, result)

            print(
                f"[STATE] Not acknowledged -> "
                f"{action.action_type.value} -> "
                f"{action.device_id}"
            )

        # ------------------------------------------------------
        # Every action was acknowledged, or this is a safety
        # workflow that ran best effort.
        #
        # Now update the user's logical location and mode.
        # ------------------------------------------------------

        self._update_location_and_mode(
            intent=intent,
            previous_room=previous_room,
            previous_mode=previous_mode,
            results=results
        )

        # The move completed and every action was acknowledged, so the
        # room the Orchestrator just committed is now a fact.
        if is_movement:
            self.context.confirm_location(
                self.context.get_current_room()
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
    # LOCATION
    # ==========================================================

    def _destination_for(self, intent):
        """Where this intent intends to leave the person, if anywhere.

        Mirrors the commit rules in _update_location_and_mode. An
        intent that does not move the person returns None.
        """

        moves_to = {
            "STUDY_MODE": Room.STUDY_ROOM,
            "RELAX_MODE": Room.RELAX_ROOM,
            "PREPARE_FOR_SLEEP": Room.SLEEP_ROOM,
            "PREPARE_FOR_MEAL": Room.MEAL_ROOM,
            "MEDICATION": Room.SLEEP_ROOM,
            "LEAVE_ROOM": Room.OUTSIDE,
            "SHUTDOWN_ENVIRONMENT": Room.OUTSIDE,
        }

        if intent in moves_to:
            return moves_to[intent]

        if intent == "RETURN_TO_ROOM":
            return self.context.get_return_target()

        # WAKE_UP, EMERGENCY and EMERGENCY_CLEAR leave the person where
        # they are.
        return None

    def _observe_plan(self, intent, actions):
        """Announce the plan. A failing observer must not stop the
        workflow it is describing."""

        if self.plan_observer is None:
            return

        try:
            self.plan_observer(intent, list(actions))
        except Exception as error:
            print(f"[STATE] Could not announce plan: {error}")

    def _observe(self, intent, action, result):
        """Tell the observer an action was acknowledged and committed.

        Never allowed to break a workflow: a recording failure must not
        stop the house responding.
        """

        if self.action_observer is None:
            return

        try:
            self.action_observer(intent, action, result)
        except Exception as error:
            print(f"[STATE] Could not record action: {error}")

    def _abandon_transit(
        self,
        is_movement,
        doors_opened,
        previous_room,
        intent,
    ):
        """A movement workflow stopped part way. Say what is still true.

        If no door was opened the person cannot have left, so the
        source room is still honest. Once a door has opened they may be
        anywhere along the route, and the only truthful answer is that
        the system does not know.
        """

        if not is_movement:
            return

        if doors_opened:
            self.context.mark_location_unknown(
                reason=f"{intent} was interrupted after a door opened",
            )
            return

        self.context.confirm_location(
            previous_room,
            reason=None,
        )

    # ==========================================================
    # ACKNOWLEDGEMENT VALIDATION  (F5)
    # ==========================================================

    @staticmethod
    def _failure_result(action, error):

        return {
            "status": "error",
            "device": action.device_id,
            "action": action.action_type.value,
            "error": str(error),
        }

    @staticmethod
    def _is_acknowledged(result, action):
        """Is this a successful acknowledgement of THIS action?

        Logical state is only allowed to move when a device confirms
        it moved. A timeout, a rejection, a malformed reply, or a
        reply about some other device must all leave state alone.

        Transports correlate replies by command_id before they get
        here; this is the layer that refuses to trust the payload
        blindly.
        """

        if not isinstance(result, dict):
            return False

        if result.get("status") != "success":
            return False

        device = result.get("device")
        if device is not None and device != action.device_id:
            return False

        reported = result.get("action")
        if (
            reported is not None
            and reported != action.action_type.value
        ):
            return False

        return True

    @staticmethod
    def _all_acknowledged(results):
        return all(
            isinstance(result, dict)
            and result.get("status") == "success"
            for result in results
        )

    # ==========================================================
    # UPDATE LOCATION + MODE
    # ==========================================================

    def _update_location_and_mode(
        self,
        intent,
        previous_room,
        previous_mode,
        results=()
    ):

        # ------------------------------------------------------
        # EMERGENCY
        #
        # The mode was latched before execution began, and a failed
        # emergency action must never undo that. Nothing to do here.
        # ------------------------------------------------------

        if intent == "EMERGENCY":
            return

        # ------------------------------------------------------
        # EMERGENCY_CLEAR
        #
        # Recovery is only complete when every required safety
        # action was confirmed. If anything failed, the latch holds
        # and the user can retry: the clear workflow is state aware,
        # so a retry asks only for what is still outstanding.
        # ------------------------------------------------------

        if intent == "EMERGENCY_CLEAR":

            if self._all_acknowledged(results):

                self.context.set_mode(
                    Mode.NONE
                )

                self.context.clear_emergency()

            return

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

            # The room the user just left becomes the room to come back
            # to. OUTSIDE and DRAWING_ROOM are not returnable locations,
            # matching the guard the LEAVE_ROOM branch already uses.
            if (
                previous_room != destination
                and previous_room not in (
                    Room.OUTSIDE,
                    Room.DRAWING_ROOM
                )
            ):
                self.context.set_return_target(
                    previous_room
                )

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
            # They do NOT leave the room, so only the mode changes.
            #
            # Waking up anywhere else generates no actions, and a
            # workflow that did nothing must not mutate state.
            if previous_room == Room.SLEEP_ROOM:

                self.context.set_mode(
                    Mode.NONE
                )

            return


    # ==========================================================
    # APPLY SUCCESSFUL ACTION TO LOGICAL STATE
    # ==========================================================

    def _apply_successful_action(self, action):

        action_type = action.action_type
        device = action.device_id

        print(
            f"[STATE] Applying -> "
            f"{action_type.value} -> {device}"
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