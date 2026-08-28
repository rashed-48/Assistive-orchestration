"""Web prediction -> confirmation -> Orchestrator.

Objectives A, B, C, D. These tests use a real ApplicationRuntime with a real
ContextManager, Orchestrator and WorkflowEngine, and inject only the device
executor. So the whole convergence path is genuinely exercised; only the
transport is a double. The MQTT transport itself is covered end to end
against a live broker in test_mqtt_end_to_end.py.
"""

import pytest

from app.orchestration.state import Mode, PowerState, Room
from app.runtime import ApplicationRuntime
from app.web.server import create_app

from tests.automated.support import quiet
from tests.automated.test_web_app_startup import (
    PREDICTED_RESULT,
    UNKNOWN_RESULT,
    StubVoiceController,
)


class RecordingExecutor:
    """Stands in for MQTTDeviceExecutor. Records and acknowledges."""

    def __init__(self, fail_at=None):
        self.actions = []
        self.fail_at = fail_at

    def execute(self, action):
        self.actions.append(action)

        if self.fail_at is not None and len(self.actions) == self.fail_at:
            raise RuntimeError(
                f"Injected device failure at action {self.fail_at}"
            )

        return {
            "status": "success",
            "device": action.device_id,
            "action": action.action_type.value,
            "node": "test_node",
        }


def build(result=PREDICTED_RESULT, fail_at=None, room=Room.RELAX_ROOM, mode=Mode.RELAX):
    executor = RecordingExecutor(fail_at=fail_at)
    runtime = ApplicationRuntime(device_executor=executor)

    runtime.context.set_current_room(room)
    runtime.context.set_mode(mode)

    app = create_app(
        controller=StubVoiceController(result),
        runtime=runtime,
    )
    app.config.update(TESTING=True)

    return app.test_client(), runtime, executor


def predict(client):
    client.post("/api/recording/start")
    return client.post("/api/recording/stop")


# ==============================================================
# PREDICTION SETS UP A CONFIRMATION
# ==============================================================


def test_prediction_marks_the_intent_as_awaiting_confirmation():
    client, runtime, executor = build()

    payload = predict(client).get_json()

    assert payload["decision"] == "PREDICTED"
    assert payload["intent"] == "PREPARE_FOR_SLEEP"
    assert payload["executable"] is True

    assert runtime.get_pending_intent() == "PREPARE_FOR_SLEEP"

    # Prediction alone must never actuate anything.
    assert executor.actions == []


def test_unknown_never_arms_a_confirmation():
    client, runtime, executor = build(result=UNKNOWN_RESULT)

    payload = predict(client).get_json()

    assert payload["decision"] == "UNKNOWN"
    assert payload["executable"] is False

    assert runtime.get_pending_intent() is None
    assert executor.actions == []


def test_unknown_cannot_be_executed():
    client, _, executor = build(result=UNKNOWN_RESULT)

    predict(client)
    response = client.post("/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"})

    assert response.status_code == 409
    assert executor.actions == []


# ==============================================================
# CONFIRMATION REACHES THE ORCHESTRATOR
# ==============================================================


def test_confirmation_executes_the_workflow_and_commits_state():
    client, runtime, executor = build()

    predict(client)
    response = client.post(
        "/api/intent/confirm",
        json={"intent": "PREPARE_FOR_SLEEP"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "executed"
    assert payload["intent"] == "PREPARE_FOR_SLEEP"

    # The plan came from WorkflowEngine, not from the web layer.
    assert payload["executed_actions"] == len(executor.actions)
    assert payload["executed_actions"] > 0

    # Authoritative state was committed by the Orchestrator.
    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_current_mode() == Mode.SLEEP

    assert payload["state"]["environment"]["current_room"] == "SLEEP_ROOM"
    assert payload["state"]["environment"]["current_mode"] == "SLEEP"

    # The confirmation is spent.
    assert runtime.get_pending_intent() is None


def test_the_same_confirmation_cannot_be_replayed():
    client, _, executor = build()

    predict(client)
    assert client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    ).status_code == 200

    executed_once = len(executor.actions)

    replay = client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    )

    assert replay.status_code == 409
    assert len(executor.actions) == executed_once


def test_confirming_a_different_intent_than_predicted_is_refused():
    client, _, executor = build()

    predict(client)
    response = client.post("/api/intent/confirm", json={"intent": "EMERGENCY"})

    assert response.status_code == 409
    assert executor.actions == []


def test_confirming_without_a_prediction_is_refused():
    client, _, executor = build()

    response = client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    )

    assert response.status_code == 409
    assert executor.actions == []


def test_confirm_requires_an_intent():
    client, _, _ = build()

    predict(client)

    assert client.post("/api/intent/confirm", json={}).status_code == 400


def test_cancel_disarms_the_confirmation():
    client, runtime, executor = build()

    predict(client)
    assert runtime.get_pending_intent() == "PREPARE_FOR_SLEEP"

    assert client.post("/api/intent/cancel").status_code == 200

    assert runtime.get_pending_intent() is None

    assert client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    ).status_code == 409
    assert executor.actions == []


# ==============================================================
# FAILURE REPORTING
# ==============================================================


def test_workflow_failure_is_reported_and_state_stays_uncommitted():
    client, runtime, executor = build(fail_at=6)

    predict(client)
    response = client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    )
    payload = response.get_json()

    assert response.status_code == 502
    assert payload["status"] == "failed"
    assert "Injected device failure" in payload["error"]

    # Orchestrator left room and mode where they were.
    assert runtime.context.get_current_room() == Room.RELAX_ROOM
    assert runtime.context.get_current_mode() == Mode.RELAX
    assert payload["state"]["environment"]["current_room"] == "RELAX_ROOM"


# ==============================================================
# APPLICATION-SCOPED RUNTIME
# ==============================================================


def test_state_persists_across_requests_so_planning_stays_state_aware():
    client, runtime, executor = build(room=Room.STUDY_ROOM, mode=Mode.STUDY)

    predict(client)
    client.post("/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"})

    assert runtime.context.get_current_room() == Room.SLEEP_ROOM
    assert runtime.context.get_return_target() == Room.STUDY_ROOM

    first_command_actions = len(executor.actions)

    # A second identical command now plans against the committed state.
    # The user is already in the sleep room, so no transition is needed.
    predict(client)
    second = client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    ).get_json()

    assert second["status"] == "executed"
    assert second["executed_actions"] < first_command_actions


def test_state_endpoint_reports_the_authoritative_environment():
    client, runtime, _ = build()

    runtime.context.state.sleep.light = PowerState.ON

    payload = client.get("/api/state").get_json()

    assert payload["environment"]["current_room"] == "RELAX_ROOM"
    assert payload["environment"]["rooms"]["sleep"]["light"] == "ON"
    assert "PREPARE_FOR_SLEEP" in payload["supported_intents"]
    assert "mqtt" in payload


def test_runtime_rejects_an_unsupported_intent():
    from app.runtime import IntentNotSupported

    _, runtime, executor = build()

    with pytest.raises(IntentNotSupported):
        runtime.execute_intent("MAKE_COFFEE")

    assert executor.actions == []


def test_web_layer_holds_no_planner_or_executor_of_its_own():
    """Architectural rules 6 and 7.

    The web module must reach devices only through the runtime's
    Orchestrator.
    """

    import ast
    from pathlib import Path

    source = Path("app/web/server.py").read_text(encoding="utf-8")
    names = {
        node.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name)
    } | {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
    }

    assert "WorkflowEngine" not in names
    assert "MQTTDeviceExecutor" not in names
    assert "create_sleep_workflow" not in names


# ==============================================================
# EMERGENCY LATCH THROUGH THE WEB INTERFACE
# ==============================================================


EMERGENCY_RESULT = dict(
    PREDICTED_RESULT,
    intent="EMERGENCY",
    matched_sentence="This is an emergency",
)

EMERGENCY_CLEAR_RESULT = dict(
    PREDICTED_RESULT,
    intent="EMERGENCY_CLEAR",
    matched_sentence="The emergency is over",
)


def test_emergency_can_be_confirmed_and_latches():
    client, runtime, executor = build(result=EMERGENCY_RESULT)

    predict(client)
    payload = client.post(
        "/api/intent/confirm", json={"intent": "EMERGENCY"}
    ).get_json()

    assert payload["status"] == "executed"
    assert payload["state"]["environment"]["current_mode"] == "EMERGENCY"
    assert payload["state"]["emergency_active"] is True
    assert runtime.emergency_active()


def test_a_normal_command_is_not_offered_during_emergency():
    client, runtime, executor = build(result=EMERGENCY_RESULT)

    predict(client)
    client.post("/api/intent/confirm", json={"intent": "EMERGENCY"})

    # Now a normal command is predicted.
    controller = StubVoiceController(PREDICTED_RESULT)
    runtime_app = create_app(controller=controller, runtime=runtime)
    runtime_app.config.update(TESTING=True)
    blocked_client = runtime_app.test_client()

    payload = predict(blocked_client).get_json()

    assert payload["decision"] == "PREDICTED"
    assert payload["executable"] is False
    assert "emergency" in payload["message"].lower()

    # Nothing is armed, so nothing can be confirmed.
    assert runtime.get_pending_intent() is None


def test_a_normal_command_is_refused_at_the_confirm_endpoint():
    client, runtime, executor = build(result=PREDICTED_RESULT)

    # Arm a normal intent first, then declare an emergency underneath it.
    predict(client)
    assert runtime.get_pending_intent() == "PREPARE_FOR_SLEEP"

    with quiet():
        runtime.execute_intent("EMERGENCY")

    actions_before = len(executor.actions)

    response = client.post(
        "/api/intent/confirm", json={"intent": "PREPARE_FOR_SLEEP"}
    )
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["status"] == "blocked"
    assert "emergency" in payload["error"].lower()

    # The blocked workflow sent nothing.
    assert len(executor.actions) == actions_before
    assert runtime.emergency_active()


def test_emergency_clear_through_the_web_returns_to_normal():
    client, runtime, executor = build(result=EMERGENCY_CLEAR_RESULT)

    with quiet():
        runtime.execute_intent("EMERGENCY")
    assert runtime.emergency_active()

    predict(client)
    payload = client.post(
        "/api/intent/confirm", json={"intent": "EMERGENCY_CLEAR"}
    ).get_json()

    assert payload["status"] == "executed"
    assert payload["degraded"] is False
    assert payload["state"]["environment"]["current_mode"] == "NONE"
    assert payload["state"]["environment"]["buzzer"] == "OFF"
    assert payload["state"]["environment"]["exit_door"] == "CLOSED"
    assert runtime.emergency_active() is False


def test_emergency_clear_is_not_offered_when_there_is_no_emergency():
    client, runtime, _ = build(result=EMERGENCY_CLEAR_RESULT)

    payload = predict(client).get_json()

    assert payload["executable"] is False
    assert "no active emergency" in payload["message"].lower()
    assert runtime.get_pending_intent() is None


def test_a_degraded_emergency_is_reported_as_degraded():
    client, runtime, executor = build(result=EMERGENCY_RESULT, fail_at=1)

    predict(client)
    payload = client.post(
        "/api/intent/confirm", json={"intent": "EMERGENCY"}
    ).get_json()

    # Best effort: the call completed, but not cleanly.
    assert payload["status"] == "degraded"
    assert payload["degraded"] is True
    assert payload["failed_actions"] >= 1

    # And the emergency latched anyway.
    assert payload["state"]["environment"]["current_mode"] == "EMERGENCY"
