const stage = document.querySelector('.voice-stage');
const recordButton = document.querySelector('#record-button');
const stageTitle = document.querySelector('#stage-title');
const stageDetail = document.querySelector('#stage-detail');
const transcript = document.querySelector('#transcript');
const pill = document.querySelector('#decision-pill');
const emptyResult = document.querySelector('#result-empty');
const resultContent = document.querySelector('#result-content');
const intentName = document.querySelector('#intent-name');
const resultMessage = document.querySelector('#result-message');
const similarityScore = document.querySelector('#similarity-score');
const matchedSentence = document.querySelector('#matched-sentence');
const topResults = document.querySelector('#top-results');
const confirmBar = document.querySelector('#confirm-bar');
const confirmButton = document.querySelector('#confirm-button');
const cancelButton = document.querySelector('#cancel-button');
const execution = document.querySelector('#execution');
const executionSummary = document.querySelector('#execution-summary');
const executionActions = document.querySelector('#execution-actions');
const stateGrid = document.querySelector('#state-grid');
const mqttPill = document.querySelector('#mqtt-pill');
const emergencyBanner = document.querySelector('#emergency-banner');
const locationBanner = document.querySelector('#location-banner');
const locationMessage = document.querySelector('#location-message');
const locationActions = document.querySelector('#location-actions');
const ROOMS = ['OUTSIDE', 'DRAWING_ROOM', 'STUDY_ROOM', 'RELAX_ROOM', 'SLEEP_ROOM', 'MEAL_ROOM'];

let recording = false;
let pendingIntent = null;

function setStage(state, title, detail) {
  stage.dataset.state = state;
  stageTitle.textContent = title;
  stageDetail.textContent = detail;
  recordButton.setAttribute('aria-label', state === 'recording' ? 'Stop recording' : 'Start recording');
  recordButton.innerHTML = state === 'recording' ? '<i data-lucide="square"></i>' : '<i data-lucide="mic"></i>';
  lucide.createIcons();
}

function setPill(label, state) {
  pill.textContent = label;
  pill.className = `decision-pill ${state}`;
}

function displayError(message) {
  setStage('idle', 'Ready when you are', 'Select the microphone to begin.');
  setPill('Needs attention', 'error');
  transcript.textContent = message;
  transcript.classList.remove('has-text');
  emptyResult.hidden = false;
  resultContent.hidden = true;
}

function displayResult(data) {
  const predicted = data.decision === 'PREDICTED';
  const readableIntent = predicted ? data.intent : 'No supported intent';
  const detail = predicted ? 'Confirm this command, or record a different one.' : 'Try recording your command again.';
  setStage('idle', predicted ? 'Command recognized' : 'Let’s try again', detail);
  setPill(data.decision, data.decision.toLowerCase());
  transcript.textContent = `“${data.transcription}”`;
  transcript.classList.add('has-text');
  intentName.textContent = readableIntent;
  resultMessage.textContent = data.message;
  similarityScore.textContent = `${Math.round(data.similarity_score * 100)}%`;
  matchedSentence.textContent = data.matched_sentence ? `“${data.matched_sentence}”` : '--';
  topResults.innerHTML = data.top_results.map((item) => `<li><span>${item.intent}</span><b>${Math.round(item.score * 100)}%</b></li>`).join('');
  emptyResult.hidden = true;
  resultContent.hidden = false;

  // Nothing runs until the user confirms it.
  pendingIntent = predicted && data.executable ? data.intent : null;
  confirmBar.hidden = pendingIntent === null;
  execution.hidden = true;
}

function renderState(snapshot) {
  const env = snapshot.environment;
  emergencyBanner.hidden = !snapshot.emergency_active;

  // The system cannot sense location. When it has lost track, the only
  // honest source is the user, so offer them the choice explicitly.
  const known = env.location_status === 'KNOWN';
  locationBanner.hidden = known;

  if (!known) {
    const heading = env.location_destination ? ` (heading to ${env.location_destination})` : '';
    locationMessage.textContent =
      `Location ${env.location_status}${heading}. ${env.location_reason || ''} `
      + `Last known: ${env.current_room}. Tell me where you are:`;
    locationActions.innerHTML = ROOMS
      .map((room) => `<button type="button" data-room="${room}">${room.replace('_', ' ')}</button>`)
      .join('');
  }

  lucide.createIcons();
  const connected = snapshot.mqtt.connected;
  mqttPill.textContent = connected ? 'MQTT connected' : 'MQTT offline';
  mqttPill.className = `decision-pill ${connected ? 'predicted' : 'unknown'}`;

  const cards = [
    ['Location', [['Room', env.current_room], ['Mode', env.current_mode], ['Return to', env.return_target ?? '--']]],
    ['Common', [['Drawing light', env.drawing_light], ['Exit door', env.exit_door], ['Buzzer', env.buzzer]]],
    ['Study', Object.entries(env.rooms.study)],
    ['Relax', Object.entries(env.rooms.relax)],
    ['Sleep', Object.entries(env.rooms.sleep)],
    ['Meal', Object.entries(env.rooms.meal)],
  ];

  stateGrid.innerHTML = cards.map(([title, rows]) => `
    <div class="state-card">
      <span class="field-label">${title}</span>
      <dl>${rows.map(([k, v]) => `<div><dt>${k.replace(/_/g, ' ')}</dt><dd>${v}</dd></div>`).join('')}</dl>
    </div>`).join('');
}

async function refreshState() {
  try {
    const response = await fetch('/api/state');
    if (response.ok) renderState(await response.json());
  } catch (error) {
    /* the state panel is informational; leave the last good render */
  }
}

function displayExecution(data) {
  confirmBar.hidden = true;
  execution.hidden = false;
  pendingIntent = null;

  const ok = data.status === 'executed';
  executionSummary.textContent = ok
    ? `${data.intent} completed. ${data.executed_actions} device actions acknowledged.`
    : data.status === 'degraded'
      ? `${data.intent} ran, but ${data.failed_actions} of ${data.executed_actions} device actions failed. Check the environment below.`
      : `${data.intent} failed: ${data.error}`;
  executionActions.innerHTML = (data.actions ?? [])
    .map((item) => `<li><span>${item.action} ${item.device}</span><b>${item.node ?? ''}</b></li>`)
    .join('');

  setPill(ok ? 'EXECUTED' : data.status === 'degraded' ? 'DEGRADED' : 'FAILED', ok ? 'predicted' : 'unknown');
  setStage('idle', ok ? 'Workflow complete' : 'Workflow failed', 'Select the microphone to record another command.');
  if (data.state) renderState(data.state);
}

async function request(endpoint, body) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || 'Something went wrong.');
    error.payload = data;
    throw error;
  }
  return data;
}

recordButton.addEventListener('click', async () => {
  recordButton.disabled = true;
  try {
    if (!recording) {
      await request('/api/recording/start');
      recording = true;
      setStage('recording', 'Listening now', 'Speak naturally, then select stop when you are done.');
      setPill('Recording', 'processing');
    } else {
      recording = false;
      setStage('processing', 'Processing command', 'Transcribing and matching your intent.');
      setPill('Processing', 'processing');
      displayResult(await request('/api/recording/stop'));
    }
  } catch (error) {
    recording = false;
    displayError(error.message);
  } finally {
    recordButton.disabled = false;
  }
});

confirmButton.addEventListener('click', async () => {
  if (!pendingIntent) return;
  const intent = pendingIntent;
  confirmButton.disabled = true;
  cancelButton.disabled = true;
  setStage('processing', 'Running workflow', 'Sending device commands and waiting for acknowledgements.');
  setPill('Executing', 'processing');
  try {
    displayExecution(await request('/api/intent/confirm', { intent }));
  } catch (error) {
    if (error.payload && (error.payload.status === 'failed' || error.payload.status === 'degraded')) displayExecution(error.payload);
    else displayError(error.message);
    if (error.payload && error.payload.state) renderState(error.payload.state);
    else await refreshState();
  } finally {
    confirmButton.disabled = false;
    cancelButton.disabled = false;
  }
});

cancelButton.addEventListener('click', async () => {
  pendingIntent = null;
  confirmBar.hidden = true;
  try {
    await request('/api/intent/cancel');
  } catch (error) {
    /* cancelling is best effort */
  }
  setStage('idle', 'Command cancelled', 'Select the microphone to record another command.');
  setPill('Cancelled', 'idle');
});

locationActions.addEventListener('click', async (event) => {
  const room = event.target.dataset?.room;
  if (!room) return;
  try {
    const data = await request('/api/location/confirm', { room });
    renderState(data.state);
    setStage('idle', 'Location confirmed', `You are in ${room.replace('_', ' ')}. Record a command.`);
    setPill('Location set', 'predicted');
  } catch (error) {
    displayError(error.message);
  }
});

lucide.createIcons();
refreshState();
