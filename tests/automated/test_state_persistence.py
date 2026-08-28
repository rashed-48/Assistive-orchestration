"""Durable storage: serialisation, atomic snapshots, and the event log.

StateRepository is the only component that touches a disk. It records
and returns data and makes no decisions, so everything here is about
whether a byte survives a crash, not about what the system should do
next. Recovery policy lives in test_startup_recovery.py.
"""

import json

import pytest

from app.orchestration.context_manager import ContextManager, StateRestoreError
from app.orchestration.state import (
    DoorState,
    LocationStatus,
    Mode,
    PowerState,
    PreparationState,
    Room,
)
from app.persistence import (
    SCHEMA_VERSION,
    SnapshotError,
    StateRepository,
)


@pytest.fixture
def repository(tmp_path):
    return StateRepository(tmp_path / "state")


def populated():
    """A context with every kind of field set to something non-default."""

    context = ContextManager()

    context.confirm_location(Room.SLEEP_ROOM)
    context.set_mode(Mode.SLEEP)
    context.set_return_target(Room.STUDY_ROOM)
    context.set_drawing_light(PowerState.ON)
    context.set_exit_door(DoorState.OPEN)
    context.set_buzzer(PowerState.ON)

    state = context.get_state()
    state.study.door = DoorState.OPEN
    state.study.light = PowerState.ON
    state.study.table = PreparationState.READY
    state.relax.tv = PowerState.ON
    state.sleep.bed = PreparationState.READY
    state.sleep.medication_servo = PowerState.ON
    state.meal.table = PreparationState.READY

    return context


# ==============================================================
# 1-3  SERIALISATION ROUND-TRIP
# ==============================================================


def test_a_fully_populated_state_round_trips():
    original = populated()

    restored = ContextManager()
    restored.restore_from(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert restored.get_state() == original.get_state()


def test_the_location_fields_round_trip():
    original = ContextManager()
    original.begin_transit(Room.MEAL_ROOM, reason="PREPARE_FOR_MEAL in progress")

    restored = ContextManager()
    restored.restore_from(original.to_dict())

    assert restored.get_location_status() == LocationStatus.IN_TRANSIT
    assert restored.get_location_destination() == Room.MEAL_ROOM
    assert restored.get_location_reason() == "PREPARE_FOR_MEAL in progress"


def test_the_emergency_lifecycle_round_trips():
    original = ContextManager()
    original.declare_emergency(at="2026-01-01T00:00:00+00:00")

    restored = ContextManager()
    restored.restore_from(original.to_dict())

    assert restored.emergency_latched()
    assert restored.get_state().emergency_declared_at == "2026-01-01T00:00:00+00:00"
    assert restored.get_state().emergency_cleared_at is None

    original.clear_emergency(at="2026-01-01T00:05:00+00:00")

    cleared = ContextManager()
    cleared.restore_from(original.to_dict())

    assert not cleared.emergency_latched()


def test_a_default_state_round_trips():
    original = ContextManager()

    restored = ContextManager()
    restored.restore_from(original.to_dict())

    assert restored.to_dict() == original.to_dict()


# ==============================================================
# STRICT VALIDATION - NOTHING IS PARTIALLY APPLIED
# ==============================================================


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_room", "KITCHEN"),
        ("current_mode", "PARTY"),
        ("location_status", "PROBABLY"),
        ("location_destination", "GARAGE"),
        ("return_target", "ATTIC"),
        ("drawing_light", "DIM"),
        ("exit_door", "AJAR"),
        ("buzzer", "LOUD"),
    ],
)
def test_an_unrecognised_enum_is_rejected(field, value):
    data = ContextManager().to_dict()
    data[field] = value

    with pytest.raises(StateRestoreError) as raised:
        ContextManager().restore_from(data)

    assert field in str(raised.value)


def test_an_unrecognised_room_enum_is_rejected():
    data = ContextManager().to_dict()
    data["rooms"]["sleep"]["bed"] = "FLUFFED"

    with pytest.raises(StateRestoreError):
        ContextManager().restore_from(data)


@pytest.mark.parametrize(
    "field", ["current_room", "current_mode", "location_status", "buzzer"]
)
def test_a_missing_required_field_is_rejected(field):
    data = ContextManager().to_dict()
    del data[field]

    with pytest.raises(StateRestoreError):
        ContextManager().restore_from(data)


def test_a_missing_room_section_is_rejected():
    data = ContextManager().to_dict()
    del data["rooms"]["relax"]

    with pytest.raises(StateRestoreError):
        ContextManager().restore_from(data)


def test_a_wrong_field_type_is_rejected():
    data = ContextManager().to_dict()
    data["location_reason"] = 42

    with pytest.raises(StateRestoreError):
        ContextManager().restore_from(data)


def test_a_rejected_restore_leaves_the_live_state_untouched():
    context = ContextManager()
    context.confirm_location(Room.MEAL_ROOM)
    context.set_mode(Mode.MEAL)

    before = context.to_dict()

    broken = ContextManager().to_dict()
    broken["current_room"] = "KITCHEN"

    with pytest.raises(StateRestoreError):
        context.restore_from(broken)

    # Not a single field of the half-parsed document was adopted.
    assert context.to_dict() == before


# ==============================================================
# 4-6  ATOMIC SNAPSHOT STORAGE
# ==============================================================


def test_a_snapshot_is_valid_json_with_metadata(repository):
    repository.save_snapshot(populated().to_dict(), clean_shutdown=True)

    document = json.loads(repository.snapshot_path.read_text(encoding="utf-8"))

    assert document["schema_version"] == SCHEMA_VERSION
    assert document["application_version"]
    assert document["saved_at"]
    assert document["clean_shutdown"] is True
    assert document["state"]["current_room"] == "SLEEP_ROOM"


def test_the_previous_snapshot_is_kept_as_a_backup(repository):
    repository.save_snapshot(ContextManager().to_dict())
    assert not repository.backup_path.exists()

    second = populated().to_dict()
    repository.save_snapshot(second)

    assert repository.backup_path.exists()

    backup = json.loads(repository.backup_path.read_text(encoding="utf-8"))
    assert backup["state"]["current_room"] == "OUTSIDE"

    assert repository.load_snapshot()["state"]["current_room"] == "SLEEP_ROOM"


def test_writing_leaves_no_temporary_files_behind(repository):
    for _ in range(3):
        repository.save_snapshot(ContextManager().to_dict())

    leftovers = [
        path.name
        for path in repository.directory.iterdir()
        if path.name.endswith(".tmp")
    ]

    assert leftovers == []


def test_a_failed_serialisation_never_damages_the_live_snapshot(repository):
    repository.save_snapshot(populated().to_dict())
    good = repository.snapshot_path.read_text(encoding="utf-8")

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        repository.save_snapshot({"broken": Unserialisable()})

    # The live file is byte-for-byte what it was.
    assert repository.snapshot_path.read_text(encoding="utf-8") == good
    assert repository.load_snapshot() is not None


# ==============================================================
# 7-10  SNAPSHOT VALIDATION
# ==============================================================


def test_a_missing_snapshot_is_simply_absent(repository):
    assert repository.load_snapshot() is None


def test_a_corrupt_snapshot_is_rejected(repository):
    repository.directory.mkdir(parents=True, exist_ok=True)
    repository.snapshot_path.write_text("{not json at all", encoding="utf-8")

    with pytest.raises(SnapshotError) as raised:
        repository.load_snapshot()

    assert "valid JSON" in str(raised.value)


def test_a_truncated_snapshot_is_rejected(repository):
    repository.save_snapshot(populated().to_dict())

    whole = repository.snapshot_path.read_text(encoding="utf-8")
    repository.snapshot_path.write_text(whole[: len(whole) // 2], encoding="utf-8")

    # There is a backup, but it is the pre-write state; with none
    # available the corruption must surface.
    repository.backup_path.unlink(missing_ok=True)

    with pytest.raises(SnapshotError):
        repository.load_snapshot()


def test_a_corrupt_snapshot_falls_back_to_the_backup(repository):
    repository.save_snapshot(ContextManager().to_dict())
    repository.save_snapshot(populated().to_dict())

    repository.snapshot_path.write_text("{ truncated", encoding="utf-8")

    document = repository.load_snapshot()

    assert document["recovered_from_backup"] is True
    assert document["state"]["current_room"] == "OUTSIDE"


def test_a_newer_schema_is_rejected_rather_than_guessed(repository):
    repository.save_snapshot(ContextManager().to_dict())

    document = json.loads(repository.snapshot_path.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION + 5
    repository.snapshot_path.write_text(json.dumps(document), encoding="utf-8")
    repository.backup_path.unlink(missing_ok=True)

    with pytest.raises(SnapshotError) as raised:
        repository.load_snapshot()

    assert "newer version" in str(raised.value)


def test_an_older_schema_without_a_migration_is_rejected(repository):
    repository.save_snapshot(ContextManager().to_dict())

    document = json.loads(repository.snapshot_path.read_text(encoding="utf-8"))
    document["schema_version"] = SCHEMA_VERSION - 1
    repository.snapshot_path.write_text(json.dumps(document), encoding="utf-8")
    repository.backup_path.unlink(missing_ok=True)

    with pytest.raises(SnapshotError) as raised:
        repository.load_snapshot()

    assert "no migration" in str(raised.value)


@pytest.mark.parametrize(
    "document",
    [
        {"state": {}},
        {"schema_version": "one", "state": {}},
        {"schema_version": SCHEMA_VERSION},
        {"schema_version": SCHEMA_VERSION, "state": "not an object"},
        [1, 2, 3],
    ],
)
def test_a_structurally_invalid_snapshot_is_rejected(repository, document):
    repository.directory.mkdir(parents=True, exist_ok=True)
    repository.snapshot_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SnapshotError):
        repository.load_snapshot()


# ==============================================================
# 11-15  EVENT LOG
# ==============================================================


def test_an_event_is_one_json_line(repository):
    repository.append_event({"event_type": "action_acknowledged", "device": "buzzer"})
    repository.append_event({"event_type": "action_acknowledged", "device": "exit_door"})

    lines = repository.event_log_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["device"] == "buzzer"
    assert json.loads(lines[1])["device"] == "exit_door"


def test_every_event_is_timestamped(repository):
    record = repository.append_event({"event_type": "action_acknowledged"})

    assert record["timestamp"]
    assert repository.load_events()[0]["timestamp"] == record["timestamp"]


def test_the_log_is_append_only(repository):
    repository.append_event({"n": 1})
    first = repository.event_log_path.read_text(encoding="utf-8")

    repository.append_event({"n": 2})
    second = repository.event_log_path.read_text(encoding="utf-8")

    # The earlier content is still there, unchanged, at the front.
    assert second.startswith(first)
    assert [event["n"] for event in repository.load_events()] == [1, 2]


def test_a_truncated_final_line_is_tolerated(repository):
    repository.append_event({"n": 1})
    repository.append_event({"n": 2})

    with open(repository.event_log_path, "a", encoding="utf-8") as handle:
        handle.write('{"n": 3, "device": "sleep_')

    events = repository.load_events()

    # The complete records survive; the partial one is discarded.
    assert [event["n"] for event in events] == [1, 2]


def test_an_absent_log_reads_as_empty(repository):
    assert repository.load_events() == []
