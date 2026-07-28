const state = {
  session: null,
  conditionIndex: 0,
  questionIndex: 0,
  currentStartedAt: 0,
  conditionStartedAt: 0,
  conditions: [],
  currentAnswers: [],
  detailOpens: 0,
  answerChanges: 0,
  confidence: null,
};

const elements = {
  status: document.querySelector('#status'),
  trial: document.querySelector('#trial'),
  workspace: document.querySelector('#workspace'),
  conditionLabel: document.querySelector('#condition-label'),
  progress: document.querySelector('#progress'),
  questionTitle: document.querySelector('#question-title'),
  answers: document.querySelector('#answers'),
  next: document.querySelector('#next'),
  detailToggle: document.querySelector('#detail-toggle'),
  detail: document.querySelector('#detail'),
  confidence: document.querySelector('#confidence'),
  confidenceOptions: document.querySelector('#confidence-options'),
  continue: document.querySelector('#continue'),
  complete: document.querySelector('#complete'),
};

function text(element, value) {
  element.textContent = value;
}

function currentCondition() {
  return state.session.conditions[state.conditionIndex];
}

function currentQuestion() {
  return currentCondition().pack.questions[state.questionIndex];
}

function renderWorkspace(condition) {
  elements.workspace.replaceChildren();
  if (condition.condition === 'state-table') {
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th>Record</th><th>Status</th><th>Scope</th><th>Relation</th></tr></thead>';
    const body = document.createElement('tbody');
    condition.pack.records.forEach((record) => {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${record.title}</td><td>${record.status}</td><td>${record.scope}</td><td>${record.relations.map((item) => item.type).join(', ') || 'none'}</td>`;
      body.append(row);
    });
    table.append(body);
    elements.workspace.append(table);
    return;
  }
  const map = document.createElement('div');
  map.className = 'map';
  condition.pack.records.forEach((record) => {
    const node = document.createElement('article');
    node.className = `node status-${record.status}`;
    node.innerHTML = `<p class="node-status">${record.status}</p><h3>${record.title}</h3><p>${record.scope}</p><p>${record.relations.map((item) => item.type).join(' / ') || 'no relation'}</p>`;
    map.append(node);
  });
  elements.workspace.append(map);
}

function renderQuestion() {
  const condition = currentCondition();
  const question = currentQuestion();
  state.currentStartedAt = performance.now();
  elements.detail.hidden = true;
  elements.detailToggle.setAttribute('aria-expanded', 'false');
  elements.next.disabled = true;
  renderWorkspace(condition);
  text(elements.conditionLabel, condition.condition === 'state-table' ? 'State table' : 'Visual map');
  text(elements.progress, `Question ${state.questionIndex + 1} of ${condition.pack.questions.length}`);
  text(elements.questionTitle, question.prompt);
  elements.answers.replaceChildren();
  let answered = false;
  question.choices.forEach((choice) => {
    const label = document.createElement('label');
    label.className = 'choice';
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = 'answer';
    input.value = choice.id;
    input.addEventListener('change', () => {
      if (answered) state.answerChanges += 1;
      answered = true;
      elements.next.disabled = false;
    });
    label.append(input, document.createTextNode(choice.label));
    elements.answers.append(label);
  });
  elements.detail.replaceChildren(...condition.pack.records.map((record) => {
    const item = document.createElement('p');
    item.textContent = `${record.title}: ${record.detail} Source: ${record.source}`;
    return item;
  }));
}

function recordAnswer() {
  const selected = elements.answers.querySelector('input:checked');
  if (!selected) return false;
  state.currentAnswers.push({
    question_id: currentQuestion().id,
    selected_choice: selected.value,
    elapsed_ms: Math.max(1, Math.round(performance.now() - state.currentStartedAt)),
  });
  return true;
}

function renderConfidence() {
  elements.trial.hidden = true;
  elements.confidence.hidden = false;
  elements.confidenceOptions.replaceChildren();
  for (let value = 1; value <= 5; value += 1) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'confidence-choice';
    button.textContent = String(value);
    button.addEventListener('click', () => {
      state.confidence = value;
      [...elements.confidenceOptions.children].forEach((item) => item.classList.toggle('selected', item === button));
      elements.continue.disabled = false;
    });
    elements.confidenceOptions.append(button);
  }
}

function advanceQuestion() {
  if (!recordAnswer()) return;
  state.questionIndex += 1;
  if (state.questionIndex < currentCondition().pack.questions.length) {
    renderQuestion();
  } else {
    renderConfidence();
  }
}

async function finishCondition() {
  const condition = currentCondition();
  state.conditions.push({
    condition: condition.condition,
    pack_id: condition.pack_id,
    elapsed_ms: Math.max(1, Math.round(performance.now() - state.conditionStartedAt)),
    correct: 0,
    total: condition.pack.questions.length,
    detail_opens: state.detailOpens,
    answer_changes: state.answerChanges,
    confidence: state.confidence,
    events: state.currentAnswers,
  });
  state.conditionIndex += 1;
  state.questionIndex = 0;
  state.currentAnswers = [];
  state.detailOpens = 0;
  state.answerChanges = 0;
  state.confidence = null;
  elements.confidence.hidden = true;
  if (state.conditionIndex < state.session.conditions.length) {
    elements.trial.hidden = false;
    state.conditionStartedAt = performance.now();
    renderQuestion();
    return;
  }
  const response = await fetch('/api/complete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_id: state.session.session_id,
      condition_order: state.session.condition_order,
      conditions: state.conditions,
    }),
  });
  if (!response.ok) throw new Error('The local trial could not be recorded.');
  elements.complete.hidden = false;
  text(elements.status, 'Complete');
}

elements.next.addEventListener('click', advanceQuestion);
elements.detailToggle.addEventListener('click', () => {
  const willOpen = elements.detail.hidden;
  elements.detail.hidden = !willOpen;
  elements.detailToggle.setAttribute('aria-expanded', String(willOpen));
  if (willOpen) state.detailOpens += 1;
});
elements.continue.addEventListener('click', () => finishCondition().catch((error) => text(elements.status, error.message)));

async function start() {
  try {
    const response = await fetch('/api/session');
    if (!response.ok) throw new Error('The local session could not be created.');
    state.session = await response.json();
    state.conditionStartedAt = performance.now();
    elements.trial.hidden = false;
    text(elements.status, 'Synthetic data only');
    renderQuestion();
  } catch (error) {
    text(elements.status, error.message);
  }
}

start();
