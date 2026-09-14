/* ==================================================================
   Assistive Orchestration - live dashboard

   One source of truth for everything that moves on this page: the
   server's event stream. Speech, recognition, the plan, every MQTT
   command / ack / completion, and every state commit arrive as
   ordered events. The page renders them; it never infers them.
   ================================================================== */

'use strict';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const ROOMS = ['OUTSIDE', 'DRAWING_ROOM', 'STUDY_ROOM', 'RELAX_ROOM', 'SLEEP_ROOM', 'MEAL_ROOM'];
const ROOM_LABEL = { OUTSIDE: 'Outside', DRAWING_ROOM: 'Drawing room', STUDY_ROOM: 'Study', RELAX_ROOM: 'Relax', SLEEP_ROOM: 'Sleep', MEAL_ROOM: 'Meal' };

const ROOM_KEY = { study: 'STUDY_ROOM', relax: 'RELAX_ROOM', sleep: 'SLEEP_ROOM', meal: 'MEAL_ROOM' };
const ROOM_LIGHT = { study: 'study_light', relax: 'relax_light', sleep: 'sleep_light', meal: 'meal_light' };
const ROOM_DEVICES = {
  study: [{ device: 'study_table', field: 'table', icon: 'table-2', label: 'Table', on: 'READY' }],
  relax: [{ device: 'relax_tv', field: 'tv', icon: 'tv', label: 'TV', on: 'ON' }],
  sleep: [{ device: 'sleep_bed', field: 'bed', icon: 'bed', label: 'Bed', on: 'READY' },
          { device: 'medication_servo', field: 'medication_servo', icon: 'pill', label: 'Medication', on: 'ON' }],
  meal:  [{ device: 'meal_table', field: 'table', icon: 'utensils', label: 'Table', on: 'READY' }],
};
const DEVICE_NODE = {
  drawing_light: 'esp32_a', relax_light: 'esp32_a', relax_tv: 'esp32_a', buzzer: 'esp32_a', exit_door: 'esp32_a', relax_door: 'esp32_a',
  sleep_light: 'esp32_b', sleep_door: 'esp32_b', sleep_bed: 'esp32_b', medication_servo: 'esp32_b',
  study_light: 'esp32_c', meal_light: 'esp32_c', study_door: 'esp32_c', meal_door: 'esp32_c', study_table: 'esp32_c', meal_table: 'esp32_c',
};

/* ------------------------------------------------------------------
   state held by the page
   ------------------------------------------------------------------ */
const ui = {
  lastSeq: 0,
  stream: null,
  pending: null,          // intent awaiting confirmation
  plan: [],               // [{index, device, action, row, commandId, ...}]
  byCommand: new Map(),   // command_id -> plan entry
  running: false,
  wireRows: 0,
};

/* ------------------------------------------------------------------
   helpers
   ------------------------------------------------------------------ */
function icons() { if (window.lucide) window.lucide.createIcons(); }
function fmtMs(v) { return v == null ? '' : (v < 10 ? v.toFixed(1) : Math.round(v)) + ' ms'; }
function shortId(id) { return id ? id.slice(0, 8) : ''; }
function nice(s) { return (s || '').replace(/_/g, ' ').toLowerCase(); }

function setStage(name, cls, meta, body) {
  const el = document.querySelector(`.stage[data-stage="${name}"]`);
  if (!el) return;
  el.classList.remove('active', 'done', 'failed');
  if (cls) el.classList.add(cls);
  if (meta !== undefined) el.querySelector('[data-meta]').textContent = meta;
  if (body !== undefined) el.querySelector('[data-body]').innerHTML = body;
}

function message(text, kind) {
  const el = $('#message');
  if (!text) { el.hidden = true; return; }
  el.hidden = false;
  el.className = 'message' + (kind ? ' ' + kind : '');
  el.textContent = text;
}

/* ------------------------------------------------------------------
   house
   ------------------------------------------------------------------ */
function tile(device, icon, label, active, value) {
  return `<span class="dev${active ? ' on' : ''}" data-device="${device}" title="${device} · ${DEVICE_NODE[device]}">`
       + `<i data-lucide="${icon}"></i>${label}${value ? `<i class="val">${value}</i>` : ''}</span>`;
}

function renderHouse(env) {
  if (!env) return;
  const house = $('#house');

  for (const key of Object.keys(ROOM_KEY)) {
    const room = env.rooms[key];
    const lit = room.light === 'ON';
    const el = house.querySelector(`[data-room="${ROOM_KEY[key]}"]`);
    el.classList.toggle('lit', lit);
    house.querySelector(`[data-devices="${key}"]`).innerHTML =
      tile(ROOM_LIGHT[key], lit ? 'lightbulb' : 'lightbulb-off', 'Light', lit, room.light)
      + ROOM_DEVICES[key].map((d) => tile(d.device, d.icon, d.label, room[d.field] === d.on, room[d.field])).join('');
  }

  const drawingLit = env.drawing_light === 'ON';
  house.querySelector('[data-room="DRAWING_ROOM"]').classList.toggle('lit', drawingLit);
  house.querySelector('[data-devices="drawing"]').innerHTML =
    tile('drawing_light', drawingLit ? 'lightbulb' : 'lightbulb-off', 'Light', drawingLit, env.drawing_light)
    + tile('buzzer', 'siren', 'Buzzer', env.buzzer === 'ON', env.buzzer);

  const doors = { exit_door: env.exit_door, study_door: env.rooms.study.door, relax_door: env.rooms.relax.door,
                  sleep_door: env.rooms.sleep.door, meal_door: env.rooms.meal.door };
  for (const [device, state] of Object.entries(doors)) {
    const node = house.querySelector(`[data-device="${device}"]`);
    const open = state === 'OPEN';
    node.classList.toggle('open', open);
    const name = device === 'exit_door' ? 'EXIT ' + (open ? 'OPEN' : 'CLOSED') : (open ? 'OPEN' : 'CLOSED');
    node.innerHTML = `<i data-lucide="${open ? 'door-open' : 'door-closed'}"></i><span>${name}</span>`;
  }

  for (const r of ROOMS) house.querySelector(`[data-room="${r}"]`).classList.toggle('here', env.current_room === r && env.location_status === 'KNOWN');
  icons();
}

function highlightDevice(device, cls) {
  const el = document.querySelector(`#house [data-device="${device}"]`);
  if (!el) return;
  el.classList.remove('busy-sent', 'busy-ack', 'busy-done', 'busy-fail');
  if (cls) el.classList.add('busy-' + cls);
  if (cls === 'done' || cls === 'fail') setTimeout(() => el.classList.remove('busy-' + cls), 1800);
}

/* ------------------------------------------------------------------
   logical state panel + banners
   ------------------------------------------------------------------ */
function renderState(snapshot) {
  const env = snapshot.environment;
  renderHouse(env);

  $('#st-room').textContent = ROOM_LABEL[env.current_room] || env.current_room;
  $('#st-mode').textContent = env.current_mode;
  const loc = $('#st-loc');
  loc.textContent = env.location_status + (env.location_destination ? ' → ' + ROOM_LABEL[env.location_destination] : '');
  loc.className = env.location_status === 'KNOWN' ? 'ok' : 'warn';
  const emg = $('#st-emg');
  emg.textContent = snapshot.emergency_active ? 'LATCHED' : 'clear';
  emg.className = snapshot.emergency_active ? 'bad' : 'ok';

  $('#banner-emergency').hidden = !snapshot.emergency_active;

  const unknown = env.location_status !== 'KNOWN';
  const banner = $('#banner-location');
  banner.hidden = !unknown;
  if (unknown) {
    $('#location-reason').textContent = env.location_reason
      || (snapshot.recovery && snapshot.recovery.location_reason)
      || 'The system will not act on a room-dependent command until you say where the person is.';
    $('#room-picks').innerHTML = ROOMS.map((r) => `<button data-room="${r}">${ROOM_LABEL[r]}</button>`).join('');
  }

  const m = $('#health-mqtt');
  m.classList.toggle('on', !!(snapshot.mqtt && snapshot.mqtt.connected));
  m.classList.toggle('off', !(snapshot.mqtt && snapshot.mqtt.connected));
}

async function refreshState() {
  try {
    const r = await fetch('/api/state');
    if (r.ok) renderState(await r.json());
  } catch (_) { /* transient */ }
}

/* ------------------------------------------------------------------
   nodes
   ------------------------------------------------------------------ */
function setNode(node, status, ms) {
  const el = document.querySelector(`.node[data-node="${node}"]`);
  if (!el) return;
  el.classList.remove('up', 'down', 'busy');
  if (status) el.classList.add(status);
  if (ms !== undefined) el.querySelector('[data-ms]').textContent = ms == null ? '' : fmtMs(ms);
}

async function probeNodes() {
  const btn = $('#probe-btn');
  btn.disabled = true;
  try {
    const r = await fetch('/api/nodes/probe', { method: 'POST' });
    const data = await r.json();
    for (const [node, up] of Object.entries(data.nodes || {})) setNode(node, up ? 'up' : 'down');
  } catch (_) { /* transient */ }
  btn.disabled = false;
}

/* ------------------------------------------------------------------
   pipeline: recognition
   ------------------------------------------------------------------ */
function renderRecognition(r) {
  const predicted = r.decision === 'PREDICTED';
  $('#recog-intent').textContent = predicted ? r.intent : 'no confident match';
  const d = $('#recog-decision');
  d.textContent = r.decision;
  d.className = 'recog-decision ' + (predicted ? 'predicted' : 'unknown');

  const score = r.similarity_score ?? r.score ?? 0;
  const tau = r.threshold ?? 0.65;
  $('#score-fill').style.width = Math.round(score * 100) + '%';
  $('#score-threshold').style.left = Math.round(tau * 100) + '%';
  $('#score-value').textContent = `similarity ${score.toFixed(3)}`;
  $('#score-tau').textContent = `threshold ${tau.toFixed(2)} · ${predicted ? 'accepted' : 'rejected'}`;

  const top = r.top_results || r.top || [];
  $('#top3').innerHTML = top.map((t) => `<div><span>${t.intent}</span><i>${t.score.toFixed(3)}</i></div>`).join('');
  $('#matched').innerHTML = r.matched_sentence || r.matched
    ? `nearest reference: <b>"${r.matched_sentence || r.matched}"</b>` : '';

  setStage('recognition', predicted ? 'done' : 'failed', `${score.toFixed(2)} ${predicted ? '≥' : '<'} ${tau}`,
    `<div class="line"><span class="k">best intent</span><span class="v">${predicted ? r.intent : '—'}</span></div>`
    + `<div class="line"><span class="k">decision</span><span class="v">${r.decision}</span></div>`
    + `<div class="line"><span class="k">rule</span><span class="k">max cosine over that intent's references vs τ</span></div>`);
}

/* ------------------------------------------------------------------
   pipeline: plan + execution rows
   ------------------------------------------------------------------ */
function renderPlan(ev) {
  ui.plan = [];
  ui.byCommand.clear();
  const list = $('#actions');
  list.innerHTML = '';

  ev.actions.forEach((a) => {
    const li = document.createElement('li');
    li.className = 'action';
    li.innerHTML = `<div class="a-name"><b>${a.action}</b><span>${a.device} · ${DEVICE_NODE[a.device] || '?'}</span></div>`
      + `<div class="step" data-step="sent">·</div><div class="step" data-step="ack">·</div>`
      + `<div class="step" data-step="done">·</div><div class="step" data-step="commit">·</div>`;
    list.appendChild(li);
    ui.plan.push({ ...a, row: li, commandId: null, sent: false, acked: false, done: false, committed: false, failed: false });
  });

  setStage('plan', 'done', `${ev.actions.length} action${ev.actions.length === 1 ? '' : 's'}`,
    `<div class="line"><span class="k">intent</span><span class="v">${ev.intent}</span></div>`
    + `<div class="line"><span class="k">ordered</span><span class="v">${ev.actions.map((a) => a.device.split('_').pop()).join(' → ')}</span></div>`
    + `<div class="line"><span class="k">nodes</span><span class="v">${[...new Set(ev.actions.map((a) => DEVICE_NODE[a.device]))].join(', ')}</span></div>`);
  setStage('execute', 'active', `0 / ${ev.actions.length}`);
}

function step(entry, name, cls, text) {
  const el = entry.row.querySelector(`[data-step="${name}"]`);
  el.className = 'step ' + cls;
  el.textContent = text;
}

function markCurrent(entry) {
  ui.plan.forEach((p) => p.row.classList.toggle('current', p === entry));
}

function progress() {
  const done = ui.plan.filter((p) => p.committed || p.failed).length;
  setStage('execute', ui.running ? 'active' : undefined, `${done} / ${ui.plan.length}`);
}

function onWire(ev) {
  addWireRow(ev);
  const node = ev.node;

  if (ev.phase === 'command') {
    let entry = ui.byCommand.get(ev.command_id);
    if (!entry) {
      entry = ui.plan.find((p) => !p.sent && p.device === ev.device && p.action === ev.action);
      if (entry) { entry.commandId = ev.command_id; ui.byCommand.set(ev.command_id, entry); }
    }
    setNode(node, 'busy');
    highlightDevice(ev.device, 'sent');
    if (entry) {
      entry.sent = true;
      markCurrent(entry);
      step(entry, 'sent', ev.retry ? 'retry' : 'sent', ev.retry ? `retry ${ev.attempt}` : 'sent');
      if (ev.retry) { step(entry, 'ack', '', '·'); step(entry, 'done', '', '·'); }
    }
    return;
  }

  const entry = ui.byCommand.get(ev.command_id);

  if (ev.phase === 'ack') {
    highlightDevice(ev.device, 'ack');
    if (entry) { entry.acked = true; step(entry, 'ack', 'ack', fmtMs(ev.since_send_ms)); }
    return;
  }

  if (ev.phase === 'complete') {
    const ok = ev.status === 'success';
    setNode(node, 'up', ev.since_send_ms);
    highlightDevice(ev.device, ok ? 'done' : 'fail');
    if (entry) {
      entry.done = ok;
      entry.failed = !ok;
      step(entry, 'done', ok ? 'done' : 'fail', ok ? fmtMs(ev.since_ack_ms ?? ev.since_send_ms) : 'error');
      if (ev.duplicate) step(entry, 'done', 'retry', 'dedup');
      if (!ok) { entry.row.classList.add('failed'); step(entry, 'commit', 'fail', 'no'); }
    }
    progress();
  }
}

function onCommit(ev) {
  const entry = ui.plan.find((p) => p.device === ev.device && p.action === ev.action && !p.committed);
  if (entry) { entry.committed = true; step(entry, 'commit', 'commit', '✓'); }
  progress();
}

function onWorkflowEnd(ev) {
  ui.running = false;
  ui.plan.forEach((p) => { if (!p.sent && !p.committed) { p.row.classList.add('skipped'); step(p, 'sent', '', 'skipped'); } });
  ui.plan.forEach((p) => p.row.classList.remove('current'));

  const ok = ev.status === 'executed';
  const degraded = ev.status === 'degraded';
  setStage('execute', ok ? 'done' : (degraded ? 'done' : 'failed'),
    ev.executed != null ? `${ev.executed - (ev.failed || 0)} ok · ${ev.failed || 0} failed` : ev.status);

  if (ev.state) {
    const env = ev.state.environment;
    setStage('commit', ok || degraded ? 'done' : 'failed', ok ? 'workflow complete' : ev.status,
      `<div class="line"><span class="k">room</span><span class="v">${env.current_room}</span></div>`
      + `<div class="line"><span class="k">mode</span><span class="v">${env.current_mode}</span></div>`
      + `<div class="line"><span class="k">location</span><span class="v">${env.location_status}</span></div>`
      + (degraded ? `<div class="line"><span class="k">note</span><span class="k">best-effort: reachable devices acted, the rest failed; room/mode still committed</span></div>` : ''));
    renderState(ev.state);
  } else {
    setStage('commit', 'failed', ev.status,
      `<div class="line"><span class="k">${ev.status}</span><span class="v">nothing committed</span></div>`
      + `<div class="line"><span class="k">why</span><span class="k">${ev.error || ''}</span></div>`);
    refreshState();
  }
  $$('.node.busy').forEach((n) => n.classList.remove('busy'));
}

/* ------------------------------------------------------------------
   wire trace
   ------------------------------------------------------------------ */
function addWireRow(ev) {
  const wire = $('#wire');
  const row = document.createElement('div');
  row.className = `wire-row ${ev.phase}${ev.status === 'error' ? ' error' : ''}${ev.retry ? ' retry' : ''}${ev.duplicate ? ' dup' : ''}`;
  const note = ev.duplicate ? 'answered from stored state · no actuation'
    : ev.retry ? `retry · attempt ${ev.attempt} · same command_id`
    : ev.phase === 'complete' ? (ev.status === 'success' ? 'hardware acted' : 'node reported error')
    : ev.phase === 'ack' ? 'received, before actuation' : '';
  row.innerHTML = `<span>${ev.t.toFixed(0)}</span><span class="ph">${ev.phase}</span><span>${ev.node}</span>`
    + `<span>${ev.device || ''}</span><span>${ev.action || ''}</span><span class="id">${shortId(ev.command_id)}</span>`
    + `<span class="ms">${fmtMs(ev.since_send_ms)}</span><span class="ms">${fmtMs(ev.since_ack_ms)}</span><span class="note">${note}</span>`;
  wire.prepend(row);
  if (++ui.wireRows > 300) { wire.lastElementChild.remove(); ui.wireRows--; }
}

/* ------------------------------------------------------------------
   event stream
   ------------------------------------------------------------------ */
function handle(ev) {
  ui.lastSeq = Math.max(ui.lastSeq, ev.seq || 0);
  switch (ev.kind) {
    case 'speech':
      $('#transcript').textContent = `"${ev.text}"`;
      $('#transcript').classList.remove('empty');
      setStage('speech', 'done', '', `<div class="line"><span class="v">"${ev.text}"</span></div>`);
      setStage('recognition', 'active', 'scoring…');
      break;
    case 'recognition':
      renderRecognition({ decision: ev.decision, intent: ev.intent, similarity_score: ev.score, threshold: ev.threshold, matched_sentence: ev.matched, top_results: ev.top });
      break;
    case 'workflow_start':
      ui.running = true;
      setStage('plan', 'active', 'planning…');
      setStage('execute', undefined, '', '<div class="exec-legend"><span></span><span>sent</span><span>ack</span><span>done</span><span>commit</span></div><ol class="actions" id="actions"></ol>');
      setStage('commit', undefined, '');
      break;
    case 'plan': renderPlan(ev); break;
    case 'wire': onWire(ev); break;
    case 'commit': onCommit(ev); break;
    case 'workflow_end': onWorkflowEnd(ev); break;
    case 'nodes': for (const n of ['esp32_a', 'esp32_b', 'esp32_c']) if (n in ev) setNode(n, ev[n] ? 'up' : 'down'); break;
    case 'node_probe': setNode(ev.node, 'up', ev.ms); break;
    case 'wire_connected': $('#health-stream').classList.add('on'); break;
    case 'wire_disconnected': $('#health-stream').classList.remove('on'); break;
    default: break;
  }
}

async function backfill() {
  // History fills the wire trace so the page is not empty on arrival,
  // but it must not animate devices or nodes for things that already
  // happened. Only the live stream does that.
  try {
    const r = await fetch('/api/events/poll?since=0');
    const d = await r.json();
    for (const ev of d.events) {
      if (ev.kind === 'wire') addWireRow(ev);
      ui.lastSeq = Math.max(ui.lastSeq, ev.seq);
    }
    if (d.events.some((e) => e.kind === 'wire_connected')) $('#health-stream').classList.add('on');
  } catch (_) { /* transient */ }
}

function connectStream() {
  if (ui.stream) ui.stream.close();
  const es = new EventSource(`/api/events?since=${ui.lastSeq}`);
  ui.stream = es;
  es.onopen = () => { $('#health-stream').classList.add('on'); $('#health-stream').classList.remove('off'); };
  es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (_) { /* ignore */ } };
  es.onerror = () => {
    $('#health-stream').classList.remove('on'); $('#health-stream').classList.add('off');
    es.close();
    setTimeout(connectStream, 1500);
  };
}

/* ------------------------------------------------------------------
   voice: hold to talk
   ------------------------------------------------------------------ */
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  let data = {};
  try { data = await r.json(); } catch (_) { /* no body */ }
  return { ok: r.ok, status: r.status, data };
}

function resetPipeline() {
  setStage('speech', 'active', 'listening…', '<span class="muted">recording 16 kHz mono</span>');
  setStage('recognition', undefined, '', '<span class="muted">embed → compare with 313 references → max per intent → threshold</span>');
  setStage('plan', undefined, '', '<span class="muted">state-conditioned expansion: room, mode, location, emergency latch</span>');
  setStage('execute', undefined, '', '<div class="exec-legend"><span></span><span>sent</span><span>ack</span><span>done</span><span>commit</span></div><ol class="actions" id="actions"></ol>');
  setStage('commit', undefined, '', '<span class="muted">device state per acknowledged action; room and mode only after the whole workflow</span>');
  $('#confirm').hidden = true;
  message('');
}

async function startTalk() {
  const mic = $('#mic');
  if (mic.classList.contains('live')) return;
  resetPipeline();
  const { ok, data } = await post('/api/recording/start');
  if (!ok) { message(data.error || 'Could not start recording.', 'bad'); setStage('speech', 'failed', 'mic'); return; }
  mic.classList.add('live');
  $('#mic-title').textContent = 'Listening…';
  $('#mic-detail').textContent = 'Release when you have finished speaking';
}

async function stopTalk() {
  const mic = $('#mic');
  if (!mic.classList.contains('live')) return;
  mic.classList.remove('live');
  $('#mic-title').textContent = 'Transcribing…';
  $('#mic-detail').textContent = 'faster-whisper, on this machine';
  setStage('speech', 'active', 'transcribing…');

  const { ok, data } = await post('/api/recording/stop');
  $('#mic-title').textContent = 'Hold to speak';
  $('#mic-detail').textContent = 'Release to transcribe and recognise';

  if (!ok) {
    message(data.error || 'Recognition failed.', 'bad');
    setStage('speech', 'failed', 'no speech');
    return;
  }

  // The stream already painted speech + recognition; this response
  // decides whether a confirmation is offered.
  if (data.decision === 'PREDICTED' && data.executable) {
    ui.pending = data.intent;
    $('#confirm-intent').textContent = data.intent;
    $('#confirm').hidden = false;
    message(data.message, '');
  } else {
    ui.pending = null;
    message(data.message || 'No executable command.', data.decision === 'PREDICTED' ? 'bad' : '');
  }
}

async function confirmIntent() {
  if (!ui.pending) return;
  const intent = ui.pending;
  $('#confirm').hidden = true;
  $('#confirm-yes').disabled = true;
  message(`Executing ${intent}…`, '');

  const { ok, status, data } = await post('/api/intent/confirm', { intent });
  $('#confirm-yes').disabled = false;
  ui.pending = null;

  if (ok) {
    message(data.degraded
      ? `${intent} completed with ${data.failed_actions} failed action(s) — best-effort workflow.`
      : `${intent} executed: ${data.executed_actions} action(s) acknowledged and committed.`, data.degraded ? 'bad' : 'ok');
    if (data.state) renderState(data.state);
    return;
  }
  const why = data.error || `HTTP ${status}`;
  message(data.status === 'blocked' ? `Refused — ${why}` : data.status === 'location_unknown' ? `Refused — ${why}` : `Failed — ${why}`, 'bad');
  if (data.state) renderState(data.state); else refreshState();
}

async function cancelIntent() {
  ui.pending = null;
  $('#confirm').hidden = true;
  await post('/api/intent/cancel');
  message('Cancelled. Nothing was sent to any device.', '');
  setStage('plan', undefined, 'cancelled');
}

async function confirmLocation(room) {
  const { ok, data } = await post('/api/location/confirm', { room });
  if (ok && data.state) renderState(data.state);
  else refreshState();
}

/* ------------------------------------------------------------------
   boot
   ------------------------------------------------------------------ */
function bind() {
  const mic = $('#mic');
  mic.addEventListener('mousedown', startTalk);
  mic.addEventListener('touchstart', (e) => { e.preventDefault(); startTalk(); }, { passive: false });
  window.addEventListener('mouseup', stopTalk);
  window.addEventListener('touchend', stopTalk);
  window.addEventListener('keydown', (e) => { if (e.code === 'Space' && !e.repeat && document.activeElement.tagName !== 'BUTTON') { e.preventDefault(); startTalk(); } });
  window.addEventListener('keyup', (e) => { if (e.code === 'Space') { e.preventDefault(); stopTalk(); } });

  $('#confirm-yes').addEventListener('click', confirmIntent);
  $('#confirm-no').addEventListener('click', cancelIntent);
  $('#probe-btn').addEventListener('click', probeNodes);
  $('#wire-clear').addEventListener('click', () => { $('#wire').innerHTML = ''; ui.wireRows = 0; });
  $('#room-picks').addEventListener('click', (e) => { const b = e.target.closest('button[data-room]'); if (b) confirmLocation(b.dataset.room); });
  $('#house').addEventListener('click', (e) => {
    const room = e.target.closest('.room');
    if (room && !ui.running) confirmLocation(room.dataset.room);
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  icons();
  bind();
  await backfill();
  connectStream();
  await refreshState();
  probeNodes();
  setInterval(refreshState, 6000);
  setInterval(probeNodes, 60000);
});
