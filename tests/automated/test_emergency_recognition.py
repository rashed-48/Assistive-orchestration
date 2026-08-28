"""Recognition of safety-critical utterances.

Phase 8A measured EMERGENCY held-out recall at 15% against the running
application's threshold. Concrete emergencies - fire, falls, being
trapped, medical distress - were absent from the dataset entirely, so
utterances naming them scored 0.31-0.49 and fell to UNKNOWN. An
unrecognised emergency never reaches the emergency workflow, however
well that workflow is built.

These tests are the recall contract. They are organised by semantic
category rather than by sentence, because the goal is coverage of
meanings, not memorisation of strings.

Two sets are used deliberately:

  LOCKED    the sentences named in the Phase 8B brief. Several of these
            are also training examples, so they measure the contract,
            not generalisation.

  HELD_OUT  sentences that appear in no corpus in this repository.
            These are the honest generalisation measure.

The recognizer is built with its own default threshold, which
test_dataset_hygiene.py separately pins to the value the application
uses.
"""

import pytest


pytestmark = pytest.mark.model


# The recall floor agreed for Phase 8B. Chosen as a contract, not as a
# claim about real-world safety.
REQUIRED_RECALL = 0.80


@pytest.fixture(scope="module")
def recognizer():
    from app.intent.recognizer import IntentRecognizer

    return IntentRecognizer("data/intents.csv")


# ==============================================================
# EMERGENCY - BY CATEGORY
# ==============================================================


FIRE = [
    "There is a fire",
    "The room is on fire",
    "I smell smoke",
]

FALL = [
    "I fell and cannot get up",
    "I have fallen and need help",
    "I am badly injured",
    "I am bleeding and need help",
]

TRAPPED = [
    "I am trapped and need help",
    "I cannot escape",
]

MEDICAL = [
    "I cannot breathe",
]

LOCKED_EMERGENCY = FIRE + FALL + TRAPPED + MEDICAL


@pytest.mark.parametrize("sentence", FIRE, ids=lambda s: s)
def test_fire_is_an_emergency(recognizer, sentence):
    assert recognizer.predict(sentence)["intent"] == "EMERGENCY"


@pytest.mark.parametrize("sentence", FALL, ids=lambda s: s)
def test_a_fall_or_injury_is_an_emergency(recognizer, sentence):
    assert recognizer.predict(sentence)["intent"] == "EMERGENCY"


@pytest.mark.parametrize("sentence", TRAPPED, ids=lambda s: s)
def test_being_trapped_is_an_emergency(recognizer, sentence):
    assert recognizer.predict(sentence)["intent"] == "EMERGENCY"


@pytest.mark.parametrize("sentence", MEDICAL, ids=lambda s: s)
def test_medical_distress_is_an_emergency(recognizer, sentence):
    assert recognizer.predict(sentence)["intent"] == "EMERGENCY"


# ==============================================================
# EMERGENCY - GENERALISATION
# ==============================================================


HELD_OUT_EMERGENCY = [
    # fire / smoke
    "The kitchen has caught fire",
    "There is thick smoke in here",
    # fall / injury
    "I have taken a bad fall",
    "I slipped and hurt myself badly",
    # trapped
    "I am shut in and cannot get out on my own",
    # medical
    "I am struggling to breathe",
    "I have a crushing pain in my chest",
    "I feel faint and need help urgently",
]


def test_held_out_emergency_recall_meets_the_agreed_floor(recognizer):
    """The honest number: none of these appear in any corpus."""

    predictions = {
        sentence: recognizer.predict(sentence)
        for sentence in HELD_OUT_EMERGENCY
    }

    recognised = [
        sentence
        for sentence, result in predictions.items()
        if result["intent"] == "EMERGENCY"
    ]

    recall = len(recognised) / len(HELD_OUT_EMERGENCY)

    missed = {
        sentence: (result["intent"], round(result["similarity_score"], 3))
        for sentence, result in predictions.items()
        if result["intent"] != "EMERGENCY"
    }

    assert recall >= REQUIRED_RECALL, (
        f"held-out EMERGENCY recall {recall:.0%} is below the "
        f"{REQUIRED_RECALL:.0%} floor. Missed: {missed}"
    )


# ==============================================================
# FALSE EMERGENCY PREVENTION
# ==============================================================


ORDINARY_COMMANDS = [
    "I need my medicine",
    "I want to sleep",
    "I want to study",
    "I want to relax",
    "I want to go outside",
    "I want to come back to my room",
    "Prepare my meal",
    "I am awake now",
    "Shut everything down",
    "It is time for my tablets",
    "I would like to eat",
    "Take me back to my room",
]


@pytest.mark.parametrize("sentence", ORDINARY_COMMANDS, ids=lambda s: s)
def test_an_ordinary_command_never_becomes_an_emergency(recognizer, sentence):
    """The safety boundary in the dangerous direction.

    Expanding EMERGENCY must not pull routine household requests into
    it. A false emergency sounds an alarm and unlocks the house.
    """

    result = recognizer.predict(sentence)

    assert result["intent"] != "EMERGENCY", (
        f"{sentence!r} was classified as an emergency "
        f"(score {result['similarity_score']:.3f}, matched "
        f"{result['matched_sentence']!r})"
    )


def test_out_of_scope_speech_never_becomes_an_emergency(recognizer):
    for sentence in [
        "Tell me a joke",
        "What is the weather today",
        "Who won the football",
        "What time is it",
    ]:
        assert recognizer.predict(sentence)["intent"] != "EMERGENCY", sentence


# ==============================================================
# EMERGENCY vs EMERGENCY_CLEAR
# ==============================================================


EMERGENCY_CLEAR_SENTENCES = [
    "The emergency is over",
    "The emergency has ended",
    "Everything is safe now",
    "The danger has passed",
    "Stop the alarm please",
    "It is all clear now",
    "The situation is under control",
    "I do not need emergency help anymore",
]


@pytest.mark.parametrize(
    "sentence", EMERGENCY_CLEAR_SENTENCES, ids=lambda s: s
)
def test_a_resolved_emergency_is_not_an_active_one(recognizer, sentence):
    """The most dangerous confusion in this pair.

    Classifying "the emergency is over" as EMERGENCY would raise an
    alarm at the moment the user is standing it down.
    """

    result = recognizer.predict(sentence)

    assert result["intent"] == "EMERGENCY_CLEAR", (
        f"{sentence!r} -> {result['intent']} "
        f"({result['similarity_score']:.3f})"
    )


def test_an_active_emergency_is_never_read_as_a_clear(recognizer):
    """The other direction: falsely clearing would silence a real alarm."""

    for sentence in LOCKED_EMERGENCY + HELD_OUT_EMERGENCY:
        result = recognizer.predict(sentence)

        assert result["intent"] != "EMERGENCY_CLEAR", (
            f"{sentence!r} was read as an emergency being stood down"
        )


# ==============================================================
# A DOCUMENTED AMBIGUITY
# ==============================================================


def test_unambiguous_trapped_phrasings_are_recognised(recognizer):
    """Phase 8A found "I cannot get out of the room" -> LEAVE_ROOM (0.854).

    That sentence is genuinely ambiguous in English: it can mean "I am
    trapped" or "the door is shut, please open it". Per the Phase 8B
    brief this phrase is deliberately excluded from the safety-critical
    assertions rather than forced into one reading.

    What must work is the disambiguated form, where the speaker has said
    they need help.
    """

    for sentence in [
        "I cannot get out and need help",
        "I am trapped and need help",
        "I am stuck and need help",
    ]:
        assert recognizer.predict(sentence)["intent"] == "EMERGENCY", sentence


def test_asking_to_leave_normally_is_still_a_room_command(recognizer):
    """The contrast case for the ambiguity above."""

    for sentence in ["I want to go outside", "I want to leave the room"]:
        assert recognizer.predict(sentence)["intent"] == "LEAVE_ROOM", sentence


# ==============================================================
# WHOLE-CORPUS RECALL
# ==============================================================


def test_every_training_sentence_still_classifies_as_its_own_label(recognizer):
    """Expanding one class must not swallow another."""

    import pandas as pd

    frame = pd.read_csv("data/intents.csv")

    wrong = [
        (row["sentence"], row["intent"], recognizer.predict(row["sentence"])["intent"])
        for _, row in frame.iterrows()
        if recognizer.predict(row["sentence"])["intent"] != row["intent"]
    ]

    assert wrong == [], f"{len(wrong)} training sentences self-misclassify: {wrong[:5]}"


def validation_recall(recognizer):
    import pandas as pd

    frame = pd.read_csv("data/validation.csv")

    return {
        label: sum(
            recognizer.predict(sentence)["intent"] == label
            for sentence in group["sentence"]
        ) / len(group)
        for label, group in frame.groupby("intent")
    }


def test_safety_critical_labels_meet_the_agreed_recall_floor(recognizer):
    by_label = validation_recall(recognizer)

    assert by_label.get("EMERGENCY", 0) >= REQUIRED_RECALL, by_label
    assert by_label.get("EMERGENCY_CLEAR", 0) >= REQUIRED_RECALL, by_label


def test_ordinary_labels_do_not_collapse(recognizer):
    """A floor, not a target.

    Phase 8B expanded the two safety-critical labels only. The ordinary
    labels were deliberately left alone, so that the validation set -
    which is new in this phase - stays a fair measure of them rather than
    something the expansion was fitted to.

    Their held-out recall is 40-70%, which is a real generalisation gap
    across the whole corpus and the recommended subject of a later phase.
    This assertion only catches a collapse caused by the emergency
    expansion swallowing another class.
    """

    ORDINARY_FLOOR = 0.40

    by_label = validation_recall(recognizer)

    collapsed = {
        label: round(recall, 2)
        for label, recall in by_label.items()
        if label not in ("EMERGENCY", "EMERGENCY_CLEAR")
        and recall < ORDINARY_FLOOR
    }

    assert collapsed == {}, (
        f"labels below the {ORDINARY_FLOOR:.0%} floor: {collapsed}. "
        f"Full picture: {({k: round(v, 2) for k, v in by_label.items()})}"
    )


# ==============================================================
# PHASE 8C - ORDINARY INTENT GENERALISATION
# ==============================================================


def holdout_recall(recognizer):
    import pandas as pd

    frame = pd.read_csv("data/holdout.csv")

    return {
        label: sum(
            recognizer.predict(sentence)["intent"] == label
            for sentence in group["sentence"]
        ) / len(group)
        for label, group in frame.groupby("intent")
    }


# Measured on the Phase 8C final holdout after expansion. These are
# floors that lock in the improvement, not targets: ordinary recall rose
# from 47% to 68% overall, and no label may now fall back below the band
# it reached.
ORDINARY_FLOORS = {
    "MEDICATION": 0.90,
    "PREPARE_FOR_MEAL": 0.90,
    "PREPARE_FOR_SLEEP": 0.90,
    "WAKE_UP": 0.60,
    "RETURN_TO_ROOM": 0.50,
    "SHUTDOWN_ENVIRONMENT": 0.50,
    "RELAX_MODE": 0.40,
    "STUDY_MODE": 0.40,
    "LEAVE_ROOM": 0.20,
}


def test_ordinary_intent_recall_does_not_regress(recognizer):
    by_label = holdout_recall(recognizer)

    below = {
        label: (round(by_label.get(label, 0), 2), floor)
        for label, floor in ORDINARY_FLOORS.items()
        if by_label.get(label, 0) < floor
    }

    assert below == {}, (
        f"labels below their locked floor (actual, floor): {below}. "
        f"Full picture: {({k: round(v, 2) for k, v in by_label.items()})}"
    )


def test_overall_ordinary_accuracy_holds(recognizer):
    import pandas as pd

    frame = pd.read_csv("data/holdout.csv")
    ordinary = frame[~frame["intent"].isin(["EMERGENCY", "EMERGENCY_CLEAR"])]

    correct = sum(
        recognizer.predict(row["sentence"])["intent"] == row["intent"]
        for _, row in ordinary.iterrows()
    )

    accuracy = correct / len(ordinary)

    assert accuracy >= 0.60, (
        f"ordinary holdout accuracy {accuracy:.0%} has fallen below the "
        f"60% floor established in Phase 8C"
    )


def test_the_safety_labels_survive_ordinary_expansion(recognizer):
    """Step 8: growing ordinary classes must not erode the safety pair."""

    by_label = holdout_recall(recognizer)

    assert by_label.get("EMERGENCY", 0) >= REQUIRED_RECALL, by_label
    assert by_label.get("EMERGENCY_CLEAR", 0) >= REQUIRED_RECALL, by_label


def test_no_ordinary_holdout_sentence_becomes_an_emergency(recognizer):
    """The safety boundary, measured on genuinely unseen sentences."""

    import pandas as pd

    frame = pd.read_csv("data/holdout.csv")
    ordinary = frame[~frame["intent"].isin(["EMERGENCY", "EMERGENCY_CLEAR"])]

    false_alarms = [
        row["sentence"]
        for _, row in ordinary.iterrows()
        if recognizer.predict(row["sentence"])["intent"] == "EMERGENCY"
    ]

    assert false_alarms == [], f"false emergencies: {false_alarms}"


def test_an_ordinary_command_is_never_routed_to_the_wrong_workflow(recognizer):
    """The failure mode that matters for an assistive system.

    After Phase 8C every remaining holdout failure is UNKNOWN, which asks
    the user to repeat themselves. Predicting the *wrong* workflow would
    instead move them through doors they did not ask for.
    """

    import pandas as pd

    frame = pd.read_csv("data/holdout.csv")

    misrouted = [
        (row["sentence"], row["intent"], result["intent"])
        for _, row in frame.iterrows()
        for result in [recognizer.predict(row["sentence"])]
        if result["intent"] is not None and result["intent"] != row["intent"]
    ]

    assert misrouted == [], f"commands sent to the wrong workflow: {misrouted}"
