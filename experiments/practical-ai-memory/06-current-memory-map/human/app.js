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

const chineseDisplay = {
  'QA-current-active': '当前哪条保留规则指导这个项目的清理工作？',
  'QA-replacement-relation': '较早的 10 天保留规则应如何处理？',
  'QA-unresolved-conflict': '两条 Pulse 刷新结果支持什么结论？',
  'QA-scope-boundary': 'Orbit Quartz 预览规则可以在哪个范围内指导发布检查？',
  'QA-pending-observation': '出现一次第四次重试才成功的结果后，应如何处理？',
  'QB-current-active': '当前哪条归档规则具有维护决策权？',
  'QB-replacement-relation': '原来的 8 天归档记录还应承担什么作用？',
  'QB-unresolved-conflict': 'Cadence 时间间隔证据支持什么结论？',
  'QB-scope-boundary': 'Harbor Metal 渲染记录覆盖哪个环境？',
  'QB-pending-observation': '一次第五次尝试才恢复的结果应如何处理？',
  'QA1-vault-old': 'Vault 保留草案',
  'QA1-vault-new': 'Vault 保留决策',
  'QA1-spark': 'Spark 重试观察',
  'QA2-continue': '每次清理都继续使用它',
  'QA2-history': '在被替代后仅作为历史记录保留',
  'QA2-conflict': '把两条保留记录都视为尚未解决',
  'QA3-twelve': '立即采用 12 分钟',
  'QA3-thirty-six': '立即采用 36 分钟',
  'QA3-pause': '在比较解决前保留两个数值',
  'QA4-everywhere': '项目中的所有平台',
  'QA4-macos': '仅 macOS',
  'QA4-nowhere': '在下一次试验前不适用于任何平台',
  'QA5-promote': '把四次重试定为稳定规则',
  'QA5-discard': '未经 Review 直接删除该结果',
  'QA5-validate': '先验证，再修改恢复动作',
  'QB1-legacy': '归档窗口旧记录',
  'QB1-policy': '归档窗口策略',
  'QB1-finding': 'Circuit 恢复发现',
  'QB2-enforce': '对所有快照删除都执行它',
  'QB2-background': '在新策略之后仅作为背景信息使用',
  'QB2-unsettled': '将两个归档窗口都标记为存在争议',
  'QB3-fifteen': '将 15 分钟扫描标准化',
  'QB3-forty-two': '将 42 分钟扫描标准化',
  'QB3-hold': '在比较完成前保留两个未决结果',
  'QB4-all': '整个项目环境',
  'QB4-apple': '仅 macOS Review 环境',
  'QB4-none': '发布前不适用于任何环境',
  'QB5-adopt': '把五次尝试定为策略',
  'QB5-ignore': '永久忽略这次演练结果',
  'QB5-study': '在修改策略前收集重复证据',
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

function display(value) {
  return chineseDisplay[value] || value;
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
  text(elements.conditionLabel, condition.condition === 'state-table' ? '状态表' : '可视化地图');
  text(elements.progress, `第 ${state.questionIndex + 1} 题，共 ${condition.pack.questions.length} 题`);
  text(elements.questionTitle, display(question.id));
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
    label.append(input, document.createTextNode(display(choice.id)));
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
