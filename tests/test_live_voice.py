import sounddevice as sd
import numpy as np
import wave
import msvcrt
import time

from app.speech.transcriber import SpeechTranscriber
from app.intent.recognizer import IntentRecognizer


# ==========================================================
# CONFIGURATION
# ==========================================================

SAMPLE_RATE = 16000
CHANNELS = 1
OUTPUT_FILE = "command.wav"


# ==========================================================
# WAIT FOR ENTER
# ==========================================================

def wait_for_enter():

    print("\n" + "=" * 60)
    print("LIVE VOICE INPUT")
    print("=" * 60)

    print("\nPress ENTER to start recording.")
    print("Press Ctrl+C to cancel.")

    while True:

        key = msvcrt.getch()

        # ENTER key
        if key == b'\r':
            return


# ==========================================================
# RECORD UNTIL SPACE
# ==========================================================

def record_until_space():

    wait_for_enter()

    print("\nSpeak your command naturally.")
    print("Press SPACE to stop recording.\n")

    audio_chunks = []

    def callback(
        indata,
        frames,
        time_info,
        status
    ):

        if status:
            print(
                "Audio status:",
                status
            )

        audio_chunks.append(
            indata.copy()
        )

    print("🎤 Listening...")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        callback=callback
    ):

        try:

            while True:

                if msvcrt.kbhit():

                    key = msvcrt.getch()

                    # SPACE key
                    if key == b' ':
                        break

                time.sleep(0.05)

        except KeyboardInterrupt:

            print("\nRecording cancelled.")

            return None

    print("\nRecording stopped.")

    # ------------------------------------------------------
    # Make sure something was recorded
    # ------------------------------------------------------

    if not audio_chunks:

        print("No audio recorded.")

        return None

    # ------------------------------------------------------
    # Combine audio chunks
    # ------------------------------------------------------

    audio = np.concatenate(
        audio_chunks,
        axis=0
    )

    audio = np.squeeze(audio)

    # ------------------------------------------------------
    # Convert float32 audio to int16 WAV format
    # ------------------------------------------------------

    audio_int16 = (
        audio * 32767
    ).astype(np.int16)

    # ------------------------------------------------------
    # Save WAV file
    # ------------------------------------------------------

    with wave.open(
        OUTPUT_FILE,
        "wb"
    ) as wav_file:

        wav_file.setnchannels(
            CHANNELS
        )

        wav_file.setsampwidth(
            2
        )

        wav_file.setframerate(
            SAMPLE_RATE
        )

        wav_file.writeframes(
            audio_int16.tobytes()
        )

    print(
        f"Audio saved to: {OUTPUT_FILE}"
    )

    return OUTPUT_FILE


# ==========================================================
# LOAD WHISPER
# ==========================================================

print("\n" + "=" * 60)
print("LOADING SPEECH RECOGNITION")
print("=" * 60)

print("\nLoading Whisper model...")

transcriber = SpeechTranscriber(
    model_size="base"
)

print("Whisper loaded successfully.")


# ==========================================================
# LOAD INTENT RECOGNIZER
# ==========================================================

print("\nLoading Intent Recognizer...")

recognizer = IntentRecognizer(
    "data/intents.csv",
    similarity_threshold=0.65,
    margin_threshold=0.20
)

print("Intent recognizer loaded successfully.")


# ==========================================================
# START RECORDING
# ==========================================================

audio_path = record_until_space()


# ==========================================================
# HANDLE CANCEL / EMPTY RECORDING
# ==========================================================

if audio_path is None:

    print("\nNo command processed.")

    raise SystemExit


# ==========================================================
# WHISPER TRANSCRIPTION
# ==========================================================

print("\n" + "=" * 60)
print("TRANSCRIBING")
print("=" * 60)

print("\nPlease wait...")

text = transcriber.transcribe(
    audio_path
)


# ==========================================================
# SHOW TRANSCRIPTION
# ==========================================================

print("\nTRANSCRIPTION:")
print(text)


# ==========================================================
# INTENT RECOGNITION
# ==========================================================

result = recognizer.predict(
    text
)


# ==========================================================
# SHOW DECISION
# ==========================================================

print("\n" + "=" * 60)
print("INTENT ANALYSIS")
print("=" * 60)


print("\nDecision:")
print(
    result["decision"]
)


print("\nPredicted Intent:")
print(
    result["intent"]
)


print("\nSimilarity Score:")
print(
    round(
        result["similarity_score"],
        4
    )
)


print("\nMargin:")
print(
    round(
        result["margin"],
        4
    )
)


# ==========================================================
# SHOW TOP RESULTS
# ==========================================================

print("\nTop Results:")

for item in result["top_results"]:

    print(
        f"{item['intent']:<25}"
        f"{item['score']:.4f}"
    )


# ==========================================================
# COMPLETE
# ==========================================================

print("\n" + "=" * 60)
print("VOICE COMMAND PROCESSING COMPLETE")
print("=" * 60)