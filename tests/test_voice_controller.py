from app.voice.controller import VoiceController


# ==========================================================
# CREATE VOICE CONTROLLER
# ==========================================================

controller = VoiceController(
    intent_file="data/intents.csv",
    whisper_model="base",

    # Current development thresholds
    similarity_threshold=0.65,
    margin_threshold=0.20,

    # Maximum number of clarification attempts
    max_clarification_attempts=2
)


# ==========================================================
# START INTERACTION
# ==========================================================

result = controller.run()


# ==========================================================
# FINAL RESULT
# ==========================================================

print("\n" + "=" * 60)
print("FINAL RESULT")
print("=" * 60)


if result is None:

    print(
        "\nNo final intent was accepted."
    )

else:

    print(
        "\nFinal Intent:"
    )

    print(
        result["intent"]
    )

    print(
        "\nSimilarity:"
    )

    print(
        round(
            result["similarity_score"],
            4
        )
    )

    print(
        "\nMargin:"
    )

    print(
        round(
            result["margin"],
            4
        )
    )

    print(
        "\nThe accepted intent is ready "
        "for the orchestration layer."
    )