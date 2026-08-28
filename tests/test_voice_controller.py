from app.voice.controller import VoiceController


# ==========================================================
# CREATE VOICE CONTROLLER
# ==========================================================

controller = VoiceController(
    intent_file="data/intents.csv",
    whisper_model="base",

    # Current development threshold
    similarity_threshold=0.65
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
        "\nThe confirmed intent is ready "
        "for the orchestration layer."
    )