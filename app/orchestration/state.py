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
    current_room: Room = Room.OUTSIDE
    return_target: Optional[Room] = None
    current_mode: Mode = Mode.NONE

    drawing_light: PowerState = PowerState.OFF

    study: StudyRoomState = field(default_factory=StudyRoomState)
    relax: RelaxRoomState = field(default_factory=RelaxRoomState)
    sleep: SleepRoomState = field(default_factory=SleepRoomState)
    meal: MealRoomState = field(default_factory=MealRoomState)

    exit_door: DoorState = DoorState.CLOSED
    buzzer: PowerState = PowerState.OFF