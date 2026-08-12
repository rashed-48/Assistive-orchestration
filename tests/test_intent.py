from app.intent.recognizer import IntentRecognizer


recognizer = IntentRecognizer(
    "data/intents.csv"
)


test_sentences = [
    "I feel exhausted and want to go to bed.",
    "Can you help me get outside?",
    "I need to take my pills.",
    "I have some studying to do.",
    "Something terrible has happened.",
    "I have just gotten out of bed.",
    "I want some quiet time.",
    "Please prepare things for my dinner.",
]


for sentence in test_sentences:

    result = recognizer.predict(sentence)

    print("\n" + "=" * 60)

    print("Input:", sentence)

    print(
        "Predicted Intent:",
        result["intent"]
    )

    print(
        "Confidence:",
        round(result["confidence"], 4)
    )

    print(
        "Best Match:",
        result["matched_sentence"]
    )

    print("Top Results:")

    for item in result["top_results"]:

        print(
            f"  {item['intent']:<25}"
            f"{item['score']:.4f}"
        )