"""Continuous console runtime for the voice assistant.

This module is the continuous *driver*. It owns nothing but the loop:

    ConsoleAssistant          drives the lifecycle - listen, confirm, repeat
      VoiceController         speech -> text -> intent  (built once)
      ApplicationRuntime      the long-lived world
        ContextManager        the logical state, created once
        Orchestrator          the dependency-aware decision authority
          WorkflowEngine      plans from the CURRENT state
          TransitionBuilder   room/device dependencies
        MQTTDeviceExecutor    physical execution
        MQTTClient           one connection for the whole session

No dependency reasoning happens here. Every command is handed to
Orchestrator.execute_intent(), which plans against whatever state the
previous command committed. That is what makes the second "I want to
sleep" cost two actions instead of eight: nothing in this file knows
about rooms.

The web interface (app/web/server.py) already drove the same
ApplicationRuntime continuously across HTTP requests. This gives the
console the same property, so voice and web are two front ends onto one
persistent world.
"""

from app.intent import DEFAULT_SIMILARITY_THRESHOLD
from app.orchestration.orchestrator import LocationUnknown
from app.orchestration.state import Room
from app.runtime import (
    DEFAULT_BROKER_HOST,
    DEFAULT_BROKER_PORT,
    ApplicationRuntime,
    EmergencyActive,
    IntentNotSupported,
    TransportUnavailable,
)


DEFAULT_CLIENT_ID = "assistive_console"

EXIT_WORDS = {"q", "quit", "exit", "stop"}

# Typed at the prompt to resolve an unknown location, e.g. "where sleep".
# Deliberately a typed command rather than a spoken intent: adding an
# intent would mean changing the recognition dataset, which is out of
# scope for this phase.
WHERE_PREFIX = "where"

ROOM_WORDS = {
    "outside": Room.OUTSIDE,
    "drawing": Room.DRAWING_ROOM,
    "study": Room.STUDY_ROOM,
    "relax": Room.RELAX_ROOM,
    "sleep": Room.SLEEP_ROOM,
    "meal": Room.MEAL_ROOM,
}


class ConsoleAssistant:
    """Accepts spoken commands repeatedly against one logical world."""

    def __init__(
        self,
        runtime=None,
        controller=None,
        confirm=None,
        prompt=input,
        intent_file="data/intents.csv",
        whisper_model="base",
        broker_host=DEFAULT_BROKER_HOST,
        broker_port=DEFAULT_BROKER_PORT,
    ):
        # Built once. Rebuilding either of these per command would
        # reload Whisper and a sentence-transformer, and - far worse -
        # would reset the logical state to OUTSIDE every time.
        self.runtime = runtime or ApplicationRuntime(
            broker_host=broker_host,
            broker_port=broker_port,
            client_id=DEFAULT_CLIENT_ID,
        )

        self._owns_controller = controller is None
        self._controller = controller
        self._controller_settings = {
            "intent_file": intent_file,
            "whisper_model": whisper_model,
            "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        }

        self._confirm = confirm
        self._prompt = prompt

        self.commands_handled = 0

    # ==========================================================
    # LAZY COMPONENTS
    # ==========================================================

    @property
    def controller(self):
        """Built on first use, then reused for the whole session."""

        if self._controller is None:
            from app.voice.controller import VoiceController

            self._controller = VoiceController(**self._controller_settings)

        return self._controller

    def confirm(self, result):
        if self._confirm is not None:
            return self._confirm(result)

        return self.controller.confirm_intent(result)

    # ==========================================================
    # ONE COMMAND
    # ==========================================================

    def handle_result(self, result):
        """Take one recognition result through to execution.

        Returns an outcome record. Nothing on any path resets the
        logical state: an unrecognised utterance, a declined
        confirmation and a failed workflow all leave the world exactly
        as the previous command left it.
        """

        self.commands_handled += 1

        intent = result.get("intent")

        if result.get("decision") != "PREDICTED" or not intent:
            return self._outcome("unrecognised", None)

        if not self.runtime.is_supported(intent):
            return self._outcome("unsupported", intent)

        # Ask before acting, but say up front when the environment will
        # refuse the command anyway.
        if not self.runtime.is_allowed_now(intent):
            return self._outcome(
                "blocked",
                intent,
                error=(
                    f"{intent} is not available right now."
                    + (
                        " The environment is in emergency."
                        if self.runtime.emergency_active()
                        else ""
                    )
                ),
            )

        if not self.confirm(result):
            return self._outcome("declined", intent)

        try:
            results = self.runtime.execute_intent(intent)

        except EmergencyActive as error:
            return self._outcome("blocked", intent, error=str(error))

        except IntentNotSupported:
            return self._outcome("unsupported", intent)

        except LocationUnknown as error:
            return self._outcome("location_unknown", intent, error=str(error))

        except TransportUnavailable as error:
            return self._outcome("transport", intent, error=str(error))

        except Exception as error:
            # One failed command must not end the session. The
            # Orchestrator has already decided what, if anything, was
            # committed; the state below is the truthful one.
            return self._outcome("failed", intent, error=str(error))

        failed = [r for r in results if r.get("status") != "success"]

        return self._outcome(
            "degraded" if failed else "executed",
            intent,
            actions=results,
            failed_actions=len(failed),
        )

    def _outcome(self, outcome, intent, **extra):
        record = {
            "outcome": outcome,
            "intent": intent,
            "state": self.runtime.state_snapshot(),
        }
        record.update(extra)
        return record

    # ==========================================================
    # ONE TURN OF THE LOOP
    # ==========================================================

    def listen(self):
        """Record and recognise one utterance. None if nothing usable."""

        heard = self.controller.process()

        if heard is None:
            return None

        text, result = heard
        self.controller.show_result(text, result)

        return result

    def run_once(self):
        result = self.listen()

        if result is None:
            print("\nNo usable command received.")
            return self._outcome("unrecognised", None)

        outcome = self.handle_result(result)
        self.report(outcome)

        return outcome

    # ==========================================================
    # REPORTING
    # ==========================================================

    def report(self, outcome):
        kind = outcome["outcome"]
        intent = outcome["intent"]

        print("\n" + "=" * 70)

        if kind == "executed":
            print(
                f"COMPLETED  {intent}  "
                f"({len(outcome['actions'])} device actions acknowledged)"
            )
        elif kind == "degraded":
            print(
                f"DEGRADED   {intent}  "
                f"({outcome['failed_actions']} of "
                f"{len(outcome['actions'])} device actions failed)"
            )
        elif kind == "blocked":
            print(f"BLOCKED    {outcome.get('error')}")
        elif kind == "declined":
            print(f"CANCELLED  {intent} was not confirmed")
        elif kind == "unsupported":
            print(f"NO WORKFLOW for {intent}")
        elif kind == "location_unknown":
            print(f"LOCATION UNKNOWN  {outcome.get('error')}")
            print(
                "           Type 'where <room>' to confirm where you are, "
                "e.g. 'where sleep'."
            )
        elif kind == "transport":
            print(f"NO BROKER  {outcome.get('error')}")
        elif kind == "failed":
            print(f"FAILED     {intent}: {outcome.get('error')}")
        else:
            print("NOT RECOGNIZED  please try again")

        print("=" * 70)

        # The state after every command, successful or not.
        self.runtime.context.print_state()

    # ==========================================================
    # THE CONTINUOUS LOOP
    # ==========================================================

    def run(self):
        """Accept commands until the operator ends the session.

        SHUTDOWN_ENVIRONMENT is a physical workflow that powers the
        house down and moves the user OUTSIDE. It is deliberately NOT
        wired to process exit: the assistant keeps listening afterwards,
        exactly as it does after any other command.
        """

        print("\n" + "=" * 70)
        print("ASSISTIVE ORCHESTRATION - CONTINUOUS RUNTIME")
        print("=" * 70)
        print(f"MQTT connected : {self.runtime.connected}")
        if self.runtime.connection_error:
            print(f"MQTT error     : {self.runtime.connection_error}")

        # What the previous session left behind, and how far it is being
        # trusted. Silent when there is nothing to report.
        recovery = self.runtime.recovery.lines()

        if recovery:
            print()
            for line in recovery:
                print(line)

        print("\nStarting state:")
        self.runtime.context.print_state()

        try:
            while True:
                print("\n" + "-" * 70)
                print("Press ENTER to speak, or type q to end the session.")

                try:
                    answer = self._prompt("> ")
                except (EOFError, KeyboardInterrupt):
                    print("\nEnding session.")
                    break

                answer = answer.strip()

                if answer.lower() in EXIT_WORDS:
                    print("\nEnding session.")
                    break

                if answer.lower().startswith(WHERE_PREFIX):
                    self.resolve_location(answer)
                    continue

                try:
                    self.run_once()
                except KeyboardInterrupt:
                    print("\nCommand interrupted. The session is still running.")
                except Exception as error:
                    # The loop outlives any single command.
                    print(f"\nUnexpected error while handling a command: {error}")

        finally:
            self.shutdown()

    def resolve_location(self, answer):
        """Let the operator state where the person actually is.

        The system cannot sense location, so when it loses track the
        only honest source is a person telling it. This is the recovery
        path out of UNKNOWN and the reason UNKNOWN is not a dead end.
        """

        word = answer.split()[1].lower() if len(answer.split()) > 1 else ""

        room = ROOM_WORDS.get(word)

        if room is None:
            print(
                f"\nUnknown room {word!r}. "
                f"Use one of: {', '.join(sorted(ROOM_WORDS))}."
            )
            return None

        self.runtime.context.confirm_location(room)

        print(f"\nLocation confirmed: {room.value}")
        self.runtime.context.print_state()

        return room

    def shutdown(self):
        """Leave the broker once, at the end of the session."""

        self.runtime.shutdown()


def main(broker_host=DEFAULT_BROKER_HOST, broker_port=DEFAULT_BROKER_PORT):
    assistant = ConsoleAssistant(
        broker_host=broker_host,
        broker_port=broker_port,
    )

    assistant.runtime.connect()
    assistant.run()
