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

## Run the web interface

```powershell
.\.venv\Scripts\python.exe run_web.py
```

Open `http://127.0.0.1:5000` in your browser. Use the microphone control to start and stop recording; the existing Whisper transcription and intent-recognition workflow runs locally and the result appears in the interface.

## Project layout

- `app/speech/`: audio recording and transcription
- `app/intent/`: intent recognition and confidence decisions
- `app/web/`: local browser interface and API
- `data/`: intent, validation, ambiguous, and unknown datasets
- `tests/`: executable validation scripts
