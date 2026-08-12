import sounddevice as sd
import numpy as np
import wave


SAMPLE_RATE = 16000
DURATION = 5


print("Recording for 5 seconds...")

audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32"
)

sd.wait()

print("Recording finished.")


audio = np.squeeze(audio)


with wave.open(
    "test_audio.wav",
    "wb"
) as wav_file:

    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(SAMPLE_RATE)

    audio_int16 = (
        audio * 32767
    ).astype(np.int16)

    wav_file.writeframes(
        audio_int16.tobytes()
    )


print("Saved: test_audio.wav")