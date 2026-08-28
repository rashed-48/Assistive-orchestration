"""Durable storage for the logical world state.

The only component in the project that knows how state reaches a disk.
It records and returns data; it makes no decisions. It never plans a
workflow, never publishes MQTT, and never decides where anyone is.

Two artefacts:

    snapshot   one JSON object, the whole EnvironmentState plus the
               metadata needed to judge how far it can be trusted
    events     append-only JSONL, one line per acknowledged action,
               an audit trail rather than a source of truth

Snapshot writes are atomic: serialise, write a temporary file in the
same directory, flush, fsync, then os.replace(). A crash mid-write
therefore leaves either the old snapshot or the new one, never half of
either. The previous snapshot is kept alongside as .bak.

Loading is strict on purpose. A snapshot that cannot be fully
understood is rejected rather than partially applied - a half-restored
world is more dangerous than a fresh one, because it looks valid.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# Bumped whenever the persisted shape of EnvironmentState changes.
SCHEMA_VERSION = 1

APPLICATION_VERSION = "0.10.0"

SNAPSHOT_NAME = "state.json"
EVENT_LOG_NAME = "events.jsonl"


class SnapshotError(Exception):
    """A persisted snapshot could not be trusted and was rejected."""


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class StateRepository:
    """Reads and writes the snapshot and the event log."""

    def __init__(self, directory, snapshot_name=SNAPSHOT_NAME,
                 event_log_name=EVENT_LOG_NAME):
        self.directory = Path(directory)
        self.snapshot_path = self.directory / snapshot_name
        self.backup_path = self.snapshot_path.with_suffix(
            self.snapshot_path.suffix + ".bak"
        )
        self.event_log_path = self.directory / event_log_name

    # ==========================================================
    # SNAPSHOT
    # ==========================================================

    def save_snapshot(self, state, clean_shutdown=False, extra=None):
        """Write the whole state atomically, keeping one backup."""

        document = {
            "schema_version": SCHEMA_VERSION,
            "application_version": APPLICATION_VERSION,
            "saved_at": _utc_now(),
            "clean_shutdown": bool(clean_shutdown),
            "state": state,
        }

        if extra:
            document.update(extra)

        self.directory.mkdir(parents=True, exist_ok=True)

        # Keep the previous good snapshot before replacing it.
        if self.snapshot_path.exists():
            try:
                self.backup_path.write_bytes(self.snapshot_path.read_bytes())
            except OSError:
                # A missing backup must never stop the live save.
                pass

        self._write_atomically(
            self.snapshot_path,
            json.dumps(document, indent=2, sort_keys=True),
        )

        return document

    def load_snapshot(self, allow_backup=True):
        """Return a validated snapshot, or None if there is nothing usable.

        Raises SnapshotError only when a file exists but cannot be
        trusted and no usable backup is available.
        """

        if not self.snapshot_path.exists():
            return None

        try:
            return self._read_snapshot(self.snapshot_path)

        except SnapshotError as error:
            if not (allow_backup and self.backup_path.exists()):
                raise

            try:
                document = self._read_snapshot(self.backup_path)
            except SnapshotError:
                raise error

            document["recovered_from_backup"] = True
            return document

    def _read_snapshot(self, path):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as error:
            raise SnapshotError(f"{path.name} could not be read: {error}")

        try:
            document = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as error:
            raise SnapshotError(
                f"{path.name} is not valid JSON (corrupt or truncated): {error}"
            )

        if not isinstance(document, dict):
            raise SnapshotError(f"{path.name} is not a JSON object")

        version = document.get("schema_version")

        if version is None:
            raise SnapshotError(f"{path.name} has no schema_version")

        if not isinstance(version, int):
            raise SnapshotError(
                f"{path.name} has a non-integer schema_version {version!r}"
            )

        if version > SCHEMA_VERSION:
            raise SnapshotError(
                f"{path.name} was written by a newer version "
                f"(schema {version}, this build understands {SCHEMA_VERSION}). "
                f"Refusing to guess."
            )

        if version < SCHEMA_VERSION:
            # No migrations exist yet. Say so rather than guessing.
            raise SnapshotError(
                f"{path.name} uses schema {version}; no migration to "
                f"{SCHEMA_VERSION} exists."
            )

        if not isinstance(document.get("state"), dict):
            raise SnapshotError(f"{path.name} has no state object")

        return document

    @staticmethod
    def _write_atomically(path, text):
        directory = path.parent

        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        )

        try:
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(handle.name, path)

        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise

    # ==========================================================
    # EVENT LOG
    # ==========================================================

    def append_event(self, event):
        """Append one JSON object as a line. Never rewrites history."""

        record = dict(event)
        record.setdefault("timestamp", _utc_now())

        self.directory.mkdir(parents=True, exist_ok=True)

        with open(self.event_log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        return record

    def load_events(self):
        """Read every complete event.

        A process killed mid-append leaves a partial final line. That
        line is discarded: the log is an audit trail, and one lost
        record must not make the rest unreadable.
        """

        if not self.event_log_path.exists():
            return []

        events = []

        for line in self.event_log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if not line:
                continue

            try:
                events.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                # Only the last line can legitimately be partial.
                continue

        return events
