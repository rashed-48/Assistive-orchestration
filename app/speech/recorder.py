import sounddevice as sd
import numpy as np
import wave
import msvcrt
import time
import threading


class AudioRecorder:

    def __init__(
        self,
        sample_rate=16000,
        channels=1
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self._audio_chunks = []
        self._stream = None
        self._lock = threading.Lock()

    def start_recording(self):
        """Start microphone capture for callers that control the stop action."""

        with self._lock:

            if self._stream is not None:
                raise RuntimeError("A recording is already in progress.")

            self._audio_chunks = []

            def callback(
                indata,
                frames,
                time_info,
                status
            ):

                if status:
                    print("Audio status:", status)

                self._audio_chunks.append(indata.copy())

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=callback
            )
            self._stream.start()

    def stop_recording(
        self,
        output_path="command.wav"
    ):
        """Stop microphone capture and save the result as a WAV file."""

        with self._lock:

            if self._stream is None:
                return None

            stream = self._stream
            self._stream = None

        stream.stop()
        stream.close()

        if not self._audio_chunks:
            print("No audio recorded.")
            return None

        audio = np.concatenate(self._audio_chunks, axis=0)
        audio = np.squeeze(audio)
        audio_int16 = (audio * 32767).astype(np.int16)

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        print(f"Audio saved to: {output_path}")
        return output_path

    def record(
        self,
        output_path="command.wav"
    ):

        print("\nSpeak your command naturally.")
        print("Press SPACE to stop recording.\n")

        audio_chunks = []

        def callback(
            indata,
            frames,
            time_info,
            status
        ):

            if status:
                print(
                    "Audio status:",
                    status
                )

            audio_chunks.append(
                indata.copy()
            )

        print(" Listening...")

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback
        ):

            try:

                while True:

                    if msvcrt.kbhit():

                        key = msvcrt.getch()

                        # SPACE
                        if key == b' ':
                            break

                    time.sleep(0.05)

            except KeyboardInterrupt:

                print("\nRecording cancelled.")

                return None

        print("\nRecording stopped.")

        # --------------------------------------------------
        # Check whether audio was recorded
        # --------------------------------------------------

        if not audio_chunks:

            print("No audio recorded.")

            return None

        # --------------------------------------------------
        # Combine audio chunks
        # --------------------------------------------------

        audio = np.concatenate(
            audio_chunks,
            axis=0
        )

        audio = np.squeeze(
            audio
        )

        # --------------------------------------------------
        # Convert float32 -> int16
        # --------------------------------------------------

        audio_int16 = (
            audio * 32767
        ).astype(
            np.int16
        )

        # --------------------------------------------------
        # Save WAV file
        # --------------------------------------------------

        with wave.open(
            output_path,
            "wb"
        ) as wav_file:

            wav_file.setnchannels(
                self.channels
            )

            wav_file.setsampwidth(
                2
            )

            wav_file.setframerate(
                self.sample_rate
            )

            wav_file.writeframes(
                audio_int16.tobytes()
            )

        print(
            f"Audio saved to: {output_path}"
        )

        return output_path
