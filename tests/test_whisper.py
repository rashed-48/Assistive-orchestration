from faster_whisper import WhisperModel


print("Loading Whisper model...")

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

print("Model loaded.")


segments, info = model.transcribe(
    "test_audio.wav"
)


print("\nTranscription:\n")

text = ""

for segment in segments:

    print(
        f"[{segment.start:.2f}s -> "
        f"{segment.end:.2f}s] "
        f"{segment.text}"
    )

    text += segment.text


print("\nFinal text:")
print(text.strip())