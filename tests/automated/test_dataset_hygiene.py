"""Dataset hygiene for the intent corpora.

Model free, so it runs in the default suite. The recognition dataset is
production input: a blank row, a duplicate, or a label the Orchestrator
cannot execute is a defect in the same way a code bug is.

Phase 8A found 10 blank physical rows, 2 exact duplicates, and a
validation set that leaked 14 of its 100 rows from the training set.
"""

import csv
from pathlib import Path

import pytest


DATA = Path("data")

CORPORA = ["intents", "validation", "holdout"]

# Enough examples to describe a semantic category without demanding an
# artificially balanced corpus. Scoring is max-over-sentences, so a small
# class is not penalised; this floor only guards against a label being
# left almost empty by accident.
MINIMUM_EXAMPLES_PER_INTENT = 12


def read_rows(name):
    """Read with the csv module, which does not silently skip blank lines."""

    with open(DATA / f"{name}.csv", newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def read_frame(name):
    import pandas as pd

    return pd.read_csv(DATA / f"{name}.csv")


def supported_intents():
    from app.devices.mock_device import MockDeviceExecutor
    from app.orchestration.context_manager import ContextManager
    from app.orchestration.orchestrator import Orchestrator

    context = ContextManager()
    return set(Orchestrator(context, MockDeviceExecutor(context)).workflow_map)


# ==============================================================
# STRUCTURE
# ==============================================================


@pytest.mark.parametrize("name", CORPORA)
def test_every_row_has_exactly_two_fields(name):
    rows = read_rows(name)

    malformed = [
        (number, row)
        for number, row in enumerate(rows, start=1)
        if len(row) != 2
    ]

    assert malformed == [], (
        f"{name}.csv has rows that are blank or badly quoted: {malformed[:5]}"
    )


@pytest.mark.parametrize("name", CORPORA)
def test_the_csv_module_and_pandas_agree_on_the_row_count(name):
    rows = read_rows(name)
    frame = read_frame(name)

    # rows includes the header; pandas does not.
    assert len(rows) - 1 == len(frame), (
        f"{name}.csv parses differently depending on the reader, which "
        f"means blank or malformed rows are being silently dropped."
    )


@pytest.mark.parametrize("name", CORPORA)
def test_the_header_is_sentence_then_intent(name):
    assert read_rows(name)[0] == ["sentence", "intent"]


# ==============================================================
# CONTENT
# ==============================================================


@pytest.mark.parametrize("name", CORPORA)
def test_no_row_has_an_empty_sentence_or_intent(name):
    frame = read_frame(name)

    assert frame["sentence"].isna().sum() == 0
    assert frame["intent"].isna().sum() == 0
    assert (frame["sentence"].str.strip() == "").sum() == 0


@pytest.mark.parametrize("name", CORPORA)
def test_no_exact_duplicate_sentences(name):
    frame = read_frame(name)

    duplicated = frame[frame["sentence"].duplicated(keep=False)]

    assert duplicated.empty, (
        f"{name}.csv repeats sentences: "
        f"{sorted(set(duplicated['sentence']))}"
    )


@pytest.mark.parametrize("name", CORPORA)
def test_every_label_is_a_workflow_the_orchestrator_can_execute(name):
    frame = read_frame(name)

    assert set(frame["intent"]) <= supported_intents()


@pytest.mark.parametrize("name", CORPORA)
def test_every_intent_has_enough_examples(name):
    frame = read_frame(name)

    counts = frame["intent"].value_counts()
    thin = counts[counts < MINIMUM_EXAMPLES_PER_INTENT]

    if name in ("validation", "holdout"):
        pytest.skip(f"the {name} set is deliberately smaller per label")

    assert thin.empty, f"{name}.csv has thin labels: {thin.to_dict()}"


# ==============================================================
# THE TWO CORPORA MUST AGREE, AND MUST NOT OVERLAP
# ==============================================================


def test_validation_covers_every_label_the_training_set_defines():
    training = read_frame("intents")
    validation = read_frame("validation")

    missing = set(training["intent"]) - set(validation["intent"])

    assert missing == set(), (
        f"validation.csv has no examples for {sorted(missing)}, so those "
        f"labels are never measured."
    )


def test_holdout_covers_every_label_the_training_set_defines():
    training = read_frame("intents")
    holdout = read_frame("holdout")

    assert set(training["intent"]) - set(holdout["intent"]) == set()


def test_the_holdout_is_genuinely_unseen():
    """The Phase 8C final holdout.

    It exists to measure generalisation, so a single shared sentence
    with either the training corpus or the development set destroys its
    purpose.
    """

    holdout = read_frame("holdout")

    for other in ("intents", "validation"):
        shared = holdout[holdout["sentence"].isin(set(read_frame(other)["sentence"]))]

        assert shared.empty, (
            f"{len(shared)} holdout sentences also appear in {other}.csv: "
            f"{sorted(shared['sentence'])[:5]}"
        )


def test_validation_is_genuinely_held_out():
    training = read_frame("intents")
    validation = read_frame("validation")

    leaked = validation[validation["sentence"].isin(set(training["sentence"]))]

    assert leaked.empty, (
        f"{len(leaked)} validation sentences also appear in the training "
        f"set, so they measure memorisation rather than generalisation: "
        f"{sorted(leaked['sentence'])[:5]}"
    )


# ==============================================================
# THRESHOLD CONSISTENCY
# ==============================================================


def test_one_authoritative_similarity_threshold():
    """The application, the library default, and the tests must agree.

    Phase 8A found the web application running at 0.65 while the
    recognizer default, the VoiceController default, and every automated
    recognition test used 0.60. Measurements taken against one value did
    not describe the other.
    """

    import ast
    from pathlib import Path

    from app.intent import DEFAULT_SIMILARITY_THRESHOLD
    from app.web.server import DEFAULT_CONTROLLER_SETTINGS

    assert (
        DEFAULT_CONTROLLER_SETTINGS["similarity_threshold"]
        == DEFAULT_SIMILARITY_THRESHOLD
    )

    # No module may hard-code a competing literal. Parsed rather than
    # imported so this test stays free of sentence-transformers.
    for module in ("app/intent/recognizer.py", "app/voice/controller.py"):
        tree = ast.parse(Path(module).read_text(encoding="utf-8"))

        literals = [
            node.value
            for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef)
            for node in function.args.defaults
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]

        assert literals == [], (
            f"{module} hard-codes a threshold default {literals}; it must "
            f"use app.intent.DEFAULT_SIMILARITY_THRESHOLD"
        )
