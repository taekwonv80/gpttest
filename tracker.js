const KEYWORD_STORAGE_KEY = 'taekine-tracked-keywords';
const KEYWORD_SYNC_KEY_STORAGE = 'taekine-keyword-sync-key';
const PENDING_VOLUME = '검색량(측정대기)';
const PENDING_RANK = '-';
const LEGACY_PENDING_VOLUMES = new Set(['측정 대기', '검색량(측정 대기)']);
const DEFAULT_KEYWORDS = [{ value: '장현동맛집', rank: PENDING_RANK, volume: PENDING_VOLUME }];
const storedKeywords = JSON.parse(localStorage.getItem(KEYWORD_STORAGE_KEY) || 'null');
let keywordSyncEndpoint = '';
let trackedKeywords = (storedKeywords || DEFAULT_KEYWORDS).map((keyword) => (
  keyword.value === '장현동맛집' && keyword.volume === '1,350' && !Number.isInteger(keyword.monthlySearches)
    ? { ...keyword, volume: PENDING_VOLUME }
    : LEGACY_PENDING_VOLUMES.has(keyword.volume)
      ? { ...keyword, volume: PENDING_VOLUME }
      : keyword
));
let selectedKeyword = trackedKeywords[0]?.value || '';

function saveKeywords() {
  localStorage.setItem(KEYWORD_STORAGE_KEY, JSON.stringify(trackedKeywords));
}

function setKeywordSyncStatus(message) {
  const status = document.querySelector('#keyword-sync-status');
  if (status) status.textContent = message;
}

function applyConfiguredKeywords(keywords) {
  const existing = new Map(trackedKeywords.map((keyword) => [keyword.value, keyword]));
  trackedKeywords = keywords.map((value) => existing.get(value) || {
    value,
    rank: PENDING_RANK,
    volume: PENDING_VOLUME,
  });
  selectedKeyword = trackedKeywords.some((keyword) => keyword.value === selectedKeyword)
    ? selectedKeyword
    : trackedKeywords[0]?.value || '';
}

async function syncKeywords(keywords) {
  if (!keywordSyncEndpoint) throw new Error('키워드 동기화 서버가 아직 연결되지 않았습니다.');
  const adminKey = sessionStorage.getItem(KEYWORD_SYNC_KEY_STORAGE) || window.prompt('키워드 동기화키를 입력해 주세요.');
  if (!adminKey) throw new Error('동기화키 입력이 취소되었습니다.');
  const response = await fetch(`${keywordSyncEndpoint}/keywords`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-tracker-key': adminKey },
    body: JSON.stringify({ keywords }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !Array.isArray(payload.keywords)) {
    if (response.status === 401) sessionStorage.removeItem(KEYWORD_SYNC_KEY_STORAGE);
    throw new Error(payload.error || '키워드 파일 저장에 실패했습니다.');
  }
  sessionStorage.setItem(KEYWORD_SYNC_KEY_STORAGE, adminKey);
  return payload;
}

function selectedKeywordData() {
  return trackedKeywords.find((keyword) => keyword.value === selectedKeyword) || trackedKeywords[0];
}

function rankPresentation(keyword) {
  if (Number.isInteger(keyword?.rank)) return { value: keyword.rank, suffix: '위', label: `${keyword.rank}위`, measured: true };
  if (keyword?.status === 'outside_top_100') return { value: 100, suffix: '위 밖', label: '100위 밖', measured: true };
  if (keyword?.status === 'not_found_in_visible_results' && Number.isInteger(keyword.visibleResultCount)) {
    return { value: keyword.visibleResultCount, suffix: '위 밖', label: `${keyword.visibleResultCount}위 밖`, measured: true };
  }
  return { value: null, suffix: '', label: PENDING_RANK, measured: false };
}

function renderKeywords() {
  const list = document.querySelector('#keyword-list');
  const current = selectedKeywordData();
  selectedKeyword = current?.value || '';
  list.innerHTML = trackedKeywords.map((keyword) => {
    const presentation = rankPresentation(keyword);
    return `
    <button class="keyword-row ${keyword.value === selectedKeyword ? 'selected' : ''}" type="button" data-keyword="${keyword.value}" aria-pressed="${keyword.value === selectedKeyword}">
      <b class="keyword-rank">${presentation.value === null ? PENDING_RANK : `${presentation.value}<small>${presentation.suffix}</small>`}</b><span class="star">★</span><strong>${keyword.value}</strong>
      <em>${keyword.value === DEFAULT_KEYWORDS[0].value ? '가장 중요한 거점키워드' : '새로 등록한 추적키워드'}</em>
      <span class="volume">${keyword.volume === PENDING_VOLUME ? PENDING_VOLUME : `월 ${keyword.volume || PENDING_RANK}회`}</span><i>⌃</i>
    </button>`;
  }).join('');
  const deleteLine = document.querySelector('.keyword-delete-line');
  deleteLine.hidden = !current;
  document.querySelector('#keyword-delete').disabled = trackedKeywords.length === 0;
  updateKeywordHeading(current);
}

function updateKeywordHeading(keyword) {
  const value = keyword?.value || '추적 키워드';
  const volume = keyword?.volume === PENDING_VOLUME ? PENDING_VOLUME : `월 ${keyword?.volume || PENDING_RANK}회`;
  const presentation = rankPresentation(keyword);
  document.querySelector('#main-keyword').textContent = `거점키워드 · ${value} · ${volume}`;
  document.querySelector('.rank-title strong').textContent = presentation.value ?? PENDING_RANK;
  document.querySelector('.rank-title span').textContent = presentation.suffix;
  document.querySelector('.rank-title span').hidden = !presentation.measured;
  document.querySelector('.rank-title em').textContent = presentation.measured ? '최근 측정 결과' : '순위(측정대기)';
  document.querySelector('.rank-time').textContent = keyword?.measuredAt ? `최근 측정 · ${keyword.measuredAt.replace('T', ' ')}` : 'GitHub Actions에서 첫 순위를 측정합니다';
  document.querySelector('.panel-heading > strong').innerHTML = presentation.measured
    ? `${presentation.label} <small>측정 결과</small>`
    : `순위(측정대기) <small>첫 수집 후 표시</small>`;
  const detailChart = document.querySelector('.detail-chart');
  if (detailChart) detailChart.setAttribute('aria-label', `${value} 순위 변화`);
  document.querySelector('#rank-chart-pending').textContent = presentation.measured
    ? '순위 이력이 쌓이면 최근 14일 추이가 표시됩니다.'
    : '첫 순위 측정 후 최근 14일 추이가 표시됩니다.';
  document.querySelector('#detail-chart-pending').textContent = presentation.measured
    ? '측정 이력을 기준으로 기간별 추이가 표시됩니다.'
    : '첫 순위 측정 후 기간별 추이가 표시됩니다.';
}

async function loadServerTracker() {
  try {
    const [configResponse, historyResponse, syncResponse] = await Promise.all([
      fetch('data/tracker_config.json', { cache: 'no-store' }),
      fetch('data/rank_history.json', { cache: 'no-store' }),
      fetch('data/keyword_sync.json', { cache: 'no-store' }),
    ]);
    let config = configResponse.ok ? await configResponse.json() : {};
    const history = historyResponse.ok ? await historyResponse.json() : {};
    const sync = syncResponse.ok ? await syncResponse.json() : {};
    keywordSyncEndpoint = typeof sync.endpoint === 'string' ? sync.endpoint.replace(/\/$/, '') : '';
    if (keywordSyncEndpoint) {
      try {
        const response = await fetch(`${keywordSyncEndpoint}/keywords`, { cache: 'no-store' });
        const source = response.ok ? await response.json() : {};
        if (Array.isArray(source.keywords)) config = { ...config, keywords: source.keywords };
      } catch {
        setKeywordSyncStatus('파일 동기화 서버에 연결하지 못했어요. 저장된 설정을 표시합니다.');
      }
    }
    const configured = Array.isArray(config.keywords) ? config.keywords : [];
    applyConfiguredKeywords(configured);
    const latest = {};
    for (const measurement of history.measurements || []) {
      const prior = latest[measurement.keyword];
      if (!prior || String(measurement.measured_at) > String(prior.measured_at)) latest[measurement.keyword] = measurement;
    }
    trackedKeywords = trackedKeywords.map((keyword) => {
      const measurement = latest[keyword.value];
      return measurement ? {
        ...keyword,
        rank: measurement.rank ?? PENDING_RANK,
        measuredAt: measurement.measured_at,
        status: measurement.status,
        visibleResultCount: Number.isInteger(measurement.visible_result_count) ? measurement.visible_result_count : null,
        // 검색량 값이 응답에 실제로 있을 때만 화면에 표시한다.
        // 과거 브라우저에 남은 예시값을 실측값처럼 보여주면 안 된다.
        monthlySearches: Number.isInteger(measurement.monthly_searches) ? measurement.monthly_searches : null,
        volume: Number.isInteger(measurement.monthly_searches)
          ? measurement.monthly_searches.toLocaleString('ko-KR')
          : PENDING_VOLUME,
      } : keyword;
    });
    saveKeywords();
    renderKeywords();
    setKeywordSyncStatus(keywordSyncEndpoint
      ? '키워드 파일과 동기화됨 · 등록 또는 삭제하면 바로 순위 측정을 요청합니다.'
      : '자동동기화 서버를 연결하면 등록·삭제가 파일에 저장됩니다.');
  } catch {
    setKeywordSyncStatus('키워드 설정을 불러오지 못했어요.');
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

document.querySelector('#keyword-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = document.querySelector('#keyword-input');
  const value = input.value.trim().replace(/\s+/g, ' ');
  if (!value || trackedKeywords.some((keyword) => keyword.value === value)) {
    input.setCustomValidity(value ? '이미 등록한 키워드예요.' : '키워드를 입력해 주세요.');
    input.reportValidity();
    return;
  }
  input.setCustomValidity('');
  try {
    setKeywordSyncStatus('키워드 파일에 저장하고 순위 측정을 요청하는 중이에요.');
    const result = await syncKeywords([...trackedKeywords.map((keyword) => keyword.value), value]);
    applyConfiguredKeywords(result.keywords);
    selectedKeyword = value;
    saveKeywords();
    renderKeywords();
    input.value = '';
    keywordDialog.close();
    setKeywordSyncStatus('키워드 파일에 저장됐어요 · 순위 측정을 요청했습니다.');
  } catch (error) {
    setKeywordSyncStatus(error.message);
  }
});

document.querySelector('#keyword-delete').addEventListener('click', async () => {
  const current = selectedKeywordData();
  if (!current || !confirm(`“${current.value}” 키워드 추적을 중단할까요?\n지금까지 기록된 순위 데이터는 유지됩니다.`)) return;
  try {
    setKeywordSyncStatus('키워드 파일을 갱신하는 중이에요.');
    const result = await syncKeywords(trackedKeywords.filter((keyword) => keyword.value !== current.value).map((keyword) => keyword.value));
    applyConfiguredKeywords(result.keywords);
    saveKeywords();
    renderKeywords();
    setKeywordSyncStatus('키워드 파일에서 삭제됐어요 · 순위 측정을 요청했습니다.');
  } catch (error) {
    setKeywordSyncStatus(error.message);
  }
});

document.querySelectorAll('.dialog-close').forEach((button) => button.addEventListener('click', () => button.closest('dialog').close()));

const tabs = document.querySelectorAll('[data-period]');
tabs.forEach((tab) => tab.addEventListener('click', () => {
  tabs.forEach((item) => { item.classList.remove('active'); item.setAttribute('aria-selected', 'false'); });
  tab.classList.add('active'); tab.setAttribute('aria-selected', 'true');
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
  document.querySelector('#season-count').textContent = '끝낸 준비(설정대기)';
  document.querySelector('#season-progress').style.width = '0%';
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
