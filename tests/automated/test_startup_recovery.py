"""Restart recovery: what survives, what is downgraded, what is refused.

A restart is the one moment the system is guaranteed to have missed
whatever happened in the physical world. These tests pin how much of
the stored world it is willing to claim afterwards.

The rules come from the Phase 10A location model:

    KNOWN   + clean shutdown  -> KNOWN      nothing happened in between
    KNOWN   + crash           -> UNKNOWN    the session ended mid-life
    IN_TRANSIT                -> UNKNOWN    the move never completed
    UNKNOWN                   -> UNKNOWN    uncertainty is not laundered

and the emergency latch is restored from explicit lifecycle metadata,
never from a mode value a fresh object would have reset.
"""

import pytest

from app.orchestration.orchestrator import EmergencyActive, LocationUnknown
from app.orchestration.state import (
    DoorState,
    LocationStatus,
    Mode,
    PowerState,
    PreparationState,
    Room,
)
from app.runtime import ApplicationRuntime

from tests.automated.support import quiet


class Executor:
    """Acknowledges everything, or refuses one named device."""

    def __init__(self, fail_device=None):
        self.actions = []
        self.fail_device = fail_device

    def execute(self, action):
        self.actions.append(action)

        return {
            "status": (
                "error" if action.device_id == self.fail_device else "success"
            ),
            "device": action.device_id,
            "action": action.action_type.value,
            "command_id": f"cmd-{len(self.actions)}",
            "node": "test_node",
        }

    def devices(self):
        return [action.device_id for action in self.actions]


def boot(directory, executor=None):
    """Start a session against a state directory, as a real process would."""

    executor = executor or Executor()

    with quiet():
        runtime = ApplicationRuntime(
            device_executor=executor,
            state_directory=directory,
        )

    return runtime, executor


def run(runtime, intent):
    with quiet():
        try:
            return runtime.execute_intent(intent), None
        except Exception as error:
            return [], error


def crash(runtime):
    """End a session without shutdown(), the way a kill -9 would."""

    # Deliberately does nothing: no clean_shutdown marker is written.
    return None


# ==============================================================
# 16-17  A CLEAN RESTART KEEPS THE WORLD
# ==============================================================


def test_state_survives_a_clean_restart(state_directory):
    first, executor = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")

    assert first.context.get_current_room() == Room.SLEEP_ROOM
    with quiet():
        first.shutdown()

    second, _ = boot(state_directory)

    assert second.recovery.restored is True
    assert second.recovery.clean_shutdown is True
    assert second.context.get_current_room() == Room.SLEEP_ROOM
    assert second.context.get_current_mode() == Mode.SLEEP
    assert second.context.get_state().sleep.bed == PreparationState.READY


def test_a_clean_restart_keeps_the_location_known(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    with quiet():
        first.shutdown()

    second, _ = boot(state_directory)

    assert second.context.get_location_status() == LocationStatus.KNOWN
    assert second.recovery.location_downgraded is False


def test_the_restored_world_is_used_for_the_next_command(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    with quiet():
        first.shutdown()

    second, executor = boot(state_directory)
    run(second, "WAKE_UP")

    # Planned from the sleep room it woke up in, not from OUTSIDE.
    assert executor.devices() == ["sleep_bed"]
    assert second.context.get_current_room() == Room.SLEEP_ROOM


def test_a_first_run_with_no_stored_state_starts_fresh(state_directory):
    runtime, _ = boot(state_directory)

    assert runtime.recovery.restored is False
    assert runtime.context.get_current_room() == Room.OUTSIDE
    assert runtime.context.get_location_status() == LocationStatus.KNOWN


# ==============================================================
# 18-21  A CRASH DOWNGRADES WHAT IT CANNOT VOUCH FOR
# ==============================================================


def test_a_crash_turns_a_known_location_into_an_unknown_one(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.restored is True
    assert second.recovery.clean_shutdown is False
    assert second.context.get_location_status() == LocationStatus.UNKNOWN
    assert second.recovery.location_downgraded is True
    assert "unexpectedly" in second.recovery.location_reason

    # The device world it recorded is still there; only the claim about
    # the person was withdrawn.
    assert second.context.get_state().sleep.light == PowerState.ON


def test_the_last_known_room_survives_a_crash_for_diagnosis(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.last_known_room == "SLEEP_ROOM"
    assert second.context.get_current_room() == Room.SLEEP_ROOM
    assert second.context.get_current_room() != Room.OUTSIDE


def test_an_interrupted_move_restores_as_unknown_with_both_ends(state_directory):
    first, _ = boot(state_directory, Executor(fail_device="sleep_door"))
    first.context.confirm_location(Room.RELAX_ROOM)
    first.context.set_mode(Mode.RELAX)

    # Fails part way; the door had already opened, so the location is
    # unknown and that is what gets persisted.
    _, error = run(first, "PREPARE_FOR_SLEEP")
    assert error is not None
    crash(first)

    second, _ = boot(state_directory)

    assert second.context.get_location_status() == LocationStatus.UNKNOWN
    assert second.recovery.last_known_room == "RELAX_ROOM"
    assert second.recovery.location_reason


def test_a_snapshot_stored_mid_transit_restores_as_unknown(state_directory):
    first, _ = boot(state_directory)
    first.context.confirm_location(Room.STUDY_ROOM)
    first.context.begin_transit(Room.MEAL_ROOM, reason="PREPARE_FOR_MEAL in progress")
    first._save_snapshot(clean_shutdown=False)
    crash(first)

    second, _ = boot(state_directory)

    assert second.context.get_location_status() == LocationStatus.UNKNOWN
    assert second.recovery.last_known_room == "STUDY_ROOM"
    assert second.recovery.interrupted_destination == "MEAL_ROOM"
    assert "interrupted moving from STUDY_ROOM to MEAL_ROOM" in (
        second.recovery.location_reason
    )


def test_an_unknown_location_is_never_laundered_into_a_room(state_directory):
    first, _ = boot(state_directory)
    first.context.confirm_location(Room.MEAL_ROOM)
    first.context.mark_location_unknown(reason="the operator was unsure")
    with quiet():
        first.shutdown()

    second, _ = boot(state_directory)

    # Even a clean shutdown does not upgrade uncertainty.
    assert second.recovery.clean_shutdown is True
    assert second.context.get_location_status() == LocationStatus.UNKNOWN
    assert second.context.get_current_room() != Room.OUTSIDE


def test_a_movement_command_is_refused_after_a_crash(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    crash(first)

    second, executor = boot(state_directory)
    _, error = run(second, "RELAX_MODE")

    assert isinstance(error, LocationUnknown)
    assert executor.actions == []

    # And confirming resolves it, exactly as within one session.
    second.context.confirm_location(Room.SLEEP_ROOM)
    _, error = run(second, "RELAX_MODE")

    assert error is None
    assert second.context.get_current_room() == Room.RELAX_ROOM


# ==============================================================
# CLEAN-SHUTDOWN MARKER LIFECYCLE
# ==============================================================


def test_a_running_session_is_marked_dirty_immediately(state_directory):
    runtime, _ = boot(state_directory)

    document = runtime.repository.load_snapshot()

    # Written at startup, before any command: a crash from here on is
    # distinguishable from a clean exit.
    assert document is not None
    assert document["clean_shutdown"] is False


def test_a_workflow_snapshot_never_claims_a_clean_shutdown(state_directory):
    runtime, _ = boot(state_directory)
    run(runtime, "PREPARE_FOR_SLEEP")

    assert runtime.repository.load_snapshot()["clean_shutdown"] is False


def test_only_shutdown_writes_the_clean_marker(state_directory):
    runtime, _ = boot(state_directory)
    run(runtime, "PREPARE_FOR_SLEEP")

    with quiet():
        runtime.shutdown()

    assert runtime.repository.load_snapshot()["clean_shutdown"] is True


def test_a_failed_workflow_still_persists_committed_device_state(state_directory):
    first, _ = boot(state_directory, Executor(fail_device="sleep_door"))
    _, error = run(first, "PREPARE_FOR_SLEEP")
    assert error is not None
    crash(first)

    second, _ = boot(state_directory)

    # exit_door opened and closed and the corridor light came on before
    # the failure; all of that was acknowledged and is still recorded.
    assert second.context.get_state().drawing_light == PowerState.ON
    assert second.context.get_current_room() == Room.OUTSIDE


# ==============================================================
# 22-29  EMERGENCY SURVIVES A RESTART
# ==============================================================


def test_the_emergency_latch_survives_a_restart(state_directory):
    first, _ = boot(state_directory)
    run(first, "EMERGENCY")

    assert first.emergency_active()
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.emergency_latched is True
    assert second.emergency_active()
    assert second.context.emergency_latched()


def test_a_restart_never_silently_clears_an_emergency(state_directory):
    first, _ = boot(state_directory)
    run(first, "EMERGENCY")
    with quiet():
        first.shutdown()

    second, executor = boot(state_directory)

    # The defect this phase exists to fix: a restart used to accept
    # normal commands again.
    _, error = run(second, "PREPARE_FOR_SLEEP")

    assert isinstance(error, EmergencyActive)
    assert executor.actions == []
    assert second.emergency_active()


def test_emergency_and_its_clear_remain_available_after_a_restart(state_directory):
    first, _ = boot(state_directory)
    run(first, "EMERGENCY")
    crash(first)

    second, executor = boot(state_directory)

    assert second.is_allowed_now("EMERGENCY")
    assert second.is_allowed_now("EMERGENCY_CLEAR")
    assert not second.is_allowed_now("PREPARE_FOR_SLEEP")

    # Re-asserting the emergency is a safe, state-aware retry.
    _, error = run(second, "EMERGENCY")
    assert error is None


def test_a_restart_actuates_nothing(state_directory):
    """The persisted file is not proof of the hardware's state."""

    first, _ = boot(state_directory)
    run(first, "EMERGENCY")
    crash(first)

    second, executor = boot(state_directory)

    # Booting sent no command at all - no buzzer, no doors.
    assert executor.actions == []
    assert "buzzer" not in executor.devices()
    assert "exit_door" not in executor.devices()


def test_clearing_after_a_restart_removes_the_latch_for_good(state_directory):
    first, _ = boot(state_directory)
    run(first, "EMERGENCY")
    crash(first)

    second, _ = boot(state_directory)
    _, error = run(second, "EMERGENCY_CLEAR")

    assert error is None
    assert not second.emergency_active()
    assert not second.context.emergency_latched()

    with quiet():
        second.shutdown()

    third, _ = boot(state_directory)

    # The clear is durable too.
    assert not third.emergency_active()
    assert third.recovery.emergency_latched is False


def test_a_failed_clear_keeps_the_latch_across_a_restart(state_directory):
    first, _ = boot(state_directory)
    run(first, "EMERGENCY")

    # The exit door refuses, so recovery is incomplete.
    first.device_executor.fail_device = "exit_door"
    run(first, "EMERGENCY_CLEAR")

    assert first.emergency_active()
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.emergency_latched is True
    assert second.emergency_active()


# ==============================================================
# 30-31  MEDICATION IS AUDITED, NEVER REPLAYED
# ==============================================================


def test_a_dose_is_recorded_in_the_event_log(state_directory):
    runtime, _ = boot(state_directory)
    runtime.context.confirm_location(Room.SLEEP_ROOM)

    run(runtime, "MEDICATION")

    doses = [
        event
        for event in runtime.repository.load_events()
        if event["action"] == "ACTIVATE_MEDICATION"
    ]

    assert len(doses) == 1
    assert doses[0]["device"] == "medication_servo"
    assert doses[0]["command_id"]
    assert doses[0]["status"] == "success"


def test_restarting_never_re_dispenses_a_dose(state_directory):
    first, _ = boot(state_directory)
    first.context.confirm_location(Room.SLEEP_ROOM)
    run(first, "MEDICATION")
    crash(first)

    second, executor = boot(state_directory)

    # Booting after an unfinished-looking session sends nothing at all.
    assert executor.actions == []

    # The dose remains visible as an audit record, and the servo state
    # it produced survived.
    doses = [
        event
        for event in second.repository.load_events()
        if event["action"] == "ACTIVATE_MEDICATION"
    ]
    assert len(doses) == 1
    assert second.context.get_state().sleep.medication_servo == PowerState.ON


# ==============================================================
# 11-14  EVENTS COME FROM ACKNOWLEDGED ACTIONS ONLY
# ==============================================================


def test_one_event_per_acknowledged_action(state_directory):
    runtime, executor = boot(state_directory)
    run(runtime, "PREPARE_FOR_SLEEP")

    events = runtime.repository.load_events()

    assert len(events) == len(executor.actions)
    assert [event["device"] for event in events] == executor.devices()


def test_an_event_carries_the_command_id_and_the_node(state_directory):
    runtime, _ = boot(state_directory)
    run(runtime, "PREPARE_FOR_SLEEP")

    for event in runtime.repository.load_events():
        assert event["event_type"] == "action_acknowledged"
        assert event["command_id"]
        assert event["node"] == "test_node"
        assert event["action"]
        assert event["status"] == "success"
        assert event["intent"] == "PREPARE_FOR_SLEEP"


def test_a_refused_action_is_never_logged_as_acknowledged(state_directory):
    runtime, executor = boot(state_directory, Executor(fail_device="sleep_door"))
    _, error = run(runtime, "PREPARE_FOR_SLEEP")

    assert error is not None

    events = runtime.repository.load_events()

    # The three that succeeded are there; the refusal is not.
    assert [event["device"] for event in events] == [
        "exit_door",
        "exit_door",
        "drawing_light",
    ]
    assert "sleep_door" not in [event["device"] for event in events]
    assert all(event["status"] == "success" for event in events)


def test_the_event_log_records_the_state_each_action_produced(state_directory):
    runtime, _ = boot(state_directory)
    run(runtime, "PREPARE_FOR_SLEEP")

    events = runtime.repository.load_events()

    # The first action opened the front door, and the recorded state
    # shows exactly that.
    assert events[0]["resulting_state"]["exit_door"] == "OPEN"

    # The log follows the two commit tiers faithfully. Device state is
    # committed per acknowledged action, so the last action already shows
    # the bed prepared - but the room is still OUTSIDE, because the move
    # is only committed once the whole workflow has succeeded, which
    # happens after the final action event.
    assert events[-1]["resulting_state"]["rooms"]["sleep"]["bed"] == "READY"
    assert events[-1]["resulting_state"]["current_room"] == "OUTSIDE"
    assert events[-1]["resulting_state"]["location_status"] == "IN_TRANSIT"

    # The snapshot taken at the end of the workflow is where the
    # completed move appears.
    assert runtime.repository.load_snapshot()["state"]["current_room"] == (
        "SLEEP_ROOM"
    )


# ==============================================================
# CORRUPTION IS SURVIVABLE
# ==============================================================


def test_a_corrupt_snapshot_starts_fresh_rather_than_half_restored(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    with quiet():
        first.shutdown()

    first.repository.snapshot_path.write_text("{ truncated", encoding="utf-8")
    first.repository.backup_path.unlink(missing_ok=True)

    second, _ = boot(state_directory)

    assert second.recovery.restored is False
    assert second.recovery.rejected_reason
    assert second.context.get_current_room() == Room.OUTSIDE
    assert second.context.get_location_status() == LocationStatus.KNOWN


def test_an_unreadable_snapshot_recovers_from_the_backup(state_directory):
    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    with quiet():
        first.shutdown()

    first.repository.snapshot_path.write_text("{ truncated", encoding="utf-8")

    second, _ = boot(state_directory)

    assert second.recovery.restored is True
    assert second.recovery.recovered_from_backup is True


def test_persistence_can_be_switched_off_entirely(tmp_path):
    with quiet():
        runtime = ApplicationRuntime(
            device_executor=Executor(),
            persist=False,
        )

    assert runtime.repository is None

    run(runtime, "PREPARE_FOR_SLEEP")
    with quiet():
        runtime.shutdown()

    assert list(tmp_path.iterdir()) == []


# ==============================================================
# 32-34  THE CONTINUOUS LOOP IS UNCHANGED
# ==============================================================


def test_a_multi_command_session_still_chains_state(state_directory):
    runtime, executor = boot(state_directory)

    journey = []
    for intent in ["PREPARE_FOR_SLEEP", "WAKE_UP", "RELAX_MODE", "STUDY_MODE"]:
        mark = len(executor.actions)
        run(runtime, intent)
        journey.append(
            (runtime.context.get_current_room(), len(executor.actions) - mark)
        )

    assert journey == [
        (Room.SLEEP_ROOM, 8),
        (Room.SLEEP_ROOM, 1),
        (Room.RELAX_ROOM, 9),
        (Room.STUDY_ROOM, 10),
    ]

    # Persistence observed the whole session without altering it.
    assert len(runtime.repository.load_events()) == len(executor.actions)


def test_dependency_planning_is_unchanged_by_persistence(state_directory):
    runtime, executor = boot(state_directory)

    run(runtime, "PREPARE_FOR_SLEEP")
    mark = len(executor.actions)
    run(runtime, "PREPARE_FOR_SLEEP")

    # Already there: still exactly two actions, as before this phase.
    assert executor.devices()[mark:] == ["sleep_light", "sleep_bed"]


# ==============================================================
# AN UNEVENTFUL SESSION LEAVES NOTHING TO DISTRUST
# ==============================================================


def test_a_crash_with_no_committed_work_does_not_warn(state_directory):
    """Starting and closing the app badly must not lock the user out.

    The downgrade exists to withdraw a stale claim. If the previous
    session committed nothing, the stored world is identical to a fresh
    one and there is no claim to withdraw - warning would be noise, and
    would refuse every command on a first run.
    """

    first, _ = boot(state_directory)
    crash(first)

    second, executor = boot(state_directory)

    assert second.recovery.restored is True
    assert second.recovery.clean_shutdown is False
    assert second.recovery.location_downgraded is False

    assert second.context.get_location_status() == LocationStatus.KNOWN
    assert second.context.get_current_room() == Room.OUTSIDE

    # And commands work straight away.
    _, error = run(second, "PREPARE_FOR_SLEEP")

    assert error is None
    assert second.context.get_current_room() == Room.SLEEP_ROOM


def test_a_crash_after_real_work_still_warns(state_directory):
    """The guard must not swallow a genuine loss of tracking."""

    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.location_downgraded is True
    assert second.context.get_location_status() == LocationStatus.UNKNOWN


def test_leaving_the_house_still_counts_as_history(state_directory):
    """OUTSIDE is not the same as never having moved.

    LEAVE_ROOM ends at OUTSIDE, which looks like the starting room - but
    it records a return target, so the world is not a fresh one and the
    crash downgrade must still apply.
    """

    first, _ = boot(state_directory)
    run(first, "PREPARE_FOR_SLEEP")
    run(first, "LEAVE_ROOM")
    assert first.context.get_current_room() == Room.OUTSIDE
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.location_downgraded is True
    assert second.context.get_location_status() == LocationStatus.UNKNOWN


def test_an_emergency_declared_then_crashed_still_latches(state_directory):
    """Even with no movement, an emergency is history worth keeping."""

    first, _ = boot(state_directory)
    run(first, "EMERGENCY")
    crash(first)

    second, _ = boot(state_directory)

    assert second.recovery.emergency_latched is True
    assert second.emergency_active()


# ==============================================================
# EVERY PRINTED CHARACTER SURVIVES A NON-UTF8 CONSOLE
# ==============================================================


def test_no_source_file_prints_a_character_a_cp1252_console_cannot_encode():
    """A Windows console defaults to cp1252.

    An arrow in a log line raised UnicodeEncodeError mid-workflow, which
    surfaced to the web interface as a failed command. Runtime output
    must therefore stay inside the encodings a plain console can print.
    """

    from pathlib import Path

    offenders = {}

    for path in Path("app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")

        unencodable = sorted(
            {
                character
                for character in text
                if ord(character) > 127
            }
        )

        if unencodable:
            offenders[str(path)] = unencodable

    assert offenders == {}, (
        f"these files contain characters a cp1252 console cannot print: "
        f"{offenders}"
    )
