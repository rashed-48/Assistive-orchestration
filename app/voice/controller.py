from app.speech.recorder import AudioRecorder
from app.speech.transcriber import SpeechTranscriber
from app.intent.recognizer import IntentRecognizer


class VoiceController:

    def __init__(
        self,
        intent_file="data/intents.csv",
        whisper_model="base",
        similarity_threshold=0.65,
        margin_threshold=0.20,
        max_clarification_attempts=2
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
            similarity_threshold=similarity_threshold,
            margin_threshold=margin_threshold
        )

        print("Intent recognizer loaded.")

        # ==================================================
        # CONFIGURATION
        # ==================================================

        self.max_clarification_attempts = (
            max_clarification_attempts
        )


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

        # --------------------------------------------------
        # Decision
        # --------------------------------------------------

        print("\nDecision:")

        print(
            result["decision"]
        )

        # --------------------------------------------------
        # Intent
        # --------------------------------------------------

        print("\nPredicted Intent:")

        print(
            result["intent"]
        )

        # --------------------------------------------------
        # Similarity
        # --------------------------------------------------

        print("\nSimilarity Score:")

        print(
            round(
                result["similarity_score"],
                4
            )
        )

        # --------------------------------------------------
        # Margin
        # --------------------------------------------------

        print("\nMargin:")

        print(
            round(
                result["margin"],
                4
            )
        )

        # --------------------------------------------------
        # Top results
        # --------------------------------------------------

        print("\nTop Results:")

        for item in result["top_results"]:

            print(
                f"{item['intent']:<25}"
                f"{item['score']:.4f}"
            )


    # ======================================================
    # SHOW AMBIGUOUS COMMAND
    # ======================================================

    def show_ambiguity(
        self,
        result
    ):

        print("\n" + "=" * 60)
        print("AMBIGUOUS COMMAND")
        print("=" * 60)

        print(
            "\nI am not completely sure "
            "what you mean."
        )

        print(
            "\nPossible interpretations:"
        )

        # --------------------------------------------------
        # Show top two possible intents
        # --------------------------------------------------

        for index, item in enumerate(
            result["top_results"][:2],
            start=1
        ):

            print(
                f"{index}. {item['intent']}"
            )

        print(
            "\nPlease clarify your request."
        )

        print(
            "Press ENTER to provide clarification."
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

        print(
            "Press ENTER to try again."
        )


    # ======================================================
    # WAIT FOR ENTER
    # ======================================================

    def wait_for_enter(self):

        while True:

            key = input()

            # Normal ENTER produces an empty string
            if key == "":
                return


    # ======================================================
    # MAIN VOICE INTERACTION LOOP
    # ======================================================

    def run(self):

        clarification_attempts = 0

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
            # ACCEPTED
            # ==================================================

            if decision == "ACCEPTED":

                print(
                    "\n" + "=" * 60
                )

                print(
                    "COMMAND ACCEPTED"
                )

                print(
                    "=" * 60
                )

                print(
                    f"\nFinal Intent: "
                    f"{result['intent']}"
                )

                print(
                    "\nThis intent is ready "
                    "for the orchestration layer."
                )

                return result

            # ==================================================
            # AMBIGUOUS
            # ==================================================

            elif decision == "AMBIGUOUS":

                clarification_attempts += 1

                self.show_ambiguity(
                    result
                )

                # ------------------------------------------------
                # Maximum clarification attempts
                # ------------------------------------------------

                if (
                    clarification_attempts
                    >= self.max_clarification_attempts
                ):

                    print(
                        "\nMaximum clarification "
                        "attempts reached."
                    )

                    print(
                        "The command has been cancelled."
                    )

                    return None

                # ------------------------------------------------
                # Continue loop
                # ------------------------------------------------

                continue

            # ==================================================
            # UNKNOWN
            # ==================================================

            elif decision == "UNKNOWN":

                self.show_unknown()

                # ------------------------------------------------
                # Reset clarification count because this is
                # a new command rather than clarification.
                # ------------------------------------------------

                clarification_attempts = 0

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