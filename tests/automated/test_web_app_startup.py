"""Web application boot and the HTTP side of the intent decision contract.

Audit finding A1: create_app() constructed VoiceController with
margin_threshold and max_clarification_attempts, which the controller has not
accepted since the ambiguity API was retired. The application could not start
at all.

These tests are deliberately model-free. The application factory accepts an
injected controller so the HTTP contract can be exercised without loading
Whisper or a sentence-transformer, and the real boot settings are proven
API-compatible by signature binding rather than by construction.
"""

import ast
from pathlib import Path

import pytest

from app.web.server import DEFAULT_CONTROLLER_SETTINGS, create_app


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def voice_controller_parameters():
    """Parameter names of VoiceController.__init__, read from source.

    Parsed rather than imported: importing the controller pulls in Whisper
    and a sentence-transformer, and the default suite must stay model-free.
    The real signature is bound for comparison in the model-marked suite.
    """

    source = (PROJECT_ROOT / "app" / "voice" / "controller.py").read_text(
        encoding="utf-8"
    )

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "VoiceController":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    arguments = item.args
                    assert not arguments.kwarg, (
                        "VoiceController.__init__ accepts **kwargs, so this "
                        "check can no longer detect an unsupported option."
                    )
                    return {
                        argument.arg
                        for argument in arguments.args + arguments.kwonlyargs
                    } - {"self"}

    raise AssertionError("VoiceController.__init__ not found")


# ==============================================================
# STUB CONTROLLER
# ==============================================================


class StubRecorder:
    def __init__(self, audio_path="command.wav"):
        self.audio_path = audio_path
        self.started = 0

    def start_recording(self):
        self.started += 1

    def stop_recording(self, output_path):
        return self.audio_path


class StubTranscriber:
    def __init__(self, text="I want to sleep"):
        self.text = text

    def transcribe(self, audio_path):
        return self.text


class StubRecognizer:
    def __init__(self, result):
        self.result = result

    def predict(self, text):
        return dict(self.result)


class StubVoiceController:
    def __init__(self, result, text="I want to sleep", audio_path="command.wav"):
        self.recorder = StubRecorder(audio_path)
        self.transcriber = StubTranscriber(text)
        self.recognizer = StubRecognizer(result)


PREDICTED_RESULT = {
    "decision": "PREDICTED",
    "intent": "PREPARE_FOR_SLEEP",
    "similarity_score": 0.89,
    "matched_sentence": "I want to sleep",
    "top_results": [
        {"intent": "PREPARE_FOR_SLEEP", "score": 0.89},
        {"intent": "WAKE_UP", "score": 0.70},
        {"intent": "RELAX_MODE", "score": 0.63},
    ],
}


UNKNOWN_RESULT = {
    "decision": "UNKNOWN",
    "intent": None,
    "similarity_score": 0.37,
    "matched_sentence": "I want to sleep",
    "top_results": [
        {"intent": "PREPARE_FOR_SLEEP", "score": 0.37},
    ],
}


class NullExecutor:
    """Acknowledges without a transport, so no broker is contacted."""

    def execute(self, action):
        return {
            "status": "success",
            "device": action.device_id,
            "action": action.action_type.value,
        }


def offline_runtime():
    """A runtime with no MQTT client, for broker-free HTTP tests."""

    from app.runtime import ApplicationRuntime

    return ApplicationRuntime(device_executor=NullExecutor())


def client_for(result, **kwargs):
    controller = StubVoiceController(result, **kwargs)
    app = create_app(controller=controller, runtime=offline_runtime())
    app.config.update(TESTING=True)
    return app.test_client(), controller


def stop_after_start(client):
    client.post("/api/recording/start")
    return client.post("/api/recording/stop")


# ==============================================================
# A1 — THE BOOT CALL MATCHES THE CONTROLLER API
# ==============================================================


def test_default_controller_settings_match_the_voice_controller_api():
    # This is the exact regression that stopped the application booting:
    # the web layer passed options the controller had stopped accepting.
    accepted = voice_controller_parameters()

    unsupported = set(DEFAULT_CONTROLLER_SETTINGS) - accepted

    assert unsupported == set(), (
        f"create_app() would pass options VoiceController does not accept: "
        f"{sorted(unsupported)}"
    )


def test_default_controller_settings_carry_no_retired_ambiguity_options():
    assert "margin_threshold" not in DEFAULT_CONTROLLER_SETTINGS
    assert "max_clarification_attempts" not in DEFAULT_CONTROLLER_SETTINGS


def test_create_app_boots_and_registers_its_routes():
    app = create_app(
        controller=StubVoiceController(PREDICTED_RESULT),
        runtime=offline_runtime(),
    )

    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/" in rules
    assert "/api/recording/start" in rules
    assert "/api/recording/stop" in rules
    assert "/api/intent/confirm" in rules
    assert "/api/intent/cancel" in rules
    assert "/api/state" in rules


def test_dashboard_renders():
    client, _ = client_for(PREDICTED_RESULT)

    response = client.get("/")

    assert response.status_code == 200


# ==============================================================
# A3 — HTTP DECISION CONTRACT
# ==============================================================


def test_predicted_response_carries_the_intent_and_its_evidence():
    client, _ = client_for(PREDICTED_RESULT)

    response = stop_after_start(client)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["decision"] == "PREDICTED"
    assert payload["intent"] == "PREPARE_FOR_SLEEP"
    assert payload["transcription"] == "I want to sleep"

    # Evidence the confirmation step needs is preserved.
    assert payload["similarity_score"] == pytest.approx(0.89)
    assert payload["matched_sentence"] == "I want to sleep"
    assert len(payload["top_results"]) == 3

    assert payload["message"]


def test_unknown_response_reports_no_intent():
    client, _ = client_for(UNKNOWN_RESULT)

    response = stop_after_start(client)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["decision"] == "UNKNOWN"
    assert payload["intent"] is None
    assert payload["message"]


@pytest.mark.parametrize(
    "result",
    [PREDICTED_RESULT, UNKNOWN_RESULT],
    ids=["predicted", "unknown"],
)
def test_response_never_carries_retired_ambiguity_fields(result):
    client, _ = client_for(result)

    payload = stop_after_start(client).get_json()

    assert "margin" not in payload
    assert "clarification_attempts" not in payload
    assert "max_clarification_attempts" not in payload
    assert payload["decision"] in {"PREDICTED", "UNKNOWN"}


# ==============================================================
# RECORDING LIFECYCLE
# ==============================================================


def test_starting_twice_is_rejected():
    client, controller = client_for(PREDICTED_RESULT)

    assert client.post("/api/recording/start").status_code == 200
    assert client.post("/api/recording/start").status_code == 409

    assert controller.recorder.started == 1


def test_stopping_without_starting_is_rejected():
    client, _ = client_for(PREDICTED_RESULT)

    assert client.post("/api/recording/stop").status_code == 409


def test_no_captured_audio_is_reported_to_the_caller():
    client, _ = client_for(PREDICTED_RESULT, audio_path=None)

    response = stop_after_start(client)

    assert response.status_code == 422
    assert "error" in response.get_json()


def test_silent_recording_is_reported_to_the_caller():
    client, _ = client_for(PREDICTED_RESULT, text="   ")

    response = stop_after_start(client)

    assert response.status_code == 422
    assert "error" in response.get_json()


def test_a_failed_stop_releases_the_recording_lock():
    # A caller must be able to retry after a failure rather than being
    # wedged in the "already recording" state.
    client, _ = client_for(PREDICTED_RESULT, audio_path=None)

    assert stop_after_start(client).status_code == 422
    assert client.post("/api/recording/start").status_code == 200
