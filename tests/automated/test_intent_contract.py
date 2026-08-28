"""The intent decision contract, against the real recognition model.

Audit finding A3: the project once used a three-state, margin-gated decision
vocabulary (ACCEPTED / AMBIGUOUS / UNKNOWN). That was retired in favour of
"predict the best supported intent, then ask the user to confirm it". The
recognizer already implements the new contract; these tests pin it.

The retired margin rule required a 0.20 gap between the best and second-best
intent. "I want to sleep" scores a 0.193 gap, so that rule would have refused
to predict one of the system's core commands. Objective A3 states this must
not happen: a close runner-up must never suppress a confident best match.

These tests load a sentence-transformer, so they carry the "model" marker and
are excluded from the default suite. Run them with:

    .\\.venv\\Scripts\\python.exe -m pytest -m model
"""

import pytest


pytestmark = pytest.mark.model


DECISION_VOCABULARY = {"PREDICTED", "UNKNOWN"}


def load_sentences(name):
    import pandas as pd

    return pd.read_csv(f"data/{name}.csv")["sentence"].dropna().tolist()


@pytest.fixture(scope="module")
def recognizer():
    # Imported here, not at module scope, so the default suite does not pay
    # for torch and sentence-transformers just to deselect these tests.
    from app.intent.recognizer import IntentRecognizer

    # Module scoped: the model is loaded once for the whole file.
    return IntentRecognizer("data/intents.csv")


# ==============================================================
# REQUIRED SENTENCES
# ==============================================================


SUPPORTED_SENTENCES = [
    ("I want to sleep", "PREPARE_FOR_SLEEP"),
    ("I need my medicine", "MEDICATION"),
    ("I have some studying to do", "STUDY_MODE"),
]


@pytest.mark.parametrize(
    "sentence,expected_intent",
    SUPPORTED_SENTENCES,
    ids=[intent for _, intent in SUPPORTED_SENTENCES],
)
def test_supported_commands_are_predicted(recognizer, sentence, expected_intent):
    result = recognizer.predict(sentence)

    assert result["decision"] == "PREDICTED"
    assert result["intent"] == expected_intent


UNSUPPORTED_SENTENCES = [
    "Tell me a joke",
    "What is the weather today",
    "How many kilometres to the moon",
]


@pytest.mark.parametrize("sentence", UNSUPPORTED_SENTENCES)
def test_unsupported_input_is_unknown_with_no_intent(recognizer, sentence):
    result = recognizer.predict(sentence)

    assert result["decision"] == "UNKNOWN"
    assert result["intent"] is None


# ==============================================================
# A CLOSE RUNNER-UP MUST NOT SUPPRESS THE PREDICTION
# ==============================================================


def test_a_close_second_intent_does_not_block_the_best_match(recognizer):
    result = recognizer.predict("I want to sleep")

    assert result["decision"] == "PREDICTED"
    assert result["intent"] == "PREPARE_FOR_SLEEP"

    scores = [item["score"] for item in result["top_results"]]
    gap = scores[0] - scores[1]

    # The whole point of this test: this phrase does not clear the 0.20
    # gap the retired margin rule demanded, and must be predicted anyway.
    assert gap < 0.20, (
        "This sentence no longer has a close runner-up, so it no longer "
        "guards against the margin rule returning. Pick a closer pair."
    )

    # The runner-up is visible to the user without changing the decision.
    runner_up = {item["intent"] for item in result["top_results"][1:]}
    assert runner_up


def test_deliberately_ambiguous_phrases_never_produce_a_third_decision(recognizer):
    # ambiguous.csv is the research set the retired margin rule was tuned
    # against. Not one of these phrases may yield an AMBIGUOUS decision.
    sentences = load_sentences("ambiguous")

    assert sentences

    decisions = {
        recognizer.predict(sentence)["decision"]
        for sentence in sentences
    }

    assert decisions <= DECISION_VOCABULARY


def test_decision_vocabulary_is_exactly_predicted_or_unknown(recognizer):
    sentences = [sentence for sentence, _ in SUPPORTED_SENTENCES]
    sentences += UNSUPPORTED_SENTENCES
    sentences += load_sentences("unknown")

    decisions = {
        recognizer.predict(sentence)["decision"]
        for sentence in sentences
    }

    assert decisions <= DECISION_VOCABULARY


# ==============================================================
# RESULT SHAPE
# ==============================================================


def test_result_keeps_the_evidence_the_confirmation_step_needs(recognizer):
    result = recognizer.predict("I want to sleep")

    assert set(result) == {
        "decision",
        "intent",
        "similarity_score",
        "matched_sentence",
        "top_results",
    }

    assert isinstance(result["similarity_score"], float)
    assert result["matched_sentence"]
    assert result["top_results"]

    # The retired ambiguity API is gone from the payload.
    assert "margin" not in result


def test_the_web_boot_settings_bind_to_the_real_controller_signature():
    """The A1 regression, checked against the imported class.

    test_web_app_startup.py checks this by parsing the source so the default
    suite stays model-free. This is the same assertion against the real
    signature, and it guards the parser drifting from reality.
    """

    import inspect

    from app.voice.controller import VoiceController
    from app.web.server import DEFAULT_CONTROLLER_SETTINGS

    inspect.signature(VoiceController.__init__).bind(
        object(),
        **DEFAULT_CONTROLLER_SETTINGS,
    )


def test_every_predicted_intent_is_one_the_orchestrator_supports(recognizer):
    from app.devices.mock_device import MockDeviceExecutor
    from app.orchestration.context_manager import ContextManager
    from app.orchestration.orchestrator import Orchestrator

    context = ContextManager()
    supported = set(
        Orchestrator(context, MockDeviceExecutor(context)).workflow_map
    )

    # Every label the recognizer can emit must be executable.
    assert set(recognizer.intent_labels) <= supported
