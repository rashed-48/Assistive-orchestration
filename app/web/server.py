from pathlib import Path
import threading

from flask import Flask, jsonify, render_template

from app.voice.controller import VoiceController


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app():
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    controller = VoiceController(
        intent_file=str(PROJECT_ROOT / "data" / "intents.csv"),
        whisper_model="base",
        similarity_threshold=0.65,
        margin_threshold=0.20,
        max_clarification_attempts=2
    )
    recording_lock = threading.Lock()
    state = {"recording": False, "clarification_attempts": 0}

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
            audio_path = controller.recorder.stop_recording(
                str(PROJECT_ROOT / "command.wav")
            )

            if audio_path is None:
                return jsonify({"error": "No audio was captured. Please try again."}), 422

            text = controller.transcriber.transcribe(audio_path).strip()

            if not text:
                return jsonify({"error": "No speech was detected. Please try again."}), 422

            result = controller.recognizer.predict(text)

            if result["decision"] == "AMBIGUOUS":
                state["clarification_attempts"] += 1
            else:
                state["clarification_attempts"] = 0

            result["clarification_attempts"] = state["clarification_attempts"]
            result["max_clarification_attempts"] = controller.max_clarification_attempts
            result["transcription"] = text

            if (
                result["decision"] == "AMBIGUOUS"
                and state["clarification_attempts"] >= controller.max_clarification_attempts
            ):
                result["message"] = "Maximum clarification attempts reached. The command has been cancelled."
                state["clarification_attempts"] = 0
            elif result["decision"] == "AMBIGUOUS":
                result["message"] = "Please clarify your request by recording another command."
            elif result["decision"] == "UNKNOWN":
                result["message"] = "This request did not match a supported command. Please try again."
            else:
                result["message"] = "Command accepted and ready for the orchestration layer."

            return jsonify(result)
        except Exception as error:
            return jsonify({"error": f"Command processing failed: {error}"}), 500

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
