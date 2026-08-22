from app.speech.recorder import AudioRecorder
from app.speech.transcriber import SpeechTranscriber
from app.intent.recognizer import IntentRecognizer


class VoiceController:

    def __init__(
        self,
        intent_file="data/intents.csv",
        whisper_model="base",
        similarity_threshold=0.60
    ):

        # ==================================================
        # AUDIO / SPEECH
        # ==================================================

        print("\nLoading speech recognizer...")

        self.recorder = AudioRecorder()

        self.transcriber = SpeechTranscriber(
            model_size=whisper_model
        )

        print("Speech recognizer loaded.")

        # ==================================================
        # INTENT RECOGNIZER
        # ==================================================

        print("\nLoading intent recognizer...")

        self.recognizer = IntentRecognizer(
            intent_file,
            similarity_threshold=similarity_threshold
        )

        print("Intent recognizer loaded.")

    # ======================================================
    # LISTEN TO ONE VOICE COMMAND
    # ======================================================

    def listen(self):

        audio_path = self.recorder.record(
            output_path="command.wav"
        )

        if audio_path is None:
            return None

        print("\nTranscribing...")

        text = self.transcriber.transcribe(
            audio_path
        )

        if text is None:
            return None

        text = text.strip()

        if not text:
            return None

        return text

    # ======================================================
    # PROCESS ONE COMMAND
    # ======================================================

    def process(self):

        text = self.listen()

        if not text:

            print(
                "\nNo speech detected."
            )

            return None

        # --------------------------------------------------
        # Show transcription
        # --------------------------------------------------

        print("\n" + "=" * 60)
        print("TRANSCRIPTION")
        print("=" * 60)

        print(text)

        # --------------------------------------------------
        # Intent recognition
        # --------------------------------------------------

        result = self.recognizer.predict(
            text
        )

        return text, result

    # ======================================================
    # SHOW RESULT
    # ======================================================

    def show_result(
        self,
        text,
        result
    ):

        print("\n" + "=" * 60)
        print("INTENT ANALYSIS")
        print("=" * 60)

        print(
            f"\nDecision: "
            f"{result['decision']}"
        )

        print(
            f"\nPredicted Intent: "
            f"{result['intent']}"
        )

        print(
            "\nSimilarity Score:"
        )

        print(
            round(
                result["similarity_score"],
                4
            )
        )

        print(
            "\nBest Match:"
        )

        print(
            result["matched_sentence"]
        )

        print(
            "\nTop Results:"
        )

        for item in result["top_results"]:

            print(
                f"{item['intent']:<25}"
                f"{item['score']:.4f}"
            )

    # ======================================================
    # SHOW UNKNOWN COMMAND
    # ======================================================

    def show_unknown(self):

        print("\n" + "=" * 60)
        print("UNKNOWN COMMAND")
        print("=" * 60)

        print(
            "\nI could not match your request "
            "to a supported command."
        )

        print(
            "\nPlease try again."
        )

    # ======================================================
    # CONFIRM PREDICTED INTENT
    # ======================================================

    def confirm_intent(
        self,
        result
    ):

        intent = result["intent"]

        print("\n" + "=" * 60)
        print("COMMAND CONFIRMATION")
        print("=" * 60)

        print(
            f"\nI understood your request as:"
        )

        print(
            f"\n  {intent}"
        )

        print(
            f"\nSimilarity Score: "
            f"{result['similarity_score']:.4f}"
        )

        while True:

            print(
                "\nDo you want me to continue?"
            )

            print(
                "Enter Y for Yes or N for No:"
            )

            answer = input(
                "\n> "
            ).strip().lower()

            if answer in ("y", "yes"):

                print(
                    "\nCommand confirmed."
                )

                return True

            if answer in ("n", "no"):

                print(
                    "\nCommand cancelled."
                )

                return False

            print(
                "\nPlease enter Y or N."
            )

    # ======================================================
    # WAIT FOR ENTER
    # ======================================================

    def wait_for_enter(self):

        while True:

            key = input()

            if key == "":
                return

    # ======================================================
    # MAIN VOICE INTERACTION LOOP
    # ======================================================

    def run(self):

        while True:

            # ==================================================
            # WAIT FOR USER TO START
            # ==================================================

            print("\n" + "=" * 60)
            print("VOICE COMMAND")
            print("=" * 60)

            print(
                "\nPress ENTER to start recording."
            )

            self.wait_for_enter()

            # ==================================================
            # RECORD + TRANSCRIBE + CLASSIFY
            # ==================================================

            result_data = self.process()

            # --------------------------------------------------
            # No usable speech
            # --------------------------------------------------

            if result_data is None:

                print(
                    "\nNo usable command received."
                )

                continue

            text, result = result_data

            # ==================================================
            # SHOW RESULT
            # ==================================================

            self.show_result(
                text,
                result
            )

            decision = result["decision"]

            # ==================================================
            # PREDICTED
            # ==================================================

            if decision == "PREDICTED":

                confirmed = self.confirm_intent(
                    result
                )

                # ------------------------------------------------
                # User confirmed
                # ------------------------------------------------

                if confirmed:

                    return result

                # ------------------------------------------------
                # User rejected prediction
                # ------------------------------------------------

                print(
                    "\nPlease provide another command."
                )

                continue

            # ==================================================
            # UNKNOWN
            # ==================================================

            elif decision == "UNKNOWN":

                self.show_unknown()

                continue

            # ==================================================
            # SAFETY FALLBACK
            # ==================================================

            else:

                print(
                    "\nUnexpected decision returned:"
                )

                print(
                    decision
                )

                print(
                    "\nCommand cancelled for safety."
                )

                return None