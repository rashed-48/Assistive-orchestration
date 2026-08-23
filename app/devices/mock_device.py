import warnings

from app.orchestration.actions import ActionType


class MockDeviceExecutor:
    """Deterministic action executor for tests and manual simulations.

    The mock executor simulates physical action success. It intentionally does
    not update ContextManager or commit workflow-level room/mode state; that is
    owned by Orchestrator.
    """

    def __init__(self, context=None):
        self.context = context
        self.actions = []
        self.device_states = {}

    # ==================================================
    # COMPATIBILITY WORKFLOW HELPER
    # ==================================================

    def execute_workflow(self, actions, *_, **__):
        """Execute actions sequentially without logical workflow authority.

        This helper is retained for manual transport-style scripts only.
        Complete workflows should be executed through Orchestrator.execute_intent().
        """

        warnings.warn(
            "MockDeviceExecutor.execute_workflow() is non-authoritative; "
            "use Orchestrator.execute_intent() for logical workflow execution.",
            DeprecationWarning,
            stacklevel=2,
        )

        results = []

        for action in actions:
            results.append(self.execute(action))

        return results

    # ==================================================
    # SINGLE ACTION EXECUTION
    # ==================================================

    def execute(self, action):
        print(
            f"[DEVICE] "
            f"{action.action_type.value:<20}"
            f"{action.device_id}"
        )

        action_type = action.action_type
        device = action.device_id

        if action_type == ActionType.LIGHT_ON:
            self._record(device, "ON")

        elif action_type == ActionType.LIGHT_OFF:
            self._record(device, "OFF")

        elif action_type == ActionType.OPEN_DOOR:
            self._record(device, "OPEN")

        elif action_type == ActionType.CLOSE_DOOR:
            self._record(device, "CLOSED")

        elif action_type == ActionType.PREPARE_TABLE:
            self._record(device, "READY")

        elif action_type == ActionType.RESET_TABLE:
            self._record(device, "NORMAL")

        elif action_type == ActionType.PREPARE_BED:
            self._record(device, "READY")

        elif action_type == ActionType.RESET_BED:
            self._record(device, "NORMAL")

        elif action_type == ActionType.TV_ON:
            self._record(device, "ON")

        elif action_type == ActionType.TV_OFF:
            self._record(device, "OFF")

        elif action_type == ActionType.ACTIVATE_MEDICATION:
            self._record(device, "ON")

        elif action_type == ActionType.BUZZER_ON:
            self._record(device, "ON")

        elif action_type == ActionType.BUZZER_OFF:
            self._record(device, "OFF")

        else:
            raise ValueError(
                f"Unsupported action: {action.action_type}"
            )

        self.actions.append(action)

        return {
            "status": "success",
            "device": action.device_id,
            "action": action.action_type.value,
            "parameters": action.parameters,
        }

    def _record(self, device_id, state):
        self.device_states[device_id] = state
