# Test Layers

The normal automated suite is collected from `tests/automated/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests must be deterministic and must not require MQTT, ESP32
hardware, microphone input, user input, or speech model loading.

Legacy scripts under `tests/` remain available for manual validation with:

```powershell
.\.venv\Scripts\python.exe -m tests.<module_name>
```

Those scripts may exercise MQTT, voice, audio, fake ESP32 endpoints, or
printed workflow demonstrations. They are intentionally excluded from normal
pytest collection by `pytest.ini`.

## Layers

- Unit tests: state, transition/workflow generation, protocol encoding, and
  deterministic registry behavior.
- Orchestration integration tests: `Orchestrator`, `ContextManager`,
  `WorkflowEngine`, and deterministic fake executors.
- MQTT integration scripts: require a broker and are manual for now.
- Hardware scripts: require ESP32/devices/network and are manual for now.
- Voice/audio scripts: require microphone/audio/model resources and are manual
  for now.
