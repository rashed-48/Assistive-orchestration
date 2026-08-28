from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Room(str, Enum):
    OUTSIDE = "OUTSIDE"
    DRAWING_ROOM = "DRAWING_ROOM"
    STUDY_ROOM = "STUDY_ROOM"
    RELAX_ROOM = "RELAX_ROOM"
    SLEEP_ROOM = "SLEEP_ROOM"
    MEAL_ROOM = "MEAL_ROOM"


class LocationStatus(str, Enum):
    """How much the system actually knows about where the person is.

    Deliberately NOT members of Room. Room is used as a dictionary key
    in the transition tables and is pattern-matched by long if/elif
    chains that have no fallback branch, so an "UNKNOWN room" would be
    silently unroutable rather than loudly rejected. Uncertainty is a
    property *of* the location reading, not a place someone can be.
    """

    # current_room is a committed fact: the last movement workflow
    # completed and every action in it was acknowledged.
    KNOWN = "KNOWN"

    # A movement workflow is running. current_room still holds the
    # source room; the destination is not committed yet.
    IN_TRANSIT = "IN_TRANSIT"

    # The system cannot say where the person is. current_room holds the
    # last place they were known to be, which must not be treated as
    # their present location.
    UNKNOWN = "UNKNOWN"


class Mode(str, Enum):
    NONE = "NONE"
    STUDY = "STUDY"
    RELAX = "RELAX"
    SLEEP = "SLEEP"
    MEAL = "MEAL"
    EMERGENCY = "EMERGENCY"


class DoorState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PowerState(str, Enum):
    ON = "ON"
    OFF = "OFF"


class PreparationState(str, Enum):
    READY = "READY"
    NORMAL = "NORMAL"


@dataclass
class RoomState:
    door: DoorState = DoorState.CLOSED
    light: PowerState = PowerState.OFF


@dataclass
class StudyRoomState(RoomState):
    table: PreparationState = PreparationState.NORMAL


@dataclass
class RelaxRoomState(RoomState):
    tv: PowerState = PowerState.OFF


@dataclass
class SleepRoomState(RoomState):
    bed: PreparationState = PreparationState.NORMAL
    medication_servo: PowerState = PowerState.OFF


@dataclass
class MealRoomState(RoomState):
    table: PreparationState = PreparationState.NORMAL


@dataclass
class EnvironmentState:
    # The last committed location. Only a present-tense claim about the
    # person while location_status is KNOWN.
    current_room: Room = Room.OUTSIDE

    location_status: LocationStatus = LocationStatus.KNOWN

    # Where a movement workflow is heading. Set only while IN_TRANSIT,
    # so an interrupted move records both ends of the journey.
    location_destination: Optional[Room] = None

    # Why the location is not KNOWN, for the operator and for the
    # future persistence layer to report on restart.
    location_reason: Optional[str] = None

    return_target: Optional[Room] = None
    current_mode: Mode = Mode.NONE

    # Explicit emergency lifecycle, so a restart can tell "an emergency
    # was declared and never cleared" from "the mode happens to read
    # EMERGENCY". current_mode is the runtime latch; these two are the
    # durable record of how it got there.
    emergency_declared_at: Optional[str] = None
    emergency_cleared_at: Optional[str] = None

    drawing_light: PowerState = PowerState.OFF

    study: StudyRoomState = field(default_factory=StudyRoomState)
    relax: RelaxRoomState = field(default_factory=RelaxRoomState)
    sleep: SleepRoomState = field(default_factory=SleepRoomState)
    meal: MealRoomState = field(default_factory=MealRoomState)

    exit_door: DoorState = DoorState.CLOSED
    buzzer: PowerState = PowerState.OFF