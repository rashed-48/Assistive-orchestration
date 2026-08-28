from datetime import datetime, timezone

from app.orchestration.state import (
    EnvironmentState,
    LocationStatus,
    MealRoomState,
    RelaxRoomState,
    Room,
    Mode,
    DoorState,
    PowerState,
    PreparationState,
    SleepRoomState,
    StudyRoomState,
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class StateRestoreError(Exception):
    """Persisted state could not be understood, so none of it was applied."""


def _enum(kind, value, field):
    """Convert a stored value back to its enum member, or refuse."""

    if value is None:
        raise StateRestoreError(f"{field} is missing")

    try:
        return kind(value)
    except ValueError:
        raise StateRestoreError(
            f"{field} has the unrecognised value {value!r}; "
            f"expected one of {[member.value for member in kind]}"
        )


def _optional_enum(kind, value, field):
    if value is None:
        return None

    return _enum(kind, value, field)


def _optional_text(value, field):
    if value is None or isinstance(value, str):
        return value

    raise StateRestoreError(f"{field} should be text, got {type(value).__name__}")


def _section(data, name):
    rooms = data.get("rooms")

    if not isinstance(rooms, dict):
        raise StateRestoreError("rooms is missing")

    section = rooms.get(name)

    if not isinstance(section, dict):
        raise StateRestoreError(f"rooms.{name} is missing")

    return section


class ContextManager:

    def __init__(self):
        self.state = EnvironmentState()

    def get_state(self) -> EnvironmentState:
        return self.state

    def get_current_room(self) -> Room:
        return self.state.current_room

    def get_return_target(self):
        return self.state.return_target

    def get_current_mode(self) -> Mode:
        return self.state.current_mode

    def set_current_room(self, room: Room):
        self.state.current_room = room

    # ==========================================================
    # LOCATION CERTAINTY
    #
    # current_room says where the person was last committed to be.
    # These say how much that is worth. Every caller that plans
    # movement must consult the status, not just the room.
    # ==========================================================

    def get_location_status(self) -> LocationStatus:
        return self.state.location_status

    def get_location_destination(self):
        return self.state.location_destination

    def get_location_reason(self):
        return self.state.location_reason

    def location_is_known(self) -> bool:
        return self.state.location_status == LocationStatus.KNOWN

    def begin_transit(self, destination: Room, reason=None):
        """A movement workflow has started and has not yet arrived.

        current_room is deliberately left at the source: nothing has
        been confirmed, so nothing may be claimed.
        """

        self.state.location_status = LocationStatus.IN_TRANSIT
        self.state.location_destination = destination
        self.state.location_reason = reason

    def confirm_location(self, room: Room, reason=None):
        """Commit a location as known.

        Called by the Orchestrator when a movement workflow completes,
        and by an operator resolving an unknown location by hand.
        """

        self.state.current_room = room
        self.state.location_status = LocationStatus.KNOWN
        self.state.location_destination = None
        self.state.location_reason = reason

    def mark_location_unknown(self, reason=None):
        """The person may have moved and the system cannot say where.

        current_room is left holding the last known room so the reason
        and the history survive, but the status withdraws the claim.
        """

        self.state.location_status = LocationStatus.UNKNOWN
        self.state.location_destination = None
        self.state.location_reason = reason

    # ==========================================================
    # EMERGENCY LIFECYCLE
    #
    # current_mode is the runtime latch. These record how it got
    # there, so a restart can restore the latch from evidence rather
    # than from a mode value that a fresh object would reset.
    # ==========================================================

    def declare_emergency(self, at=None):
        self.state.emergency_declared_at = at or _utc_now()
        self.state.emergency_cleared_at = None

    def clear_emergency(self, at=None):
        if self.state.emergency_declared_at is not None:
            self.state.emergency_cleared_at = at or _utc_now()

    def emergency_latched(self) -> bool:
        """Declared, and not since cleared."""

        return (
            self.state.emergency_declared_at is not None
            and self.state.emergency_cleared_at is None
        )

    def set_return_target(self, room):
        self.state.return_target = room

    def clear_return_target(self):
        self.state.return_target = None

    def set_mode(self, mode: Mode):
        self.state.current_mode = mode

    def set_drawing_light(self, state: PowerState):
        self.state.drawing_light = state

    def set_exit_door(self, state: DoorState):
        self.state.exit_door = state

    def set_buzzer(self, state: PowerState):
        self.state.buzzer = state

    def set_device_state(
        self,
        room: Room,
        device: str,
        value
    ):
        if room == Room.STUDY_ROOM:
            setattr(self.state.study, device, value)

        elif room == Room.RELAX_ROOM:
            setattr(self.state.relax, device, value)

        elif room == Room.SLEEP_ROOM:
            setattr(self.state.sleep, device, value)

        elif room == Room.MEAL_ROOM:
            setattr(self.state.meal, device, value)

    def to_dict(self) -> dict:
        """Serialize the authoritative logical state for presentation.

        This is a view of EnvironmentState, not a second state model. Any
        interface that shows state renders this.
        """

        state = self.state

        return {
            "current_room": state.current_room.value,
            "location_status": state.location_status.value,
            "location_destination": (
                state.location_destination.value
                if state.location_destination
                else None
            ),
            "location_reason": state.location_reason,
            "return_target": (
                state.return_target.value
                if state.return_target
                else None
            ),
            "current_mode": state.current_mode.value,
            "emergency_declared_at": state.emergency_declared_at,
            "emergency_cleared_at": state.emergency_cleared_at,
            "drawing_light": state.drawing_light.value,
            "exit_door": state.exit_door.value,
            "buzzer": state.buzzer.value,
            "rooms": {
                "study": {
                    "door": state.study.door.value,
                    "light": state.study.light.value,
                    "table": state.study.table.value,
                },
                "relax": {
                    "door": state.relax.door.value,
                    "light": state.relax.light.value,
                    "tv": state.relax.tv.value,
                },
                "sleep": {
                    "door": state.sleep.door.value,
                    "light": state.sleep.light.value,
                    "bed": state.sleep.bed.value,
                    "medication_servo": (
                        state.sleep.medication_servo.value
                    ),
                },
                "meal": {
                    "door": state.meal.door.value,
                    "light": state.meal.light.value,
                    "table": state.meal.table.value,
                },
            },
        }

    def restore_from(self, data: dict):
        """Rebuild the whole state from a to_dict() document.

        All or nothing. Every field is parsed into a fresh
        EnvironmentState first, and only a completely valid result is
        adopted; anything unrecognised raises and leaves the live state
        untouched. A half-restored world is worse than a fresh one,
        because it looks trustworthy.
        """

        if not isinstance(data, dict):
            raise StateRestoreError("state must be a JSON object")

        study = _section(data, "study")
        relax = _section(data, "relax")
        sleep = _section(data, "sleep")
        meal = _section(data, "meal")

        restored = EnvironmentState(
            current_room=_enum(Room, data.get("current_room"), "current_room"),
            location_status=_enum(
                LocationStatus,
                data.get("location_status"),
                "location_status",
            ),
            location_destination=_optional_enum(
                Room,
                data.get("location_destination"),
                "location_destination",
            ),
            location_reason=_optional_text(
                data.get("location_reason"), "location_reason"
            ),
            return_target=_optional_enum(
                Room, data.get("return_target"), "return_target"
            ),
            current_mode=_enum(Mode, data.get("current_mode"), "current_mode"),
            emergency_declared_at=_optional_text(
                data.get("emergency_declared_at"), "emergency_declared_at"
            ),
            emergency_cleared_at=_optional_text(
                data.get("emergency_cleared_at"), "emergency_cleared_at"
            ),
            drawing_light=_enum(
                PowerState, data.get("drawing_light"), "drawing_light"
            ),
            exit_door=_enum(DoorState, data.get("exit_door"), "exit_door"),
            buzzer=_enum(PowerState, data.get("buzzer"), "buzzer"),
            study=StudyRoomState(
                door=_enum(DoorState, study.get("door"), "study.door"),
                light=_enum(PowerState, study.get("light"), "study.light"),
                table=_enum(
                    PreparationState, study.get("table"), "study.table"
                ),
            ),
            relax=RelaxRoomState(
                door=_enum(DoorState, relax.get("door"), "relax.door"),
                light=_enum(PowerState, relax.get("light"), "relax.light"),
                tv=_enum(PowerState, relax.get("tv"), "relax.tv"),
            ),
            sleep=SleepRoomState(
                door=_enum(DoorState, sleep.get("door"), "sleep.door"),
                light=_enum(PowerState, sleep.get("light"), "sleep.light"),
                bed=_enum(PreparationState, sleep.get("bed"), "sleep.bed"),
                medication_servo=_enum(
                    PowerState,
                    sleep.get("medication_servo"),
                    "sleep.medication_servo",
                ),
            ),
            meal=MealRoomState(
                door=_enum(DoorState, meal.get("door"), "meal.door"),
                light=_enum(PowerState, meal.get("light"), "meal.light"),
                table=_enum(PreparationState, meal.get("table"), "meal.table"),
            ),
        )

        # Everything parsed. Adopt it in one step.
        self.state = restored

        return self.state

    def print_state(self):
        print("\n" + "=" * 60)
        print("ENVIRONMENT STATE")
        print("=" * 60)

        print(f"Current Room : {self.state.current_room.value}")

        if self.state.location_status != LocationStatus.KNOWN:
            heading = (
                f" -> {self.state.location_destination.value}"
                if self.state.location_destination
                else ""
            )
            print(
                f"Location     : {self.state.location_status.value}"
                f"{heading}"
                f"  ({self.state.location_reason or 'no reason recorded'})"
            )
        return_target = (
            self.state.return_target.value
            if self.state.return_target
            else "NONE"
        )

        print(f"Return Target: {return_target}")
        print(f"Current Mode : {self.state.current_mode.value}")

        print(
            f"Drawing Light: "
            f"{self.state.drawing_light.value}"
        )

        print(
            f"Exit Door: "
            f"{self.state.exit_door.value}"
        )

        print(
            f"Buzzer: "
            f"{self.state.buzzer.value}"
        )

        print("\nStudy:")
        print(f"  Door : {self.state.study.door.value}")
        print(f"  Light: {self.state.study.light.value}")
        print(f"  Table: {self.state.study.table.value}")

        print("\nRelax:")
        print(f"  Door : {self.state.relax.door.value}")
        print(f"  Light: {self.state.relax.light.value}")
        print(f"  TV   : {self.state.relax.tv.value}")

        print("\nSleep:")
        print(f"  Door : {self.state.sleep.door.value}")
        print(f"  Light: {self.state.sleep.light.value}")
        print(f"  Bed  : {self.state.sleep.bed.value}")
        print(
            f"  Medication: "
            f"{self.state.sleep.medication_servo.value}"
        )

        print("\nMeal:")
        print(f"  Door : {self.state.meal.door.value}")
        print(f"  Light: {self.state.meal.light.value}")
        print(f"  Table: {self.state.meal.table.value}")

        print("=" * 60)