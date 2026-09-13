"""The ordering-violation detector used by the baseline comparison.

The detector is only meaningful if it fires when it should and stays
silent when it should not. Against simulated nodes it can do neither
usefully - they complete in under a millisecond, so no realistic delay
can dispatch ahead of them - which is exactly why the baseline
experiment needs physical actuators. These tests exercise the analysis
directly on constructed event sequences instead.
"""

from tools.measure_baseline import analyse


def command(at, command_id, device):
    return (at, "command", {"command_id": command_id, "device": device})


def complete(at, command_id, status="success"):
    return (at, "complete", {"command_id": command_id, "status": status})


def test_waiting_for_completion_before_dispatching_is_not_a_violation():
    """Acknowledgement-gated execution makes this impossible by
    construction: the next command cannot leave until the previous
    action has been confirmed."""

    events = [
        command(0.0, "a", "sleep_door"),
        complete(0.7, "a"),
        command(0.8, "b", "sleep_bed"),
        complete(1.5, "b"),
    ]

    result = analyse(events)

    assert result["violations"] == 0
    assert result["dispatched"] == 2
    assert result["acted"] == 2


def test_dispatching_before_the_previous_action_finished_is_a_violation():
    """Open loop with a delay shorter than the device takes: the second
    command leaves at 0.1 s while the first door is still moving and
    does not report until 0.7 s."""

    events = [
        command(0.0, "a", "sleep_door"),
        command(0.1, "b", "sleep_bed"),
        complete(0.7, "a"),
        complete(0.8, "b"),
    ]

    result = analyse(events)

    assert result["violations"] == 1
    assert result["violation_pairs"] == [("sleep_door", "sleep_bed")]


def test_every_early_dispatch_is_counted_not_just_the_first():
    events = [
        command(0.0, "a", "d1"),
        command(0.1, "b", "d2"),
        command(0.2, "c", "d3"),
        complete(0.7, "a"),
        complete(0.8, "b"),
        complete(0.9, "c"),
    ]

    assert analyse(events)["violations"] == 2


def test_a_prerequisite_that_never_completed_is_a_violation():
    """The strongest case: the previous action was never confirmed at
    all, so dispatching after it cannot have been ordered correctly."""

    events = [
        command(0.0, "a", "study_door"),
        command(0.1, "b", "sleep_bed"),
        complete(0.8, "b"),
    ]

    result = analyse(events)

    assert result["violations"] == 1
    assert result["acted"] == 1


def test_a_retry_is_not_counted_as_a_second_dispatch():
    """Retries reuse the command id, so counting publishes rather than
    distinct ids would inflate both the dispatch count and the
    violations."""

    events = [
        command(0.0, "a", "sleep_door"),
        command(5.0, "a", "sleep_door"),
        complete(5.7, "a"),
        command(5.8, "b", "sleep_bed"),
        complete(6.5, "b"),
    ]

    result = analyse(events)

    assert result["dispatched"] == 2
    assert result["violations"] == 0


def test_only_the_first_completion_for_an_id_is_taken():
    """A duplicate reply arrives for an id already completed. Taking a
    later one would move the completion timestamp forward and
    manufacture violations that did not happen."""

    events = [
        command(0.0, "a", "sleep_door"),
        complete(0.7, "a"),
        command(0.8, "b", "sleep_bed"),
        complete(0.9, "a"),
        complete(1.5, "b"),
    ]

    assert analyse(events)["violations"] == 0


def test_failed_actions_are_not_counted_as_acted():
    events = [
        command(0.0, "a", "study_door"),
        complete(0.7, "a", status="error"),
    ]

    result = analyse(events)

    assert result["dispatched"] == 1
    assert result["acted"] == 0


def test_an_empty_workflow_is_handled():
    assert analyse([])["violations"] == 0
    assert analyse([])["dispatched"] == 0
