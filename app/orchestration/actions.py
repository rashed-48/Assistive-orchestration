from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List


class ActionType(str, Enum):
    OPEN_DOOR = "OPEN_DOOR"
    CLOSE_DOOR = "CLOSE_DOOR"

    LIGHT_ON = "LIGHT_ON"
    LIGHT_OFF = "LIGHT_OFF"

    TV_ON = "TV_ON"
    TV_OFF = "TV_OFF"

    PREPARE_TABLE = "PREPARE_TABLE"
    RESET_TABLE = "RESET_TABLE"

    PREPARE_BED = "PREPARE_BED"
    RESET_BED = "RESET_BED"

    ACTIVATE_MEDICATION = "ACTIVATE_MEDICATION"

    BUZZER_ON = "BUZZER_ON"
    BUZZER_OFF = "BUZZER_OFF"


@dataclass
class Action:
    action_type: ActionType
    device_id: str
    parameters: dict[str, Any] = field(default_factory=dict)

    depends_on: List[int] = field(default_factory=list)

    priority: int = 0