import warnings

import requests

from app.orchestration.actions import Action
from app.devices.json_protocol import JSONProtocol


class ESP32DeviceExecutor:

    def __init__(self, esp32_url: str):
        self.esp32_url = esp32_url.rstrip("/")

    def execute(self, action: Action):

        payload = JSONProtocol.action_to_dict(action)

        response = requests.post(
            f"{self.esp32_url}/command",
            json=payload,
            timeout=5
        )

        response.raise_for_status()

        return response.json()

    def execute_workflow(self, actions):
        """Execute actions sequentially without logical workflow authority.

        This compatibility helper performs HTTP transport execution only. Use
        Orchestrator.execute_intent() for authoritative workflow execution and
        ContextManager state synchronization.
        """

        warnings.warn(
            "ESP32DeviceExecutor.execute_workflow() is non-authoritative; "
            "use Orchestrator.execute_intent() for logical workflow execution.",
            DeprecationWarning,
            stacklevel=2,
        )

        results = []

        for action in actions:

            result = self.execute(action)

            results.append(result)

        return results
