from faster_whisper import WhisperModel


class SpeechTranscriber:

    def __init__(
        self,
        model_size="base"
    ):

        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )


    def transcribe(
        self,
        audio_path
    ):

        segments, info = self.model.transcribe(
            audio_path
        )

        text = ""

        for segment in segments:

            text += segment.text

        return text.strip()