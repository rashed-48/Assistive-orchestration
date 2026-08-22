from app.intent.recognizer import IntentRecognizer


recognizer = IntentRecognizer(
    "data/intents.csv"
)


test_sentences = [
    "I want to sleep",
    "prepare for sleep",
    "I want to study",
    "I need my medicine",
    "Something terrible has happened.",
    "prepare for skill",
    "the weather is nice",
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
        "similarity_score:",
        round(result["similarity_score"], 4)
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