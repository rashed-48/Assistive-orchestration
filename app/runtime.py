"""Application-scoped orchestration runtime.

One runtime holds the authoritative objects for the life of the process:

    ApplicationRuntime
        +-- ContextManager      authoritative logical state
        +-- MQTTClient          one connection, one status listener
        +-- MQTTDeviceExecutor  transport and acknowledgement
        +-- Orchestrator        the only workflow execution entry point

Every confirmed command - from the web interface or from the console voice
loop - goes through the same runtime, so the state one command commits is
the state the next command plans against.

The runtime adds no orchestration logic of its own. It owns object
lifetime and serialises access; planning stays in WorkflowEngine and state
authority stays with Orchestrator/ContextManager.
"""

import threading
from pathlib import Path

from app.devices.mqtt_client import MQTTClient
from app.devices.mqtt_device import MQTTDeviceExecutor
from app.orchestration.context_manager import (
    ContextManager,
    StateRestoreError,
)
from app.orchestration.state import LocationStatus, Mode
from app.discovery import BrokerBeacon
from app.persistence import SnapshotError, StateRepository
from app.orchestration.orchestrator import EmergencyActive, Orchestrator


__all__ = [
    "ApplicationRuntime",
    "RecoveryReport",
    "EmergencyActive",
    "IntentNotSupported",
    "TransportUnavailable",
    "DEFAULT_BROKER_HOST",
    "DEFAULT_BROKER_PORT",
]


DEFAULT_BROKER_HOST = "localhost"
DEFAULT_BROKER_PORT = 1883
DEFAULT_CLIENT_ID = "assistive_web"

# Runtime state lives beside the code but is never committed.
DEFAULT_STATE_DIRECTORY = Path("var")


class RecoveryReport:
    """What the runtime found on disk, and how far it decided to trust it."""

    def __init__(self):
        self.restored = False
        self.clean_shutdown = None
        self.saved_at = None
        self.recovered_from_backup = False
        self.rejected_reason = None
        self.location_downgraded = False
        self.last_known_room = None
        self.interrupted_destination = None
        self.location_reason = None
        self.emergency_latched = False

    def as_dict(self):
        return {
            "restored": self.restored,
            "clean_shutdown": self.clean_shutdown,
            "saved_at": self.saved_at,
            "recovered_from_backup": self.recovered_from_backup,
            "rejected_reason": self.rejected_reason,
            "location_downgraded": self.location_downgraded,
            "last_known_room": self.last_known_room,
            "interrupted_destination": self.interrupted_destination,
            "location_reason": self.location_reason,
            "emergency_latched": self.emergency_latched,
        }

    def lines(self):
        """Operator-facing summary. Empty when there is nothing to report."""

        if self.rejected_reason:
            return [
                "Previous state could not be trusted and was discarded:",
                f"  {self.rejected_reason}",
                "Starting from a fresh environment.",
            ]

        if not self.restored:
            return []

        out = [f"Restored from a previous session (saved {self.saved_at})."]

        if self.recovered_from_backup:
            out.append("  The main snapshot was unreadable; the backup was used.")

        if self.location_downgraded:
            out.append(
                "  Location is UNVERIFIED - the system does not know where you are."
            )
            if self.last_known_room:
                out.append(f"    Last known room     : {self.last_known_room}")
            if self.interrupted_destination:
                out.append(
                    f"    Interrupted heading : {self.interrupted_destination}"
                )
            if self.location_reason:
                out.append(f"    Reason              : {self.location_reason}")
            out.append(
                "    Confirm the location before issuing a movement command."
            )

        if self.emergency_latched:
            out.append("  EMERGENCY latched from the previous session.")
            out.append(
                "    Hardware state is UNVERIFIED - nothing was re-actuated."
            )
            out.append(
                "    Normal commands are blocked until the emergency is cleared."
            )

        return out


class IntentNotSupported(Exception):
    """The requested intent has no workflow."""


class TransportUnavailable(Exception):
    """The runtime has no usable connection to the broker."""


class ApplicationRuntime:

    def __init__(
        self,
        broker_host=DEFAULT_BROKER_HOST,
        broker_port=DEFAULT_BROKER_PORT,
        client_id=DEFAULT_CLIENT_ID,
        context=None,
        device_executor=None,
        mqtt_client=None,
        repository=None,
        state_directory=None,
        persist=True,
        announce_broker=False,
    ):

        self.context = context or ContextManager()

        # Nodes carry no broker address of their own; the host says
        # where it is. Off by default so tests stay off the network.
        self.beacon = (
            BrokerBeacon(broker_port=broker_port)
            if announce_broker else None
        )

        # Persistence is opt-out so tests stay filesystem-free by default.
        if repository is not None:
            self.repository = repository
        elif persist:
            self.repository = StateRepository(
                state_directory or DEFAULT_STATE_DIRECTORY
            )
        else:
            self.repository = None

        self.recovery = RecoveryReport()

        if self.repository is not None:
            self._restore()

        # A device executor may be injected so the orchestration path can
        # be exercised without a broker. Production uses MQTT.
        if device_executor is None:

            self.mqtt_client = mqtt_client or MQTTClient(
                broker_host=broker_host,
                broker_port=broker_port,
                client_id=client_id,
            )

            self.device_executor = MQTTDeviceExecutor(
                self.mqtt_client
            )

        else:

            self.mqtt_client = mqtt_client
            self.device_executor = device_executor

        self.orchestrator = Orchestrator(
            context=self.context,
            device_executor=self.device_executor,
            action_observer=self._record_action,
        )

        # Workflows actuate doors and lights. Serialise them so two
        # confirmations cannot interleave against one environment.
        self._execution_lock = threading.Lock()

        self._pending_lock = threading.Lock()
        self._pending_intent = None

        self.connected = False
        self.connection_error = None

        # Mark the stored snapshot as belonging to a running session, so
        # a crash cannot later be mistaken for a clean exit.
        if self.repository is not None:
            self._save_snapshot(clean_shutdown=False)

    # ==========================================================
    # PERSISTENCE
    #
    # The runtime owns durability. ContextManager stays unaware of the
    # filesystem, and the Orchestrator only reports acknowledged actions
    # through an observer callback.
    # ==========================================================

    def _restore(self):
        """Load the previous session and decide how far to trust it."""

        try:
            document = self.repository.load_snapshot()
        except SnapshotError as error:
            self.recovery.rejected_reason = str(error)
            print(f"[RUNTIME] Rejected stored state: {error}")
            return

        if document is None:
            return

        try:
            self.context.restore_from(document["state"])
        except StateRestoreError as error:
            self.recovery.rejected_reason = str(error)
            print(f"[RUNTIME] Rejected stored state: {error}")
            return

        self.recovery.restored = True
        self.recovery.clean_shutdown = document.get("clean_shutdown")
        self.recovery.saved_at = document.get("saved_at")
        self.recovery.recovered_from_backup = document.get(
            "recovered_from_backup", False
        )

        self._apply_recovery_policy()

    def _apply_recovery_policy(self):
        """Phase 10A location semantics, applied across a restart.

        A stored location is still a fact only if the previous session
        ended cleanly and was not part way through a move. Anything else
        becomes UNKNOWN, keeping the last known room and the interrupted
        destination so the operator can see what happened.
        """

        state = self.context.get_state()

        self.recovery.last_known_room = state.current_room.value
        self.recovery.interrupted_destination = (
            state.location_destination.value
            if state.location_destination
            else None
        )

        status = state.location_status
        clean = self.recovery.clean_shutdown

        if status == LocationStatus.KNOWN and clean:
            reason = None
        elif status == LocationStatus.KNOWN and self._nothing_happened():
            # The previous session ended badly, but it had not committed
            # anything: the stored world is identical to a brand-new one.
            # There is no stale claim to distrust, so warning here would
            # be noise, and would leave a first-time user locked out of
            # every command for no reason.
            reason = None
        elif status == LocationStatus.KNOWN:
            reason = "the previous session ended unexpectedly"
        elif status == LocationStatus.IN_TRANSIT:
            reason = (
                f"the previous session was interrupted moving from "
                f"{state.current_room.value} to "
                f"{self.recovery.interrupted_destination}"
            )
        else:
            reason = state.location_reason or "the location was already unknown"

        if reason is not None:
            self.context.mark_location_unknown(reason=reason)
            self.recovery.location_downgraded = True
            self.recovery.location_reason = reason

        # An emergency declared and never cleared outlives the process.
        # Restore the latch only - never the actuators.
        if self.context.emergency_latched():
            self.context.set_mode(Mode.EMERGENCY)
            self.recovery.emergency_latched = True

    def _nothing_happened(self):
        """Is the restored world indistinguishable from a fresh one?

        Every workflow that moves the person leaves a trace: a room, a
        mode, a return target, or a device out of its resting state. If
        none of that is present, no command ever committed, and treating
        the location as unknown would express doubt about a fact the
        system never asserted.

        Deliberately a whole-state comparison rather than a room check:
        LEAVE_ROOM and SHUTDOWN_ENVIRONMENT both end OUTSIDE but set a
        return target, so they are correctly still treated as history.
        """

        return self.context.to_dict() == ContextManager().to_dict()

    def _save_snapshot(self, clean_shutdown=False):
        if self.repository is None:
            return None

        try:
            return self.repository.save_snapshot(
                self.context.to_dict(),
                clean_shutdown=clean_shutdown,
            )
        except OSError as error:
            print(f"[RUNTIME] Could not save state: {error}")
            return None

    def _record_action(self, intent, action, result):
        """Append one audit line for an acknowledged, committed action.

        An audit trail, never a replay queue. Nothing in this project
        re-issues an action from the log, which is what keeps the
        non-idempotent ACTIVATE_MEDICATION safe.
        """

        if self.repository is None:
            return

        self.repository.append_event(
            {
                "event_type": "action_acknowledged",
                "intent": intent,
                "device": action.device_id,
                "action": action.action_type.value,
                "command_id": result.get("command_id"),
                "node": result.get("node"),
                "status": result.get("status"),
                "resulting_state": self.context.to_dict(),
            }
        )

    # ==========================================================
    # SUPPORTED INTENTS
    # ==========================================================

    @property
    def supported_intents(self):
        return sorted(self.orchestrator.workflow_map)

    def is_supported(self, intent):
        return intent in self.orchestrator.workflow_map

    # ==========================================================
    # EMERGENCY LATCH
    #
    # The policy itself lives in the Orchestrator. These are read
    # only views, so an interface can grey out a command instead of
    # offering one that will be refused.
    # ==========================================================

    def emergency_active(self):
        return self.context.get_current_mode() == Mode.EMERGENCY

    def is_allowed_now(self, intent):

        if not self.is_supported(intent):
            return False

        if (
            self.emergency_active()
            and intent not in Orchestrator.EMERGENCY_INTENTS
        ):
            return False

        if (
            intent == "EMERGENCY_CLEAR"
            and not self.emergency_active()
        ):
            return False

        return True

    # ==========================================================
    # PENDING CONFIRMATION
    #
    # A predicted intent is held here until the user confirms it, so a
    # confirmation can only execute something the system actually
    # proposed.
    # ==========================================================

    def set_pending_intent(self, intent):
        with self._pending_lock:
            self._pending_intent = intent

    def get_pending_intent(self):
        with self._pending_lock:
            return self._pending_intent

    def clear_pending_intent(self):
        with self._pending_lock:
            self._pending_intent = None

    # ==========================================================
    # MQTT LIFECYCLE
    # ==========================================================

    def connect(self):
        """Connect once, and stay connected for the process lifetime.

        A broker that is down must not stop the application booting, so
        the failure is recorded and reported by the endpoints that need
        transport rather than raised here.
        """

        if self.beacon is not None:
            # Announce before connecting: a node that boots first
            # should not have to wait out its discovery window.
            self.beacon.start()

        if self.mqtt_client is None or self.connected:
            return self.connected

        try:

            self.mqtt_client.connect()

            self.connected = True
            self.connection_error = None

        except Exception as error:

            self.connected = False
            self.connection_error = str(error)

            print(
                f"[RUNTIME] MQTT connection failed: {error}"
            )

        return self.connected

    def shutdown(self):
        """End the session: record a clean exit, then leave the broker."""

        self._save_snapshot(clean_shutdown=True)

        if self.beacon is not None:
            self.beacon.stop()

        if self.mqtt_client is None or not self.connected:
            return

        try:
            self.mqtt_client.disconnect()
        finally:
            self.connected = False

    # ==========================================================
    # EXECUTION
    # ==========================================================

    def execute_intent(self, intent):
        """Run a confirmed intent through the authoritative path.

        This is a thin, serialised delegation to
        Orchestrator.execute_intent(). The runtime never builds an action
        plan and never talks to the executor directly.
        """

        if not self.is_supported(intent):
            raise IntentNotSupported(intent)

        if self.mqtt_client is not None and not self.connected:
            raise TransportUnavailable(
                self.connection_error
                or "The application is not connected to the MQTT broker."
            )

        with self._execution_lock:
            try:
                return self.orchestrator.execute_intent(intent)
            finally:
                # Device state commits per acknowledged action even when
                # a workflow aborts, so the snapshot is taken either way.
                self._save_snapshot(clean_shutdown=False)

    # ==========================================================
    # PRESENTATION
    # ==========================================================

    def state_snapshot(self):
        """Authoritative logical state, plus how to reach it."""

        return {
            "environment": self.context.to_dict(),
            "supported_intents": self.supported_intents,
            "pending_intent": self.get_pending_intent(),
            "emergency_active": self.emergency_active(),
            "recovery": self.recovery.as_dict(),
            "mqtt": {
                "connected": self.connected,
                "error": self.connection_error,
            },
        }
