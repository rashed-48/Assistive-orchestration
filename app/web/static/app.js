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
const house = document.querySelector('#house');
const houseCaption = document.querySelector('#house-caption');
const replayPill = document.querySelector('#replay-pill');
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


/* ============================================================
   THE HOUSE
   A floor plan of the real device registry. Every tile maps to a
   device the Orchestrator can actually command, so what is drawn
   is the authoritative state rather than a decoration.
   ============================================================ */

// Which utilities each room owns, and what counts as "active".
const ROOM_DEVICES = {
  study: [{ field: 'table', device: 'study_table', icon: 'book-open', label: 'Desk', on: 'READY' }],
  relax: [{ field: 'tv', device: 'relax_tv', icon: 'tv', label: 'TV', on: 'ON' }],
  sleep: [{ field: 'bed', device: 'sleep_bed', icon: 'bed', label: 'Bed', on: 'READY' },
          { field: 'medication_servo', device: 'medication_servo', icon: 'pill', label: 'Medication', on: 'ON' }],
  meal:  [{ field: 'table', device: 'meal_table', icon: 'utensils', label: 'Table', on: 'READY' }],
};

const ROOM_LIGHT = { study: 'study_light', relax: 'relax_light', sleep: 'sleep_light', meal: 'meal_light' };
const ROOM_OF = { study: 'STUDY_ROOM', relax: 'RELAX_ROOM', sleep: 'SLEEP_ROOM', meal: 'MEAL_ROOM' };

// Device id -> where its value lives inside the state document.
const DEVICE_PATH = {
  drawing_light: ['drawing_light'], exit_door: ['exit_door'], buzzer: ['buzzer'],
  study_light: ['rooms', 'study', 'light'], study_door: ['rooms', 'study', 'door'], study_table: ['rooms', 'study', 'table'],
  relax_light: ['rooms', 'relax', 'light'], relax_door: ['rooms', 'relax', 'door'], relax_tv: ['rooms', 'relax', 'tv'],
  sleep_light: ['rooms', 'sleep', 'light'], sleep_door: ['rooms', 'sleep', 'door'],
  sleep_bed: ['rooms', 'sleep', 'bed'], medication_servo: ['rooms', 'sleep', 'medication_servo'],
  meal_light: ['rooms', 'meal', 'light'], meal_door: ['rooms', 'meal', 'door'], meal_table: ['rooms', 'meal', 'table'],
};

// What each action leaves its device in - lets a workflow be replayed.
const ACTION_RESULT = {
  LIGHT_ON: 'ON', LIGHT_OFF: 'OFF', TV_ON: 'ON', TV_OFF: 'OFF',
  OPEN_DOOR: 'OPEN', CLOSE_DOOR: 'CLOSED',
  PREPARE_TABLE: 'READY', RESET_TABLE: 'NORMAL',
  PREPARE_BED: 'READY', RESET_BED: 'NORMAL',
  ACTIVATE_MEDICATION: 'ON', BUZZER_ON: 'ON', BUZZER_OFF: 'OFF',
};

// Resting value, used when an action is the first thing in a workflow
// to touch a device and there is no earlier step to rewind to.
const RESTING = {
  exit_door: 'CLOSED', study_door: 'CLOSED', relax_door: 'CLOSED',
  sleep_door: 'CLOSED', meal_door: 'CLOSED',
  drawing_light: 'OFF', study_light: 'OFF', relax_light: 'OFF',
  sleep_light: 'OFF', meal_light: 'OFF', relax_tv: 'OFF',
  buzzer: 'OFF', medication_servo: 'OFF',
  study_table: 'NORMAL', meal_table: 'NORMAL', sleep_bed: 'NORMAL',
};

function deviceValue(env, device) {
  return (DEVICE_PATH[device] || []).reduce((node, key) => (node || {})[key], env);
}

function setDeviceValue(env, device, value) {
  const path = DEVICE_PATH[device];
  if (!path) return;
  const parent = path.slice(0, -1).reduce((node, key) => node[key], env);
  parent[path[path.length - 1]] = value;
}

function tile(device, icon, label, active, value) {
  return '<span class="dev' + (active ? ' on' : '') + '" data-device="' + device
    + '" title="' + device + '"><i data-lucide="' + icon + '"></i>' + label
    + (value ? '<i class="val">' + value + '</i>' : '') + '</span>';
}

function renderHouse(env) {
  Object.keys(ROOM_LIGHT).forEach((key) => {
    const lit = env.rooms[key].light === 'ON';

    house.querySelector('[data-devices="' + key + '"]').innerHTML =
      tile(ROOM_LIGHT[key], lit ? 'lightbulb' : 'lightbulb-off', 'Light', lit,
           env.rooms[key].light)
      + ROOM_DEVICES[key]
          .map((d) => tile(d.device, d.icon, d.label,
                           env.rooms[key][d.field] === d.on, env.rooms[key][d.field]))
          .join('');

    house.querySelector('[data-room="' + ROOM_OF[key] + '"]').classList.toggle('lit', lit);
  });

  // The corridor light and the alarm belong to the drawing room.
  const drawingLit = env.drawing_light === 'ON';
  house.querySelector('[data-devices="drawing"]').innerHTML =
    tile('drawing_light', drawingLit ? 'lightbulb' : 'lightbulb-off', 'Light',
         drawingLit, env.drawing_light)
    + tile('buzzer', 'siren', 'Buzzer', env.buzzer === 'ON', env.buzzer);
  house.querySelector('[data-room="DRAWING_ROOM"]').classList.toggle('lit', drawingLit);

  house.querySelectorAll('.door').forEach((node) => {
    const open = deviceValue(env, node.dataset.device) === 'OPEN';
    node.classList.toggle('open', open);
    const name = node.dataset.device === 'exit_door'
      ? 'EXIT ' + (open ? 'OPEN' : 'CLOSED')
      : (open ? 'OPEN' : 'CLOSED');
    node.innerHTML = '<i data-lucide="' + (open ? 'door-open' : 'door-closed') + '"></i>'
      + '<span>' + name + '</span>';
  });

  // Where the person is, and how sure the system is about it.
  const certain = env.location_status === 'KNOWN';

  house.querySelectorAll('.person').forEach((node) => {
    const here = node.dataset.person === env.current_room;
    node.classList.toggle('here', here);
    node.classList.toggle('uncertain', here && !certain);
  });

  house.querySelectorAll('.room').forEach((node) => {
    node.classList.toggle('occupied', certain && node.dataset.room === env.current_room);
  });

  houseCaption.innerHTML = certain
    ? 'Person in <b>' + env.current_room.replace('_', ' ') + '</b> &middot; mode <b>'
      + env.current_mode + '</b>'
    : 'Location <b>' + env.location_status + '</b> &middot; last known <b>'
      + env.current_room.replace('_', ' ') + '</b>';

  lucide.createIcons();
}

/* Replay a finished workflow across the floor plan one action at a
   time, so the dependency order becomes visible instead of implied.
   The starting world is reconstructed by rewinding the action list. */
let replayTimer = null;

function replayWorkflow(actions, finalState) {
  if (replayTimer) {
    clearInterval(replayTimer);
    replayTimer = null;
  }

  const steps = (actions || []).filter((a) => DEVICE_PATH[a.device] && ACTION_RESULT[a.action]);

  if (!steps.length) {
    renderHouse(finalState);
    return;
  }

  // Rewind: a device's value before step i is whatever the most recent
  // earlier step left it at, or its resting value if untouched.
  const world = JSON.parse(JSON.stringify(finalState));

  steps.forEach((step, i) => {
    const earlier = steps.slice(0, i).reverse().find((s) => s.device === step.device);
    setDeviceValue(world, step.device,
      earlier ? ACTION_RESULT[earlier.action] : (RESTING[step.device] || 'OFF'));
  });

  renderHouse(world);
  replayPill.hidden = false;
  replayPill.className = 'decision-pill processing';

  let i = 0;

  replayTimer = setInterval(() => {
    if (i >= steps.length) {
      clearInterval(replayTimer);
      replayTimer = null;
      replayPill.hidden = true;
      renderHouse(finalState);
      return;
    }

    const step = steps[i];
    setDeviceValue(world, step.device, ACTION_RESULT[step.action]);
    renderHouse(world);

    const node = house.querySelector('[data-device="' + step.device + '"]');
    if (node) {
      const room = node.closest('.room');
      node.classList.add('firing');
      if (room) room.classList.add('firing');
      setTimeout(() => {
        node.classList.remove('firing');
        if (room) room.classList.remove('firing');
      }, 420);
    }

    houseCaption.innerHTML = '<b>' + (i + 1) + '/' + steps.length + '</b> &nbsp; '
      + step.action + ' &rarr; <b>' + step.device + '</b>';

    i += 1;
  }, 480);
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

  renderHouse(env);
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
  if (data.state) {
    emergencyBanner.hidden = !data.state.emergency_active;
    replayWorkflow(data.actions, data.state.environment);
  }
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
