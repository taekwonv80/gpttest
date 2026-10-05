const tabs = document.querySelectorAll('[data-period]');
const configs = {
  '1주': ['최고 3위 (10/1)', '최저 13위 (9/30)'],
  '1개월': ['최고 3위 (10/1)', '최저 15위 (9/7)'],
  '3개월': ['최고 3위 (10/1)', '최저 17위 (9/7)'],
  '전체': ['최고 3위 (10/1)', '최저 17위 (9/7)'],
};

tabs.forEach((tab) => tab.addEventListener('click', () => {
  tabs.forEach((item) => { item.classList.remove('active'); item.setAttribute('aria-selected', 'false'); });
  tab.classList.add('active'); tab.setAttribute('aria-selected', 'true');
  document.querySelector('#peak-note').textContent = configs[tab.dataset.period][0];
  document.querySelector('#low-note').textContent = configs[tab.dataset.period][1];
  document.querySelector('.detail-chart').setAttribute('aria-label', `장현동맛집 ${tab.dataset.period} 순위 변화`);
}));

document.querySelectorAll('[data-dismiss]').forEach((button) => button.addEventListener('click', () => {
  document.querySelector(`#${button.dataset.dismiss}`).hidden = true;
}));

const guide = document.querySelector('#guide-dialog');
document.querySelector('#guide-open').addEventListener('click', () => guide.showModal());
document.querySelector('.dialog-close').addEventListener('click', () => guide.close());

const missionDone = document.querySelector('#mission-done');
missionDone.addEventListener('click', () => {
  missionDone.classList.add('done');
  missionDone.textContent = '기록했어요 ✓';
  missionDone.disabled = true;
});

document.querySelectorAll('[data-feedback]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-feedback]').forEach((item) => item.classList.remove('selected'));
  button.classList.add('selected');
}));

const seasonCheck = document.querySelector('#season-check');
seasonCheck.addEventListener('change', () => {
  document.querySelector('#season-count').textContent = seasonCheck.checked ? '끝낸 준비 2 / 7' : '끝낸 준비 1 / 7';
  document.querySelector('#season-progress').style.width = seasonCheck.checked ? '29%' : '14%';
});

const logInput = document.querySelector('#log-input');
const logList = document.querySelector('#log-list');
const logCount = document.querySelector('#log-count');
let selectedQuickLog = '';

document.querySelectorAll('.log-chips button').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.log-chips button').forEach((item) => item.classList.remove('selected'));
  button.classList.add('selected');
  selectedQuickLog = button.textContent;
  logInput.value = selectedQuickLog;
  logInput.focus();
}));

function addLog() {
  const text = logInput.value.trim() || selectedQuickLog;
  if (!text) { logInput.focus(); return; }
  const item = document.createElement('li');
  item.textContent = text;
  logList.prepend(item);
  logCount.textContent = String(logList.children.length);
  logInput.value = '';
  selectedQuickLog = '';
  document.querySelectorAll('.log-chips button').forEach((item) => item.classList.remove('selected'));
}
document.querySelector('#log-submit').addEventListener('click', addLog);
logInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') addLog(); });
