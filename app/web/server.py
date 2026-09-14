import json
import os
from pathlib import Path
import threading

from flask import Flask, Response, jsonify, render_template, request

from app.web.events import EventBus
from app.web.wire import WireObserver

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


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INTENT_DATASET = PROJECT_ROOT / "data" / "intents.csv"
RECORDING_PATH = PROJECT_ROOT / "command.wav"


# Settings used to build the application's default VoiceController.
#
# Kept as a named constant so a test can prove they still match the
# controller's signature without paying for a model load. They drifted apart
# once already: the web layer went on passing margin_threshold and
# max_clarification_attempts after the ambiguity API was retired, and the
# application stopped booting.
DEFAULT_CONTROLLER_SETTINGS = {
    "intent_file": str(INTENT_DATASET),
    "whisper_model": "base",
    # Sourced from the recognizer so the application, the library
    # default, and the automated measurements cannot drift apart again.
    "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
}


def create_app(controller=None, runtime=None):
    """Build the Flask application.

    controller and runtime are injectable so the HTTP layer can be tested
    without loading Whisper, a sentence-transformer, or a broker.
    Production callers omit both.

    The runtime is application scoped: one ContextManager, one MQTT
    connection, one Orchestrator for the life of the process, so state
    committed by one command is visible to the next.
    """

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    if controller is None:
        # Imported here rather than at module scope: building the default
        # controller loads Whisper and a sentence-transformer, and callers
        # that inject their own must not pay for that.
        from app.voice.controller import VoiceController

        controller = VoiceController(**DEFAULT_CONTROLLER_SETTINGS)

    if runtime is None:
        # The broker address is configurable so the application can be
        # pointed at a test broker without editing code.
        runtime = ApplicationRuntime(
            broker_host=os.environ.get(
                "ASSISTIVE_BROKER_HOST",
                DEFAULT_BROKER_HOST,
            ),
            broker_port=int(
                os.environ.get(
                    "ASSISTIVE_BROKER_PORT",
                    DEFAULT_BROKER_PORT,
                )
            ),
            # Nodes discover the broker rather than carrying its
            # address, so a demo on a phone hotspot needs no reflash.
            announce_broker=True,
        )
        runtime.connect()

    app.runtime = runtime

    # ----------------------------------------------------------
    # LIVE VIEW
    #
    # Everything the interface animates comes from one ordered event
    # stream. Speech and recognition are emitted here; the plan and
    # each commit come from the orchestrator's observer seams; and
    # every command, acknowledgement and completion comes from a
    # separate subscriber watching the bus itself, so what the browser
    # shows is what actually crossed the wire.
    # ----------------------------------------------------------

    bus = EventBus()
    app.events = bus

    wire = None
    mqtt_client = getattr(runtime, "mqtt_client", None)
    if mqtt_client is not None and getattr(mqtt_client, "broker_host", None):
        wire = WireObserver(
            bus,
            broker_host=mqtt_client.broker_host,
            broker_port=getattr(mqtt_client, "broker_port", 1883),
        ).start()
    app.wire = wire

    orchestrator = getattr(runtime, "orchestrator", None)
    if orchestrator is not None:

        def announce_plan(intent, actions):
            bus.emit(
                "plan",
                intent=intent,
                actions=[
                    {"index": i, "device": a.device_id,
                     "action": a.action_type.value}
                    for i, a in enumerate(actions, start=1)
                ],
            )

        orchestrator.plan_observer = announce_plan

        # Persistence already listens here. Chain rather than replace,
        # so recording a commit and displaying it cannot drift apart.
        previous = orchestrator.action_observer

        def announce_commit(intent, action, result):
            if previous is not None:
                previous(intent, action, result)
            bus.emit(
                "commit",
                intent=intent,
                device=action.device_id,
                action=action.action_type.value,
                node=(result or {}).get("node"),
            )

        orchestrator.action_observer = announce_commit

    recording_lock = threading.Lock()
    state = {"recording": False}

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.post("/api/recording/start")
    def start_recording():
        with recording_lock:
            if state["recording"]:
                return jsonify({"error": "Recording is already in progress."}), 409

            try:
                controller.recorder.start_recording()
            except Exception as error:
                return jsonify({"error": f"Could not access the microphone: {error}"}), 500

            state["recording"] = True

        return jsonify({"status": "recording"})

    @app.post("/api/recording/stop")
    def stop_recording():
        with recording_lock:
            if not state["recording"]:
                return jsonify({"error": "There is no active recording."}), 409

            state["recording"] = False

        try:
            audio_path = controller.recorder.stop_recording(str(RECORDING_PATH))

            if audio_path is None:
                return jsonify({"error": "No audio was captured. Please try again."}), 422

            text = controller.transcriber.transcribe(audio_path).strip()

            if not text:
                return jsonify({"error": "No speech was detected. Please try again."}), 422

            bus.emit("speech", text=text)

            result = controller.recognizer.predict(text)
            result["transcription"] = text
            result["threshold"] = getattr(
                controller.recognizer, "similarity_threshold",
                DEFAULT_SIMILARITY_THRESHOLD,
            )

            bus.emit(
                "recognition",
                decision=result.get("decision"),
                intent=result.get("intent"),
                score=result.get("similarity_score"),
                threshold=result["threshold"],
                matched=result.get("matched_sentence"),
                top=result.get("top_results", []),
            )

            # The recognizer picks the best supported intent and reports
            # how confident it was. Deciding whether to run it is the
            # user's call, and executing it belongs to the orchestration
            # layer, not to this endpoint.
            if result["decision"] == "PREDICTED":

                intent = result["intent"]
                executable = runtime.is_allowed_now(intent)

                if executable:
                    runtime.set_pending_intent(intent)

                    result["message"] = (
                        "Best matching command. Confirm it to run the "
                        "workflow."
                    )

                elif not runtime.is_supported(intent):
                    runtime.clear_pending_intent()

                    result["message"] = (
                        f"{intent} was recognized but has no workflow, "
                        f"so it cannot be run."
                    )

                elif runtime.emergency_active():
                    runtime.clear_pending_intent()

                    result["message"] = (
                        f"The environment is in emergency, so {intent} "
                        f"is blocked. Clear the emergency first."
                    )

                else:
                    runtime.clear_pending_intent()

                    result["message"] = (
                        "There is no active emergency to clear."
                    )

                result["executable"] = executable

            else:
                runtime.clear_pending_intent()

                result["executable"] = False
                result["message"] = (
                    "This request did not match a supported command. "
                    "Please try again."
                )

            return jsonify(result)
        except Exception as error:
            return jsonify({"error": f"Command processing failed: {error}"}), 500

    # ==========================================================
    # CONFIRMATION
    #
    # The user has seen the predicted intent and accepted it. From
    # here the web layer only hands the intent to the runtime; it
    # never plans actions and never touches the device executor.
    # ==========================================================

    @app.post("/api/intent/confirm")
    def confirm_intent():

        payload = request.get_json(silent=True) or {}

        intent = payload.get("intent")
        pending = runtime.get_pending_intent()

        if not intent:
            return jsonify({"error": "No intent was supplied."}), 400

        if pending is None:
            return jsonify(
                {"error": "There is no predicted command awaiting confirmation."}
            ), 409

        if intent != pending:
            # Only the command the system actually proposed may run.
            return jsonify(
                {
                    "error": (
                        f"{intent} does not match the predicted command "
                        f"{pending}."
                    )
                }
            ), 409

        bus.emit("workflow_start", intent=intent)

        try:
            results = runtime.execute_intent(intent)

        except IntentNotSupported:
            runtime.clear_pending_intent()
            return jsonify(
                {"error": f"{intent} is not a supported workflow."}
            ), 400

        except LocationUnknown as error:
            runtime.clear_pending_intent()
            bus.emit("workflow_end", intent=intent, status="refused",
                     error=str(error))
            return jsonify(
                {
                    "status": "location_unknown",
                    "intent": intent,
                    "error": str(error),
                    "state": runtime.state_snapshot(),
                }
            ), 409

        except EmergencyActive as error:
            # The latch is checked again here, not only at prediction
            # time: nothing may slip through between the two.
            runtime.clear_pending_intent()
            bus.emit("workflow_end", intent=intent, status="blocked",
                     error=str(error))
            return jsonify(
                {
                    "status": "blocked",
                    "intent": intent,
                    "error": str(error),
                    "state": runtime.state_snapshot(),
                }
            ), 409

        except TransportUnavailable as error:
            return jsonify(
                {
                    "status": "failed",
                    "intent": intent,
                    "error": str(error),
                    "state": runtime.state_snapshot(),
                }
            ), 503

        except Exception as error:
            # The workflow stopped part way. Orchestrator deliberately
            # leaves room and mode uncommitted, so the state below is
            # the truthful one to show.
            runtime.clear_pending_intent()
            bus.emit("workflow_end", intent=intent, status="failed",
                     error=str(error))

            return jsonify(
                {
                    "status": "failed",
                    "intent": intent,
                    "error": str(error),
                    "state": runtime.state_snapshot(),
                }
            ), 502

        runtime.clear_pending_intent()

        # Safety workflows run best effort, so a completed call can
        # still contain failed actions. Say so rather than reporting a
        # clean success.
        failed = [
            result
            for result in results
            if result.get("status") != "success"
        ]

        bus.emit(
            "workflow_end",
            intent=intent,
            status="degraded" if failed else "executed",
            executed=len(results),
            failed=len(failed),
            state=runtime.state_snapshot(),
        )

        return jsonify(
            {
                "status": "degraded" if failed else "executed",
                "degraded": bool(failed),
                "failed_actions": len(failed),
                "intent": intent,
                "executed_actions": len(results),
                "actions": [
                    {
                        "device": result.get("device"),
                        "action": result.get("action"),
                        "status": result.get("status"),
                        "node": result.get("node"),
                    }
                    for result in results
                ],
                "state": runtime.state_snapshot(),
            }
        )

    # ==========================================================
    # LIVE EVENT STREAM
    # ==========================================================

    @app.get("/api/events")
    def event_stream():
        """Server-sent events. `since` resumes after a given sequence
        number, so a reconnecting client misses nothing."""

        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            since = 0

        def generate(cursor):
            # Anything the client has not seen yet goes out at once.
            for event in bus.since(cursor):
                cursor = event["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"

            while True:
                fresh = bus.wait_for(cursor, timeout=15.0)
                if not fresh:
                    # Keep the connection alive through proxies and
                    # let the browser know we are still here.
                    yield ": keepalive\n\n"
                    continue
                for event in fresh:
                    cursor = event["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"

        return Response(
            generate(since),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache",
                     "X-Accel-Buffering": "no"},
        )

    @app.get("/api/events/poll")
    def event_poll():
        """Plain polling alternative for clients without SSE."""

        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            since = 0
        return jsonify({"events": bus.since(since), "latest": bus.latest})

    @app.post("/api/nodes/probe")
    def probe_nodes():
        """Which nodes are answering right now. Nothing moves."""

        if wire is None:
            return jsonify({"nodes": {}, "note": "no broker in this configuration"})
        return jsonify({"nodes": wire.probe()})

    @app.post("/api/intent/cancel")
    def cancel_intent():

        runtime.clear_pending_intent()

        return jsonify({"status": "cancelled"})

    # ==========================================================
    # STATE VISIBILITY
    # ==========================================================

    @app.post("/api/location/confirm")
    def confirm_location():
        """Let the user say where they are.

        The system cannot sense location, so when it loses track - after
        a crash, or a workflow interrupted once a door had opened - the
        only honest source is a person telling it. Without this the web
        interface has no way out of UNKNOWN.
        """

        payload = request.get_json(silent=True) or {}
        name = (payload.get("room") or "").strip().upper()

        try:
            room = Room(name)
        except ValueError:
            return jsonify(
                {
                    "error": f"{name or 'No room'} is not a known room.",
                    "rooms": [member.value for member in Room],
                }
            ), 400

        runtime.context.confirm_location(room)

        return jsonify(
            {
                "status": "confirmed",
                "room": room.value,
                "state": runtime.state_snapshot(),
            }
        )

    @app.get("/api/state")
    def environment_state():
        return jsonify(runtime.state_snapshot())

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
