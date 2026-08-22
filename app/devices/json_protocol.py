import json

from app.orchestration.actions import Action


class JSONProtocol:

    @staticmethod
    def action_to_dict(action: Action) -> dict:

        return {
            "device": action.device_id,
            "action": action.action_type.value,
            "parameters": action.parameters,
        }

    @staticmethod
    def action_to_json(action: Action) -> str:

        return json.dumps(
            JSONProtocol.action_to_dict(action)
        )

    @staticmethod
    def actions_to_dict(actions: list[Action]) -> list[dict]:

        return [
            JSONProtocol.action_to_dict(action)
            for action in actions
        ]

    @staticmethod
    def actions_to_json(actions: list[Action]) -> str:

        return json.dumps(
            JSONProtocol.actions_to_dict(actions)
        )