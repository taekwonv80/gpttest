const KEYWORD_STORAGE_KEY = 'taekine-tracked-keywords';
const DEFAULT_KEYWORDS = [{ value: '장현동맛집', rank: 5, volume: '1,350' }];
let trackedKeywords = JSON.parse(localStorage.getItem(KEYWORD_STORAGE_KEY) || 'null') || DEFAULT_KEYWORDS;
let selectedKeyword = trackedKeywords[0]?.value || '';

function saveKeywords() {
  localStorage.setItem(KEYWORD_STORAGE_KEY, JSON.stringify(trackedKeywords));
}

function selectedKeywordData() {
  return trackedKeywords.find((keyword) => keyword.value === selectedKeyword) || trackedKeywords[0];
}

function renderKeywords() {
  const list = document.querySelector('#keyword-list');
  const current = selectedKeywordData();
  selectedKeyword = current?.value || '';
  list.innerHTML = trackedKeywords.map((keyword) => `
    <button class="keyword-row ${keyword.value === selectedKeyword ? 'selected' : ''}" type="button" data-keyword="${keyword.value}" aria-pressed="${keyword.value === selectedKeyword}">
      <b class="keyword-rank">${keyword.rank || '—'}<small>위</small></b><span class="star">★</span><strong>${keyword.value}</strong>
      <em>${keyword.value === DEFAULT_KEYWORDS[0].value ? '가장 중요한 거점키워드' : '새로 등록한 추적키워드'}</em>
      <span class="volume">${keyword.volume === '측정 대기' ? '측정 대기' : `월 ${keyword.volume || '—'}회`}</span><i>⌃</i>
    </button>`).join('');
  const deleteLine = document.querySelector('.keyword-delete-line');
  deleteLine.hidden = !current;
  document.querySelector('#keyword-delete').disabled = trackedKeywords.length === 0;
  updateKeywordHeading(current);
}

function updateKeywordHeading(keyword) {
  const value = keyword?.value || '추적 키워드';
  const volume = keyword?.volume === '측정 대기' ? '측정 대기' : `월 ${keyword?.volume || '—'}회`;
  document.querySelector('#main-keyword').textContent = `거점키워드 · ${value} · ${volume}`;
  document.querySelector('.rank-title strong').textContent = keyword?.rank && keyword.rank !== '—' ? keyword.rank : '—';
  document.querySelector('.panel-heading > strong').innerHTML = keyword?.rank && keyword.rank !== '—'
    ? `${keyword.rank}위 <small>보합</small>`
    : `측정 대기 <small>첫 수집 후 표시</small>`;
  document.querySelector('.detail-chart').setAttribute('aria-label', `${value} 순위 변화`);
}

async function loadServerTracker() {
  try {
    const [configResponse, historyResponse] = await Promise.all([
      fetch('data/tracker_config.json', { cache: 'no-store' }),
      fetch('data/rank_history.json', { cache: 'no-store' }),
    ]);
    const config = configResponse.ok ? await configResponse.json() : {};
    const history = historyResponse.ok ? await historyResponse.json() : {};
    for (const value of config.keywords || []) {
      if (!trackedKeywords.some((keyword) => keyword.value === value)) {
        trackedKeywords.push({ value, rank: '—', volume: '측정 대기' });
      }
    }
    const latest = {};
    for (const measurement of history.measurements || []) {
      const prior = latest[measurement.keyword];
      if (!prior || String(measurement.measured_at) > String(prior.measured_at)) latest[measurement.keyword] = measurement;
    }
    trackedKeywords = trackedKeywords.map((keyword) => {
      const measurement = latest[keyword.value];
      return measurement ? { ...keyword, rank: measurement.rank ?? '—', measuredAt: measurement.measured_at } : keyword;
    });
    saveKeywords();
    renderKeywords();
  } catch {
    // Keep the dashboard usable with its locally cached keywords offline.
  }
}

document.querySelector('#keyword-list').addEventListener('click', (event) => {
  const row = event.target.closest('[data-keyword]');
  if (!row) return;
  selectedKeyword = row.dataset.keyword;
  renderKeywords();
});

const keywordDialog = document.querySelector('#keyword-dialog');
document.querySelector('#keyword-add-open').addEventListener('click', () => {
  keywordDialog.showModal();
  document.querySelector('#keyword-input').focus();
});

document.querySelector('#keyword-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const input = document.querySelector('#keyword-input');
  const value = input.value.trim().replace(/\s+/g, ' ');
  if (!value || trackedKeywords.some((keyword) => keyword.value === value)) {
    input.setCustomValidity(value ? '이미 등록한 키워드예요.' : '키워드를 입력해 주세요.');
    input.reportValidity();
    return;
  }
  input.setCustomValidity('');
  trackedKeywords.push({ value, rank: '—', volume: '측정 대기' });
  selectedKeyword = value;
  saveKeywords();
  renderKeywords();
  input.value = '';
  keywordDialog.close();
});

document.querySelector('#keyword-delete').addEventListener('click', () => {
  const current = selectedKeywordData();
  if (!current || !confirm(`“${current.value}” 키워드 추적을 중단할까요?\n지금까지 기록된 순위 데이터는 유지됩니다.`)) return;
  trackedKeywords = trackedKeywords.filter((keyword) => keyword.value !== current.value);
  selectedKeyword = trackedKeywords[0]?.value || '';
  saveKeywords();
  renderKeywords();
});

document.querySelectorAll('.dialog-close').forEach((button) => button.addEventListener('click', () => button.closest('dialog').close()));

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
  document.querySelector('.detail-chart').setAttribute('aria-label', `${selectedKeyword} ${tab.dataset.period} 순위 변화`);
}));

document.querySelectorAll('[data-dismiss]').forEach((button) => button.addEventListener('click', () => {
  document.querySelector(`#${button.dataset.dismiss}`).hidden = true;
}));

const guide = document.querySelector('#guide-dialog');
document.querySelector('#guide-open').addEventListener('click', () => guide.showModal());

const missionDone = document.querySelector('#mission-done');
missionDone.addEventListener('click', () => {
  missionDone.classList.add('done'); missionDone.textContent = '기록했어요 ✓'; missionDone.disabled = true;
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
  button.classList.add('selected'); selectedQuickLog = button.textContent; logInput.value = selectedQuickLog; logInput.focus();
}));
function addLog() {
  const text = logInput.value.trim() || selectedQuickLog;
  if (!text) { logInput.focus(); return; }
  const item = document.createElement('li'); item.textContent = text; logList.prepend(item);
  logCount.textContent = String(logList.children.length); logInput.value = ''; selectedQuickLog = '';
  document.querySelectorAll('.log-chips button').forEach((item) => item.classList.remove('selected'));
}
document.querySelector('#log-submit').addEventListener('click', addLog);
logInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') addLog(); });

renderKeywords();
loadServerTracker();
