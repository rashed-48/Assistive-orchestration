from app.speech.transcriber import SpeechTranscriber
from app.intent.recognizer import IntentRecognizer


transcriber = SpeechTranscriber(
    model_size="base"
)


recognizer = IntentRecognizer(
    "data/intents.csv",
    similarity_threshold=0.65
)


print("Transcribing audio...")

text = transcriber.transcribe(
    "test_audio.wav"
)


print("\n" + "=" * 60)

print("TRANSCRIPTION:")
print(text)


result = recognizer.predict(
    text
)


print("\nDECISION:")
print(result["decision"])


print("\nINTENT:")
print(result["intent"])


print("\nSIMILARITY:")
print(
    round(
        result["similarity_score"],
        4
    )
)



print("\nTOP RESULTS:")

for item in result["top_results"]:

    print(
        f"{item['intent']:<25}"
        f"{item['score']:.4f}"
    )