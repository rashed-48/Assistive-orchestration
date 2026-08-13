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
const marginScore = document.querySelector('#margin-score');
const topResults = document.querySelector('#top-results');

let recording = false;

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
  const decision = data.decision.toLowerCase();
  const readableIntent = data.intent || data.top_results[0]?.intent || 'No accepted intent';
  const detail = data.decision === 'ACCEPTED' ? 'Select the microphone to record another command.' : data.decision === 'AMBIGUOUS' ? 'Record a more specific clarification.' : 'Try recording your command again.';
  setStage('idle', data.decision === 'ACCEPTED' ? 'Command complete' : 'Let’s try again', detail);
  setPill(data.decision, decision);
  transcript.textContent = `“${data.transcription}”`;
  transcript.classList.add('has-text');
  intentName.textContent = readableIntent;
  resultMessage.textContent = data.message;
  similarityScore.textContent = `${Math.round(data.similarity_score * 100)}%`;
  marginScore.textContent = `${Math.round(data.margin * 100)} pts`;
  topResults.innerHTML = data.top_results.map((item) => `<li><span>${item.intent}</span><b>${Math.round(item.score * 100)}%</b></li>`).join('');
  emptyResult.hidden = true;
  resultContent.hidden = false;
}

async function request(endpoint) {
  const response = await fetch(endpoint, { method: 'POST' });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong.');
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

lucide.createIcons();
