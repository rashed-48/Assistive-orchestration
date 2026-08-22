from app.orchestration.actions import Action, ActionType
from app.devices.json_protocol import JSONProtocol


# ======================================================
# SINGLE ACTION
# ======================================================

action = Action(
    ActionType.LIGHT_ON,
    "study_light"
)

print("\n" + "=" * 70)
print("SINGLE ACTION")
print("=" * 70)

print(JSONProtocol.action_to_json(action))


# ======================================================
# MULTIPLE ACTIONS
# ======================================================

actions = [
    Action(
        ActionType.LIGHT_OFF,
        "study_light"
    ),
    Action(
        ActionType.OPEN_DOOR,
        "study_door"
    ),
    Action(
        ActionType.CLOSE_DOOR,
        "study_door"
    ),
    Action(
        ActionType.LIGHT_ON,
        "relax_light"
    ),
    Action(
        ActionType.TV_ON,
        "relax_tv"
    ),
]

print("\n" + "=" * 70)
print("MULTIPLE ACTIONS")
print("=" * 70)

print(JSONProtocol.actions_to_json(actions))