const KEYWORD_STORAGE_KEY = 'taekine-tracked-keywords';
const KEYWORD_SYNC_KEY_STORAGE = 'taekine-keyword-sync-key';
const PRIMARY_KEYWORD_STORAGE = 'taekine-primary-keyword';
const PENDING_VOLUME = '검색량(측정대기)';
const PENDING_RANK = '-';
const LEGACY_PENDING_VOLUMES = new Set(['측정 대기', '검색량(측정 대기)']);
const DEFAULT_KEYWORDS = [{ value: '장현동맛집', rank: PENDING_RANK, volume: PENDING_VOLUME }];
const storedKeywords = JSON.parse(localStorage.getItem(KEYWORD_STORAGE_KEY) || 'null');
let keywordSyncEndpoint = '';
let rankHistory = [];
let primaryKeyword = localStorage.getItem(PRIMARY_KEYWORD_STORAGE) || '';
let keywordAddedAt = {};
let selectedPeriod = '1주';
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

function applyConfiguredKeywords(keywords, metadata = {}) {
  const configuredPrimary = metadata.primaryKeyword ?? metadata.primary_keyword;
  const storedPrimary = localStorage.getItem(PRIMARY_KEYWORD_STORAGE);
  primaryKeyword = keywords.includes(storedPrimary)
    ? storedPrimary
    : (keywords.includes(configuredPrimary)
      ? configuredPrimary
    : (keywords.includes(primaryKeyword) ? primaryKeyword : ''));
  if (primaryKeyword) localStorage.setItem(PRIMARY_KEYWORD_STORAGE, primaryKeyword);
  else localStorage.removeItem(PRIMARY_KEYWORD_STORAGE);
  keywordAddedAt = metadata.keywordAddedAt || metadata.keyword_added_at || keywordAddedAt;
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

async function syncKeywords(keywords, primary = primaryKeyword) {
  if (!keywordSyncEndpoint) throw new Error('키워드 동기화 서버가 아직 연결되지 않았습니다.');
  const adminKey = sessionStorage.getItem(KEYWORD_SYNC_KEY_STORAGE) || window.prompt('키워드 동기화키를 입력해 주세요.');
  if (!adminKey) throw new Error('동기화키 입력이 취소되었습니다.');
  const response = await fetch(`${keywordSyncEndpoint}/keywords`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-tracker-key': adminKey },
    body: JSON.stringify({ keywords, primaryKeyword: primary }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !Array.isArray(payload.keywords)) {
    if (response.status === 401) sessionStorage.removeItem(KEYWORD_SYNC_KEY_STORAGE);
    throw new Error(payload.error || '키워드 파일 저장에 실패했습니다.');
  }
  sessionStorage.setItem(KEYWORD_SYNC_KEY_STORAGE, adminKey);
  return payload;
}

function isNewKeyword(value) {
  const added = Date.parse(keywordAddedAt[value]);
  return Number.isFinite(added) && Date.now() - added >= 0 && Date.now() - added < 7 * 24 * 60 * 60 * 1000;
}

function selectedKeywordData() {
  return trackedKeywords.find((keyword) => keyword.value === selectedKeyword) || trackedKeywords[0];
}

function hasMeasuredSearchVolume(measurement) {
  return Boolean(measurement) && [
    'monthly_pc_searches',
    'monthly_mobile_searches',
    'monthly_searches',
  ].some((field) => Object.hasOwn(measurement, field));
}

function zeroSearchVolumeDevice(measurement) {
  if (!hasMeasuredSearchVolume(measurement)) return null;
  const pc = Number.isInteger(measurement?.monthly_pc_searches) ? measurement.monthly_pc_searches : 0;
  const mobile = Number.isInteger(measurement?.monthly_mobile_searches) ? measurement.monthly_mobile_searches : 0;
  if (mobile === 0 && pc > 0) return '모바일';
  if (pc === 0 && mobile > 0) return 'PC';
  return null;
}

function searchVolumeLabel(volume, zeroDevice = null) {
  if (volume === PENDING_VOLUME) return PENDING_VOLUME;
  return `월 ${volume}회${zeroDevice ? ` (${zeroDevice}: 0회)` : ''}`;
}

function displaySearchVolume(measurement) {
  const pc = Number.isInteger(measurement?.monthly_pc_searches) ? measurement.monthly_pc_searches : null;
  const mobile = Number.isInteger(measurement?.monthly_mobile_searches) ? measurement.monthly_mobile_searches : null;
  if (pc !== null && mobile !== null) return (pc + mobile).toLocaleString('ko-KR');
  if (hasMeasuredSearchVolume(measurement)) return ((pc || 0) + (mobile || 0)).toLocaleString('ko-KR');
  return PENDING_VOLUME;
}

function renderRankHistory(keyword) {
  const chart = document.querySelector('#rank-chart-pending');
  const points = rankHistory
    .filter((item) => item.keyword === keyword?.value && Number.isInteger(item.rank))
    .sort((left, right) => String(left.measured_at).localeCompare(String(right.measured_at)))
    .slice(-14);
  if (!points.length) {
    chart.textContent = '순위 이력이 쌓이면 최근 14일 추이가 표시됩니다.';
    return;
  }

  const ranks = points.map((item) => item.rank);
  const highest = Math.min(...ranks);
  const lowest = Math.max(...ranks);
  const width = 560;
  const height = 112;
  const padding = 18;
  const spread = Math.max(lowest - highest, 1);
  const coordinates = points.map((item, index) => {
    const x = padding + ((width - padding * 2) * index) / Math.max(points.length - 1, 1);
    const y = padding + ((height - padding * 2) * (item.rank - highest)) / spread;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  chart.innerHTML = `<svg class="rank-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="최근 ${points.length}회 순위 추이"><line x1="${padding}" y1="${padding}" x2="${width - padding}" y2="${padding}"/><line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}"/><polyline points="${coordinates}"/><text x="${padding}" y="12">${highest}위</text><text x="${padding}" y="${height - 3}">${lowest}위</text></svg>`;
  document.querySelector('.date-row span:first-child').textContent = `최근 ${points.length}회 · 순위추이`;
  document.querySelector('.date-row span:last-child').textContent = `오늘 · ${points.at(-1).rank}위`;
  const daysByPeriod = { '1주': 7, '1개월': 30, '3개월': 90, '전체': Infinity };
  const cutoff = Date.now() - daysByPeriod[selectedPeriod] * 24 * 60 * 60 * 1000;
  const detailPoints = rankHistory
    .filter((item) => item.keyword === keyword?.value && Number.isInteger(item.rank) && Date.parse(item.measured_at) >= cutoff)
    .sort((left, right) => String(left.measured_at).localeCompare(String(right.measured_at)));
  const detail = document.querySelector('#detail-chart-pending');
  if (!detailPoints.length) {
    detail.textContent = '선택한 기간에 순위 이력이 없습니다.';
    return;
  }
  const detailRanks = detailPoints.map((item) => item.rank);
  const start = detailRanks[0];
  const best = Math.min(...detailRanks);
  const worst = Math.max(...detailRanks);
  const dWidth = 560;
  const dHeight = 164;
  const dPadding = 22;
  const dSpread = Math.max(worst - best, 1);
  const detailCoordinates = detailPoints.map((item, index) => {
    const x = dPadding + ((dWidth - dPadding * 2) * index) / Math.max(detailPoints.length - 1, 1);
    const y = dPadding + ((dHeight - dPadding * 2) * (item.rank - best)) / dSpread;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  detail.innerHTML = `<svg class="rank-chart" viewBox="0 0 ${dWidth} ${dHeight}" role="img" aria-label="${selectedPeriod} 순위 추이"><polyline points="${detailCoordinates}"/><text x="${dPadding}" y="14">${best}위</text><text x="${dPadding}" y="${dHeight - 4}">${worst}위</text></svg>`;
  document.querySelector('.panel-heading p').textContent = `시작 ${start}위 · 최고 ${best}위 · 최저 ${worst}위`;
  document.querySelector('#peak-note').textContent = `최고 ${best}위`;
  document.querySelector('#low-note').textContent = `최저 ${worst}위`;
  const latest = detailPoints.at(-1);
  const volumeWasMeasured = hasMeasuredSearchVolume(latest);
  const pc = Number.isInteger(latest.monthly_pc_searches) ? latest.monthly_pc_searches.toLocaleString('ko-KR') : volumeWasMeasured ? '0' : '-';
  const mobile = Number.isInteger(latest.monthly_mobile_searches) ? latest.monthly_mobile_searches.toLocaleString('ko-KR') : volumeWasMeasured ? '0' : '-';
  const volume = displaySearchVolume(latest);
  document.querySelector('.volume-head span').innerHTML = `<strong>${searchVolumeLabel(volume, zeroSearchVolumeDevice(latest))}</strong> · 모바일 ${mobile} / PC ${pc}`;
  document.querySelector('.volume-pending').textContent = volume === PENDING_VOLUME ? '네이버 검색광고 API에서 실제 검색량을 수집합니다.' : '네이버 검색광고 API의 최근 월간 검색량입니다.';
}

function rankPresentation(keyword) {
  if (Number.isInteger(keyword?.rank)) return { value: keyword.rank, suffix: '위', label: `${keyword.rank}위`, measured: true };
  const visibleResultCount = Number(keyword?.visibleResultCount);
  if (keyword?.status === 'outside_top_100' && visibleResultCount >= 100) {
    return { value: 100, suffix: '위 밖', label: '100위 밖', measured: true };
  }
  if ((keyword?.status === 'outside_top_100' || keyword?.status === 'not_found_in_visible_results') && Number.isInteger(visibleResultCount)) {
    return { value: null, suffix: '', label: `상위 ${visibleResultCount}개 내 미발견`, measured: true, partial: true };
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
      <b class="keyword-rank">${presentation.partial ? `<small>${presentation.label}</small>` : presentation.value === null ? PENDING_RANK : `${presentation.value}<small>${presentation.suffix}</small>`}</b><span class="star ${keyword.value === primaryKeyword ? 'selected' : ''}" data-primary-keyword="${keyword.value}" role="button" aria-pressed="${keyword.value === primaryKeyword}" tabindex="0" aria-label="${keyword.value}을 가장 중요한 거점키워드로 선택">★</span><strong>${keyword.value}</strong>
      ${keyword.value === primaryKeyword ? '<em>가장 중요한 거점키워드</em>' : isNewKeyword(keyword.value) ? '<em>새로 등록한 추적키워드</em>' : ''}
      <span class="volume">${searchVolumeLabel(keyword.volume, keyword.zeroVolumeDevice)}</span><i>⌃</i>
    </button>`;
  }).join('');
  const deleteLine = document.querySelector('.keyword-delete-line');
  deleteLine.hidden = !current;
  document.querySelector('#keyword-delete').disabled = trackedKeywords.length === 0;
  updateKeywordHeading(current);
}

function updateKeywordHeading(keyword) {
  const value = keyword?.value || '추적 키워드';
  const volume = searchVolumeLabel(keyword?.volume || PENDING_RANK, keyword?.zeroVolumeDevice);
  const presentation = rankPresentation(keyword);
  document.querySelector('#main-keyword').textContent = `거점키워드 · ${value} · ${volume}`;
  document.querySelector('.rank-title strong').textContent = presentation.partial ? '미발견' : presentation.value ?? PENDING_RANK;
  document.querySelector('.rank-title span').textContent = presentation.partial ? presentation.label : presentation.suffix;
  document.querySelector('.rank-title span').hidden = !presentation.measured || (!presentation.partial && !presentation.suffix);
  document.querySelector('.rank-title em').textContent = presentation.partial ? '100위 밖으로 확정하지 않음' : presentation.measured ? '최근 측정 결과' : '순위(측정대기)';
  document.querySelector('.rank-time').textContent = keyword?.measuredAt ? `최근 측정 · ${keyword.measuredAt.replace('T', ' ')}` : 'GitHub Actions에서 첫 순위를 측정합니다';
  document.querySelector('.panel-heading > strong').innerHTML = presentation.measured
    ? presentation.partial
      ? `${presentation.label} <small>100위 밖으로 확정하지 않음</small>`
      : `${presentation.label} <small>측정 결과</small>`
    : `순위(측정대기) <small>첫 수집 후 표시</small>`;
  const detailChart = document.querySelector('.detail-chart');
  if (detailChart) detailChart.setAttribute('aria-label', `${value} 순위 변화`);
  renderRankHistory(keyword);
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
    rankHistory = Array.isArray(history.measurements) ? history.measurements : [];
    const sync = syncResponse.ok ? await syncResponse.json() : {};
    keywordSyncEndpoint = typeof sync.endpoint === 'string' ? sync.endpoint.replace(/\/$/, '') : '';
    if (keywordSyncEndpoint) {
      try {
        const response = await fetch(`${keywordSyncEndpoint}/keywords`, { cache: 'no-store' });
        const source = response.ok ? await response.json() : {};
        if (Array.isArray(source.keywords)) config = { ...config, ...source };
      } catch {
        setKeywordSyncStatus('파일 동기화 서버에 연결하지 못했어요. 저장된 설정을 표시합니다.');
      }
    }
    const configured = Array.isArray(config.keywords) ? config.keywords : [];
    applyConfiguredKeywords(configured, config);
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
        volume: displaySearchVolume(measurement),
        zeroVolumeDevice: zeroSearchVolumeDevice(measurement),
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
  const star = event.target.closest('[data-primary-keyword]');
  if (star) {
    const value = star.dataset.primaryKeyword;
    const previousPrimary = primaryKeyword;
    primaryKeyword = value;
    localStorage.setItem(PRIMARY_KEYWORD_STORAGE, value);
    renderKeywords();
    syncKeywords(trackedKeywords.map((keyword) => keyword.value), value).then((result) => {
      applyConfiguredKeywords(result.keywords, result);
      renderKeywords();
    }).catch((error) => {
      primaryKeyword = previousPrimary;
      if (previousPrimary) localStorage.setItem(PRIMARY_KEYWORD_STORAGE, previousPrimary);
      else localStorage.removeItem(PRIMARY_KEYWORD_STORAGE);
      renderKeywords();
      setKeywordSyncStatus(error.message);
    });
    return;
  }
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
    applyConfiguredKeywords(result.keywords, result);
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
    applyConfiguredKeywords(result.keywords, result);
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
  selectedPeriod = tab.dataset.period;
  updateKeywordHeading(selectedKeywordData());
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
