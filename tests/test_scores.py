from app.intent.recognizer import IntentRecognizer


recognizer = IntentRecognizer(
    "data/intents.csv"
)


test_sentences = [

    # Clearly known intents
    "I want to go to bed now.",
    "Please help me get outside.",
    "I need my pills.",
    "I am ready to study.",
    "I want to relax for a while.",
    "I just woke up.",

    # More natural / indirect requests
    "I've had a long day and think I should get some rest.",
    "Can you help me get out of the room?",
    "My medicine needs to be taken now.",
    "I need to focus on my coursework.",
    "Make things comfortable for me.",
    "I am awake and ready to start my day.",

    # Potentially ambiguous
    "I need some rest.",
    "I want to get comfortable.",
    "I need some peace and quiet.",
    "I want to go back.",
    "I need to get ready.",

    # Unknown requests
    "Tell me a joke.",
    "What is the weather today?",
    "Play some music.",
    "What time is it?",
    "Tell me something interesting.",
    "What is two plus two?",
]


for sentence in test_sentences:

    result = recognizer.predict(sentence)

    print("\n" + "=" * 70)

    print("Input:")
    print(sentence)

    print("\nDecision:")
    print(result["decision"])

    print("\nPredicted Intent:")
    print(result["intent"])

    print("\nSimilarity Score:")
    print(round(result["similarity_score"], 4))

    print("\nMargin:")
    print(round(result["margin"], 4))

    print("\nTop Results:")

    for item in result["top_results"]:
        print(
            f"{item['intent']:<25}"
            f"{item['score']:.4f}"
        )

    print("\nBest Matching Reference:")
    print(result["matched_sentence"])