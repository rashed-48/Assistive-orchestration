# Assistive Orchestration

A Python prototype for speech transcription and intent recognition. It uses Faster Whisper to turn audio into text and a sentence-transformer model to classify the text against the intents in `data/intents.csv`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The first run downloads the `base` Whisper model and the `all-MiniLM-L6-v2` sentence-transformer model.

## Run checks

```powershell
python tests/test_intent.py
python tests/test_voice_intent.py
python tests/test_evaluation.py
```

Some tests require a working microphone. The live recording flow currently uses `msvcrt`, so it is intended for Windows.

## Project layout

- `app/speech/`: audio recording and transcription
- `app/intent/`: intent recognition and confidence decisions
- `data/`: intent, validation, ambiguous, and unknown datasets
- `tests/`: executable validation scripts
