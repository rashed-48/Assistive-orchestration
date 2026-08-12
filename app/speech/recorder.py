import sounddevice as sd
import numpy as np
import wave


class AudioRecorder:

    def __init__(
        self,
        sample_rate=16000,
        channels=1
    ):
        self.sample_rate = sample_rate
        self.channels = channels

    def record(
        self,
        duration=5,
        output_path="command.wav"
    ):

        print(
            f"Recording for {duration} seconds..."
        )

        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32"
        )

        sd.wait()

        print("Recording finished.")

        audio = np.squeeze(audio)

        audio_int16 = (
            audio * 32767
        ).astype(np.int16)

        with wave.open(
            output_path,
            "wb"
        ) as wav_file:

            wav_file.setnchannels(
                self.channels
            )

            wav_file.setsampwidth(2)

            wav_file.setframerate(
                self.sample_rate
            )

            wav_file.writeframes(
                audio_int16.tobytes()
            )

        return output_path