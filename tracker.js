const KEYWORD_STORAGE_KEY = 'taekine-tracked-keywords';
const KEYWORD_SYNC_KEY_STORAGE = 'taekine-keyword-sync-key';
const PRIMARY_KEYWORD_STORAGE = 'taekine-primary-keyword';
const MISSION_STATE_STORAGE = 'taekine-mission-state';
const ACTIVITY_LOG_STORAGE = 'taekine-activity-log';
const DESCRIPTION_DRAFT_STORAGE = 'taekine-description-draft';
const SEASON_PROGRESS_STORAGE = 'taekine-season-progress';
const SEASON_STAGE_MODULE_URL = 'https://ai.euncoach.com/components/season-dashboard-stages.generated.js';
const PENDING_VOLUME = '실제 검색 횟수(측정대기)';
const PENDING_RANK = '-';
const LEGACY_PENDING_VOLUMES = new Set(['측정 대기', '검색량(측정 대기)']);
const DEFAULT_KEYWORDS = [{ value: '장현동맛집', rank: PENDING_RANK, volume: PENDING_VOLUME }];
const storedKeywords = JSON.parse(localStorage.getItem(KEYWORD_STORAGE_KEY) || 'null');
let keywordSyncEndpoint = '';
let rankHistory = [];
let placeDailyRows = [];
let performancePeriod = 'recent30';
let showAllPerformanceActivities = false;
let selectedWeeklyReport = '';
let primaryKeyword = localStorage.getItem(PRIMARY_KEYWORD_STORAGE) || '';
let keywordAddedAt = {};
let selectedPeriod = '1주';
let placeName = '은경이네';
let activeMission = null;
let seasonStageModulePromise = null;
let seasonPlannerMonth = '';
let seasonPlannerFocusKey = '';
let seasonPlannerSelectedDate = '';
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

function trackerAdminKey() {
  const saved = sessionStorage.getItem(KEYWORD_SYNC_KEY_STORAGE);
  const adminKey = saved || window.prompt('동기화키를 입력해 주세요.');
  if (!adminKey) throw new Error('동기화키 입력이 취소되었습니다.');
  sessionStorage.setItem(KEYWORD_SYNC_KEY_STORAGE, adminKey);
  return adminKey;
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
  const adminKey = trackerAdminKey();
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
  return payload;
}

async function syncActivity(kind, text) {
  if (!keywordSyncEndpoint) return;
  const response = await fetch(`${keywordSyncEndpoint}/activity`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-tracker-key': trackerAdminKey() },
    body: JSON.stringify({ kind, text }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !Array.isArray(payload.logs)) {
    if (response.status === 401) sessionStorage.removeItem(KEYWORD_SYNC_KEY_STORAGE);
    throw new Error(payload.error || '활동 기록 저장에 실패했습니다.');
  }
  localStorage.setItem(ACTIVITY_LOG_STORAGE, JSON.stringify(payload.logs));
  renderActivityLogs();
}

async function loadSyncedActivities() {
  if (!keywordSyncEndpoint) return;
  try {
    const response = await fetch(`${keywordSyncEndpoint}/activity`, { cache: 'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(payload.logs)) return;
    localStorage.setItem(ACTIVITY_LOG_STORAGE, JSON.stringify(payload.logs));
    renderActivityLogs();
  } catch {
    // The dashboard remains usable with its most recently stored activity log.
  }
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
  return `실제 검색 횟수: ${volume}회${zeroDevice ? ` (${zeroDevice}: 0회)` : ''}`;
}

function displaySearchVolume(measurement) {
  const pc = Number.isInteger(measurement?.monthly_pc_searches) ? measurement.monthly_pc_searches : null;
  const mobile = Number.isInteger(measurement?.monthly_mobile_searches) ? measurement.monthly_mobile_searches : null;
  if (pc !== null && mobile !== null) return (pc + mobile).toLocaleString('ko-KR');
  if (hasMeasuredSearchVolume(measurement)) return ((pc || 0) + (mobile || 0)).toLocaleString('ko-KR');
  return PENDING_VOLUME;
}

function rankCoachCopy(keyword) {
  const points = rankHistory
    .filter((item) => item.keyword === keyword && Number.isInteger(item.rank))
    .sort((left, right) => String(left.measured_at).localeCompare(String(right.measured_at)));
  const note = document.querySelector('.ai-note');
  if (!note) return;
  const setCopy = (copy) => {
    const label = document.createElement('b');
    label.textContent = 'AI 마케터:';
    note.replaceChildren(label, document.createTextNode(` ${copy}`));
  };
  const latest = points.at(-1);
  const previous = points.at(-2);
  if (!latest) {
    setCopy('첫 순위가 측정되면 순위 흐름과 지금 챙길 한 가지를 데이터에 맞춰 안내합니다.');
    return;
  }
  if (!previous) {
    setCopy(`${latest.rank}위의 첫 기록이에요. 같은 기준의 순위가 더 쌓이면 오름·내림 흐름에 맞춰 다음 할 일을 안내합니다.`);
    return;
  }
  const change = latest.rank - previous.rank;
  if (change < 0) {
    setCopy(`지난 측정 ${previous.rank}위에서 ${latest.rank}위로 ${Math.abs(change)}위 올랐어요. 새 리뷰 답글과 대표사진처럼 이미 하던 관리를 이어가 보세요.`);
  } else if (change > 0) {
    setCopy(`지난 측정 ${previous.rank}위에서 ${latest.rank}위로 ${change}위 내려왔어요. 오늘은 새 리뷰 답글, 대표사진, 소식 중 바로 확인할 수 있는 한 가지만 점검해 보세요.`);
  } else if (latest.rank <= 5) {
    setCopy(`${latest.rank}위로 상위권을 유지하고 있어요. 손님이 보는 대표사진과 최근 소식을 최신 상태로 이어가 보세요.`);
  } else {
    setCopy(`최근 두 번 모두 ${latest.rank}위로 큰 변화 없이 유지 중이에요. 오늘은 리뷰 답글이나 소식 한 건처럼 부담이 작은 관리부터 챙겨보세요.`);
  }
}

function renderSearchVolumeTrend(keyword) {
  const bars = document.querySelector('#volume-bars');
  const months = document.querySelector('#volume-months');
  if (!bars || !months) return;

  const today = new Date();
  const currentMonth = today.getMonth() + 1;
  // 진행 중인 이번 달은 확정 월별 데이터가 아니므로, 최근 12개 완료 월만 표시한다.
  const dates = Array.from({ length: 12 }, (_, index) => new Date(
    index + 1 >= currentMonth ? today.getFullYear() - 1 : today.getFullYear(),
    index,
    1,
  ));
  const trendMeasurement = rankHistory
    .filter((item) => item.keyword === keyword && Array.isArray(item.monthly_trend) && item.monthly_trend.length)
    .sort((left, right) => String(left.measured_at).localeCompare(String(right.measured_at)))
    .at(-1);
  const ratioByMonth = new Map();
  for (const point of trendMeasurement?.monthly_trend || []) {
    if (typeof point?.month === 'string' && Number.isFinite(point?.ratio)) ratioByMonth.set(point.month, point.ratio);
  }
  let values = dates.map((date) => ratioByMonth.get(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`) ?? null);
  const measuredValues = values.filter((value) => value !== null);
  const hasUsableTrend = measuredValues.some((value) => value > 0);
  const maximum = Math.max(...measuredValues, 1);
  const peakValue = measuredValues.length ? Math.max(...measuredValues) : null;
  const peakIndex = peakValue === null || peakValue <= 0 ? -1 : values.indexOf(peakValue);
  const currentIndex = today.getMonth();
  bars.classList.toggle('volume-trend-unavailable', !hasUsableTrend);
  bars.innerHTML = values.map((value, index) => {
    const states = [value === null ? 'volume-bar--pending' : 'volume-bar--measured'];
    if (index === peakIndex) states.push('volume-bar--peak');
    if (index === currentIndex) states.push('volume-bar--current');
    const height = value === null ? '' : ` style="height:${Math.round((value / maximum) * 100)}%"`;
    const label = value === null ? '검색 추이 미수집' : `검색지수 ${value.toLocaleString('ko-KR')}`;
    return `<i class="${states.join(' ')}"${height} title="${dates[index].getMonth() + 1}월 ${label}"></i>`;
  }).join('');
  months.innerHTML = dates.map((date) => {
    const isLastYear = date.getFullYear() !== today.getFullYear();
    return `<span>${date.getMonth() + 1}월${isLastYear ? '<small>(작년)</small>' : ''}</span>`;
  }).join('');

  const peak = document.querySelector('#volume-peak');
  const timing = document.querySelector('#volume-timing');
  const volumePending = document.querySelector('.volume-pending');
  if (!hasUsableTrend) {
    const hasZeroOnlyTrend = measuredValues.length > 0;
    peak.innerHTML = `<b>피크</b> ${hasZeroOnlyTrend ? '월별 검색지수 표본이 부족해 피크를 계산하지 않습니다.' : '월별 검색지수 수집 후 표시됩니다.'}`;
    timing.innerHTML = '<b class="mint">타이밍</b> 월별 검색지수가 쌓이면 계절별 준비 시점을 안내합니다.';
    if (volumePending) {
      volumePending.dataset.trendState = hasZeroOnlyTrend ? 'zero-only' : 'pending';
      volumePending.textContent = hasZeroOnlyTrend
        ? '최근 실제 검색 횟수와 별개로, 완료된 월의 데이터랩 상대지수는 표본 부족으로 표시하지 않습니다.'
        : '완료된 월의 검색지수를 수집하면 최근 12개월 추이가 표시됩니다.';
    }
    return;
  }
  if (volumePending) {
    volumePending.dataset.trendState = 'measured';
    volumePending.textContent = '막대는 데이터랩 최근 12개월 검색지수(상대값)입니다.';
  }
  const peakMonth = dates[peakIndex].getMonth() + 1;
  const prepMonth = peakMonth === 1 ? 12 : peakMonth - 1;
  const average = measuredValues.reduce((sum, value) => sum + value, 0) / measuredValues.length;
  const strength = average > 0 ? peakValue / average : 0;
  peak.innerHTML = `<b>피크</b> ${peakMonth}월 검색지수가 가장 높아요. (평달의 ${strength.toFixed(1)}배)`;
  timing.innerHTML = `<b class="mint">타이밍</b> 피크 준비는 <strong>${prepMonth}월부터</strong>가 좋아요. 시즌 준비 알림과 이어서 챙겨드려요.`;
}

function renderRankHistory(keyword, detailKeyword = keyword) {
  rankCoachCopy(detailKeyword?.value);
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
  const previous = points.at(-2);
  document.querySelector('.date-row span:first-child').textContent = previous
    ? `최근 14일 · ${performanceDateLabel(previous.measured_at)} · ${previous.rank}위`
    : '최근 14일 · 이전 순위 없음';
  document.querySelector('.date-row span:last-child').textContent = `오늘 · ${points.at(-1).rank}위`;
  const daysByPeriod = { '1주': 7, '1개월': 30, '3개월': 90, '전체': Infinity };
  const cutoff = Date.now() - daysByPeriod[selectedPeriod] * 24 * 60 * 60 * 1000;
  const detailPoints = rankHistory
    .filter((item) => item.keyword === detailKeyword?.value && Number.isInteger(item.rank) && Date.parse(item.measured_at) >= cutoff)
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
  document.querySelector('.volume-head b').textContent = '실제 검색 횟수';
  document.querySelector('.volume-head span').innerHTML = `<strong>${searchVolumeLabel(volume, zeroSearchVolumeDevice(latest))}</strong> · 모바일 ${mobile} / PC ${pc}`;
  const volumePending = document.querySelector('.volume-pending');
  if (volumePending?.dataset.trendState !== 'zero-only') {
    volumePending.textContent = volume === PENDING_VOLUME ? '네이버 검색광고 API에서 실제 검색 횟수를 수집합니다.' : '네이버 검색광고 API의 실제 월간 검색 횟수입니다.';
  }
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
      <span class="volume">${searchVolumeLabel(keyword.volume, keyword.zeroVolumeDevice)}</span>
    </button>`;
  }).join('');
  const deleteLine = document.querySelector('.keyword-delete-line');
  deleteLine.hidden = !current;
  document.querySelector('#keyword-delete').disabled = trackedKeywords.length === 0;
  updateKeywordHeading(current);
}

function updateKeywordHeading(keyword) {
  const primary = trackedKeywords.find((item) => item.value === primaryKeyword) || keyword;
  const value = primary?.value || '추적 키워드';
  const volume = searchVolumeLabel(primary?.volume || PENDING_RANK, primary?.zeroVolumeDevice);
  const presentation = rankPresentation(primary);
  const selectedPresentation = rankPresentation(keyword);
  document.querySelector('#main-keyword').textContent = `거점키워드 · ${value} · ${volume}`;
  document.querySelector('.rank-title strong').textContent = presentation.partial ? '미발견' : presentation.value ?? PENDING_RANK;
  document.querySelector('.rank-title span').textContent = presentation.partial ? presentation.label : presentation.suffix;
  document.querySelector('.rank-title span').hidden = !presentation.measured || (!presentation.partial && !presentation.suffix);
  document.querySelector('.rank-title em').textContent = presentation.partial ? '100위 밖으로 확정하지 않음' : presentation.measured ? '최근 측정 결과' : '순위(측정대기)';
  document.querySelector('.rank-time').textContent = primary?.measuredAt ? `최근 측정 · ${primary.measuredAt.replace('T', ' ')}` : 'GitHub Actions에서 첫 순위를 측정합니다';
  document.querySelector('.panel-heading > strong').innerHTML = selectedPresentation.measured
    ? selectedPresentation.partial
      ? `${selectedPresentation.label} <small>100위 밖으로 확정하지 않음</small>`
      : `${selectedPresentation.label} <small>측정 결과</small>`
    : `순위(측정대기) <small>첫 수집 후 표시</small>`;
  const detailChart = document.querySelector('.detail-chart');
  if (detailChart) detailChart.setAttribute('aria-label', `${keyword?.value || '추적 키워드'} 순위 변화`);
  renderRankHistory(primary, keyword);
  renderSearchVolumeTrend(keyword?.value);
}

async function loadServerTracker() {
  try {
    const [configResponse, storeProfileResponse, historyResponse, syncResponse, placeDailyResponse] = await Promise.all([
      fetch('data/tracker_config.json', { cache: 'no-store' }),
      fetch('data/store_profile.json', { cache: 'no-store' }),
      fetch('data/rank_history.json', { cache: 'no-store' }),
      fetch('data/keyword_sync.json', { cache: 'no-store' }),
      fetch('data/naver_place_daily.csv', { cache: 'no-store' }),
    ]);
    let config = configResponse.ok ? await configResponse.json() : {};
    const storeProfile = storeProfileResponse.ok ? await storeProfileResponse.json() : {};
    const history = historyResponse.ok ? await historyResponse.json() : {};
    rankHistory = Array.isArray(history.measurements) ? history.measurements : [];
    placeDailyRows = placeDailyResponse.ok ? parsePlaceDailyCsv(await placeDailyResponse.text()) : [];
    const sync = syncResponse.ok ? await syncResponse.json() : {};
    keywordSyncEndpoint = typeof sync.endpoint === 'string' ? sync.endpoint.replace(/\/$/, '') : '';
    void loadSyncedActivities();
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
    placeName = String(config.place?.name || placeName).trim() || placeName;
    currentStoreProfile = storeProfile;
    const seasonTimeline = annualSeasonTimeline(storeProfile);
    void renderSeasonGuide(seasonTimeline);
    void renderSeasonPlanner(seasonTimeline);
    void renderSeasonMission(seasonTimeline);
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
    renderPerformance();
    renderWeeklyReport();
    setKeywordSyncStatus(keywordSyncEndpoint
      ? '키워드 파일과 동기화됨 · 등록 또는 삭제하면 바로 순위 측정을 요청합니다.'
      : '자동동기화 서버를 연결하면 등록·삭제가 파일에 저장됩니다.');
  } catch {
    setKeywordSyncStatus('키워드 설정을 불러오지 못했어요.');
  }
}

function selectPrimaryKeyword(value) {
  if (!trackedKeywords.some((keyword) => keyword.value === value)) return;
  primaryKeyword = value;
  localStorage.setItem(PRIMARY_KEYWORD_STORAGE, value);
  renderKeywords();
  renderPerformance();
  syncKeywords(trackedKeywords.map((keyword) => keyword.value), value).then(() => {
    setKeywordSyncStatus('거점키워드를 저장했어요.');
  }).catch((error) => {
    renderKeywords();
    renderPerformance();
    setKeywordSyncStatus(`거점키워드는 이 브라우저에 저장됐어요. 서버 동기화는 잠시 후 다시 시도해 주세요. (${error.message})`);
  });
}

document.querySelector('#keyword-list').addEventListener('click', (event) => {
  const star = event.target.closest('[data-primary-keyword]');
  if (star) {
    selectPrimaryKeyword(star.dataset.primaryKeyword);
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

const logInput = document.querySelector('#log-input');
const logList = document.querySelector('#log-list');
const logCount = document.querySelector('#log-count');
const sideNavGroup = document.querySelector('.side-nav-group');
const sideNavMenu = document.querySelector('#side-nav-menu');
let selectedQuickLog = '';
if (sideNavGroup && sideNavMenu) sideNavGroup.addEventListener('click', () => {
  const expanded = sideNavGroup.getAttribute('aria-expanded') === 'true';
  sideNavGroup.setAttribute('aria-expanded', String(!expanded));
  sideNavMenu.hidden = expanded;
});
document.querySelectorAll('.log-chips button').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.log-chips button').forEach((item) => item.classList.remove('selected'));
  button.classList.add('selected'); selectedQuickLog = button.textContent; logInput.value = selectedQuickLog; logInput.focus();
}));
function readStoredValue(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || ''); } catch { return fallback; }
}

function activityLogs() {
  const saved = readStoredValue(ACTIVITY_LOG_STORAGE, []);
  return Array.isArray(saved) ? saved
    .filter((item) => typeof item?.text === 'string')
    .map((item) => ({ ...item, recordedAt: item.recordedAt || item.recorded_at || '' })) : [];
}

function renderActivityLogs() {
  const today = koreaToday();
  const todayLogs = activityLogs().filter((item) => performanceDateKey(item.recordedAt) === today);
  logList.replaceChildren(...todayLogs.map((item) => {
    const row = document.createElement('li');
    row.textContent = item.text;
    return row;
  }));
  logCount.textContent = String(todayLogs.length);
  renderPerformance();
}

function performanceDateParts(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const values = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).reduce((all, part) => ({ ...all, [part.type]: part.value }), {});
  return { date, year: Number(values.year), month: Number(values.month), day: Number(values.day), hour: Number(values.hour) };
}

function performanceDateKey(value) {
  const parts = performanceDateParts(value);
  return parts ? `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}` : '';
}

function performanceDateLabel(value) {
  const parts = performanceDateParts(value);
  return parts ? `${parts.month}월 ${parts.day}일` : '-';
}

function parsePlaceDailyCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"' && quoted && text[index + 1] === '"') { cell += char; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[index + 1] === '\n') index += 1;
      row.push(cell); cell = '';
      if (row.length > 1) rows.push(row);
      row = [];
    } else cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers = [], ...records] = rows;
  return records.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])));
}

function performanceRange() {
  const now = new Date();
  if (performancePeriod === 'previous-month') {
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const end = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999);
    return { start, end, label: '지난달' };
  }
  if (performancePeriod === 'current-month') {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now);
    end.setHours(23, 59, 59, 999);
    return { start, end, label: '이번 달' };
  }
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  start.setHours(0, 0, 0, 0);
  return { start, end, label: '최근 30일' };
}

function performanceRanks(start, end) {
  const keyword = primaryKeyword || trackedKeywords[0]?.value || '';
  const byDay = new Map();
  rankHistory
    .filter((item) => item.keyword === keyword && Number.isInteger(item.rank))
    .filter((item) => {
      const time = Date.parse(item.measured_at);
      return Number.isFinite(time) && time >= start.getTime() && time <= end.getTime();
    })
    .sort((left, right) => String(left.measured_at).localeCompare(String(right.measured_at)))
    .forEach((item) => byDay.set(performanceDateKey(item.measured_at), item));
  return { keyword, points: [...byDay.values()] };
}

function performanceActivities(start, end) {
  return activityLogs()
    .filter((item) => {
      const time = Date.parse(item.recordedAt);
      return Number.isFinite(time) && time >= start.getTime() && time <= end.getTime();
    })
    .sort((left, right) => String(right.recordedAt).localeCompare(String(left.recordedAt)));
}

function activitySource(item) {
  if (item.text.startsWith('AI 작업실 ·')) return 'AI 작업실에서';
  if (item.text.startsWith('오늘 할 일 완료')) return '했어요에서';
  return '오늘 기록에서';
}

function renderPerformanceChart(points, activities, start, end) {
  const chart = document.querySelector('#performance-rank-chart');
  const note = document.querySelector('#performance-chart-note');
  if (!chart || !note) return;
  if (!points.length) {
    chart.innerHTML = '<div class="performance-empty">선택한 기간의 측정된 순위가 없어요.</div>';
    note.textContent = '순위를 측정하면 기록한 일과 함께 변화가 표시됩니다.';
    return;
  }
  const width = 540;
  const height = 206;
  const left = 38;
  const right = 14;
  const top = 16;
  const bottom = 30;
  const ranks = points.map((point) => point.rank);
  const maxRank = Math.max(30, Math.ceil(Math.max(...ranks) / 10) * 10);
  const y = (rank) => top + ((height - top - bottom) * (rank - 1)) / Math.max(maxRank - 1, 1);
  const x = (value) => left + ((width - left - right) * (new Date(value).getTime() - start.getTime())) / Math.max(end.getTime() - start.getTime(), 1);
  const tickValues = [1, Math.max(10, Math.round(maxRank / 3 / 10) * 10), Math.max(20, Math.round(maxRank * 2 / 3 / 10) * 10), maxRank]
    .filter((value, index, all) => all.indexOf(value) === index)
    .sort((a, b) => a - b);
  const grid = tickValues.map((rank) => `<line class="grid-line" x1="${left}" y1="${y(rank)}" x2="${width - right}" y2="${y(rank)}"/><text x="0" y="${y(rank) + 4}">${rank}위</text>`).join('');
  const line = points.map((point) => `${x(point.measured_at).toFixed(1)},${y(point.rank).toFixed(1)}`).join(' ');
  const dots = points.map((point) => `<circle class="rank-dot" cx="${x(point.measured_at).toFixed(1)}" cy="${y(point.rank).toFixed(1)}" r="3"/>`).join('');
  const eventMarks = activities.slice(0, 6).map((item, index) => {
    const pointX = x(item.recordedAt).toFixed(1);
    const pointY = height - bottom - 6;
    return `<line class="event-line" x1="${pointX}" y1="${pointY - 34}" x2="${pointX}" y2="${pointY - 12}"/><circle class="event-dot" cx="${pointX}" cy="${pointY}" r="10"/><text class="event-label" x="${pointX}" y="${pointY + 3}">${index + 1}</text>`;
  }).join('');
  const middle = new Date((start.getTime() + end.getTime()) / 2);
  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${points.length}일 순위와 활동 기록"><g>${grid}</g><polyline class="rank-line" points="${line}"/>${dots}<g>${eventMarks}</g><text class="date-label" x="${left}" y="${height - 3}">${performanceDateLabel(start)}</text><text class="date-label" x="${(width / 2).toFixed(1)}" y="${height - 3}">${performanceDateLabel(middle)}</text><text class="date-label" x="${width - right}" y="${height - 3}">${performanceDateLabel(end)}</text></svg>`;
  note.textContent = `낮 ${performanceDateParts(points.at(-1).measured_at)?.hour || ''}시 측정값 · 번호는 아래 기록과 같아요`;
}

function renderPerformanceActivityList(activities) {
  const list = document.querySelector('#performance-activity-list');
  const toggle = document.querySelector('#performance-activity-toggle');
  if (!list || !toggle) return;
  const visible = showAllPerformanceActivities ? activities : activities.slice(0, 5);
  list.replaceChildren(...visible.map((item, index) => {
    const row = document.createElement('li');
    const number = document.createElement('i');
    number.className = 'performance-activity-number';
    number.textContent = String(index + 1);
    const title = document.createElement('b');
    title.textContent = item.text;
    const date = document.createElement('span');
    date.textContent = `${performanceDateLabel(item.recordedAt)} · ${activitySource(item)}`;
    row.append(number, title, date);
    return row;
  }));
  if (!activities.length) {
    const empty = document.createElement('li');
    empty.textContent = '이 기간에 기록한 일이 아직 없어요.';
    list.replaceChildren(empty);
  }
  toggle.hidden = activities.length <= 5;
  toggle.textContent = showAllPerformanceActivities ? '접기 ︿' : `이 기간 한 일 모두 보기 (${activities.length}건) ︿`;
}

function renderPerformance() {
  const page = document.querySelector('#performance');
  if (!page) return;
  const { start, end, label } = performanceRange();
  const { keyword, points } = performanceRanks(start, end);
  const activities = performanceActivities(start, end);
  const average = points.length ? points.reduce((sum, point) => sum + point.rank, 0) / points.length : null;
  const reviewRows = placeDailyRows.filter((row) => {
    const date = new Date(`${row.collected_date}T12:00:00+09:00`);
    return Number.isFinite(date.getTime()) && date >= start && date <= end;
  });
  const reviewValues = reviewRows.map((row) => Number(row.reviews_daily_delta)).filter((value) => Number.isFinite(value));
  const reviews = reviewValues.length ? reviewValues.reduce((sum, value) => sum + value, 0) : null;
  document.querySelector('#performance-range-copy').textContent = `${label} · ${performanceDateLabel(start)} ~ ${performanceDateLabel(end)}`;
  document.querySelector('#performance-average').textContent = average === null ? '-' : `${average.toFixed(1)}위`;
  document.querySelector('#performance-reviews').textContent = reviews === null ? '집계 대기' : `${reviews}건`;
  document.querySelector('#performance-review-note').textContent = reviews === null ? '해당 기간의 리뷰 수집 자료 없음' : '';
  document.querySelector('#performance-keyword-copy').textContent = keyword ? `거점키워드 「${keyword}」 순위 · 선이 위로 갈수록 좋아요 (1위가 맨 위)` : '거점키워드를 등록하면 순위를 표시해요.';
  document.querySelector('#performance-activity-period').textContent = label;
  renderPerformanceChart(points, activities, start, end);
  renderPerformanceActivityList(activities);
}

function reportDateFromYmd(value) {
  const date = new Date(`${value}T12:00:00+09:00`);
  return Number.isFinite(date.getTime()) ? date : null;
}

function reportMonthDay(value) {
  const date = value instanceof Date ? value : reportDateFromYmd(value);
  return date ? `${date.getMonth() + 1}월 ${date.getDate()}일` : '-';
}

function weeklyReports() {
  const grouped = new Map();
  for (const row of placeDailyRows) {
    const date = reportDateFromYmd(row.collected_date);
    if (!date) continue;
    const weekStart = typeof row.week_start === 'string' && row.week_start ? row.week_start : row.collected_date;
    if (!grouped.has(weekStart)) grouped.set(weekStart, []);
    grouped.get(weekStart).push(row);
  }
  const groups = [...grouped.entries()]
    .map(([weekStart, rows]) => ({ weekStart, rows: rows.sort((left, right) => String(left.collected_date).localeCompare(String(right.collected_date))) }))
    .filter(({ rows }) => new Set(rows.map((row) => row.collected_date)).size >= 7)
    .sort((left, right) => right.weekStart.localeCompare(left.weekStart));
  const usableGroups = groups.length ? groups : [...grouped.entries()]
    .map(([weekStart, rows]) => ({ weekStart, rows: rows.sort((left, right) => String(left.collected_date).localeCompare(String(right.collected_date))) }))
    .sort((left, right) => right.weekStart.localeCompare(left.weekStart));
  return usableGroups.map(({ weekStart, rows }, index, all) => {
    const start = reportDateFromYmd(weekStart);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const numberSum = (field) => rows.reduce((sum, row) => {
      const value = Number(row[field]);
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
    const reviewDeltas = rows.map((row) => Number(row.reviews_daily_delta)).filter(Number.isFinite);
    const lastWeeklyReview = [...rows].reverse().map((row) => Number(row.reviews_weekly)).find(Number.isFinite);
    const reviews = reviewDeltas.length ? numberSum('reviews_daily_delta') : (lastWeeklyReview ?? null);
    const reservations = numberSum('reservation_applications_daily_delta');
    const completions = numberSum('reservation_completions_daily_delta');
    const priorReviews = all.slice(index + 1, index + 3)
      .map(({ rows: priorRows }) => {
        const values = priorRows.map((row) => Number(row.reviews_daily_delta)).filter(Number.isFinite);
        return values.length ? priorRows.reduce((sum, row) => sum + (Number(row.reviews_daily_delta) || 0), 0) : null;
      }).filter(Number.isFinite);
    const averageReviews = priorReviews.length ? priorReviews.reduce((sum, value) => sum + value, 0) / priorReviews.length : null;
    return { weekStart, start, end, issuedAt: new Date(end.getFullYear(), end.getMonth(), end.getDate() + 1), reviews, reservations, completions, averageReviews };
  });
}

function weeklyReportLabel(report) {
  return `${reportMonthDay(report.start)}~${reportMonthDay(report.end)}`;
}

function nextWeeklyReleaseDate() {
  const date = reportDateFromYmd(koreaToday());
  if (!date) return new Date();
  const daysUntilMonday = (8 - date.getDay()) % 7;
  date.setDate(date.getDate() + daysUntilMonday);
  date.setHours(0, 0, 0, 0);
  return date;
}

function weeklyReleaseLabel(date) {
  const weekdays = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
  return `${reportMonthDay(date)} ${weekdays[date.getDay()]} 발행`;
}

function renderWeeklyHistory(reports, selectedReport = null) {
  const history = document.querySelector('#weekly-history-list');
  if (!history) return;
  if (!reports.length) {
    history.textContent = '주간 데이터를 모으면 리포트가 자동으로 쌓입니다.';
    return;
  }
  history.replaceChildren(...reports.slice(0, 8).map((item, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.weekStart = item.weekStart;
    button.className = item.weekStart === selectedReport?.weekStart ? 'selected' : '';
    const title = document.createElement('b');
    title.textContent = `${reportMonthDay(item.issuedAt)} 발행`;
    const range = document.createElement('span');
    range.textContent = weeklyReportLabel(item);
    const action = document.createElement('em');
    action.textContent = item.weekStart === selectedReport?.weekStart ? '지금 보는 리포트' : '보기 ›';
    button.append(title, range, action);
    return button;
  }));
}

function renderWeeklyReport() {
  const reports = weeklyReports();
  const releaseCard = document.querySelector('#weekly-release-card');
  const detail = document.querySelector('#weekly-report-detail');
  const previousLink = document.querySelector('#weekly-previous-link');
  if (!releaseCard || !detail || !previousLink) return;
  document.querySelector('#weekly-release-date').textContent = weeklyReleaseLabel(nextWeeklyReleaseDate());
  const listView = !selectedWeeklyReport;
  releaseCard.hidden = !listView;
  detail.hidden = false;
  previousLink.hidden = listView;
  if (!reports.length) {
    document.querySelector('#weekly-headline').textContent = '주간 데이터를 수집하고 있어요';
    document.querySelector('#weekly-range').textContent = '수집 후 주간 리포트가 발행됩니다';
    renderWeeklyHistory(reports);
    return;
  }
  const report = listView ? reports[0] : (reports.find((item) => item.weekStart === selectedWeeklyReport) || reports[0]);
  if (!listView) selectedWeeklyReport = report.weekStart;
  const reviewCount = Number.isFinite(report.reviews) ? report.reviews : 0;
  const average = report.averageReviews;
  const barMax = Math.max(reviewCount, average || 0, 1);
  const change = average === null ? null : reviewCount - average;
  document.querySelector('#weekly-place-name').textContent = placeName;
  document.querySelector('#weekly-range').textContent = weeklyReportLabel(report);
  document.querySelector('#weekly-headline').textContent = reviewCount
    ? `지난주 방문자 리뷰가 ${reviewCount}개 늘었어요`
    : '지난주 새 리뷰 데이터를 확인해 주세요';
  document.querySelector('#weekly-review-change').textContent = reviewCount ? `+${reviewCount}개` : '-';
  document.querySelector('#weekly-review-detail').textContent = '실제 일별 수집 데이터 기준';
  document.querySelector('#weekly-current-count').textContent = `${reviewCount}개`;
  document.querySelector('#weekly-average-count').textContent = average === null ? '비교 대기' : `${average.toFixed(average % 1 ? 1 : 0)}개`;
  document.querySelector('#weekly-current-bar').style.width = `${Math.max((reviewCount / barMax) * 100, reviewCount ? 4 : 0)}%`;
  document.querySelector('#weekly-average-bar').style.width = average === null ? '0%' : `${Math.max((average / barMax) * 100, 4)}%`;
  document.querySelector('#weekly-comparison-copy').textContent = change === null
    ? '비교할 지난 주 데이터가 쌓이면 변화도 함께 보여드려요.'
    : (change > 0 ? `지난 2주 평균보다 ${change.toFixed(change % 1 ? 1 : 0)}개 더 늘었어요.` : change < 0 ? `지난 2주 평균보다 ${Math.abs(change).toFixed(Math.abs(change) % 1 ? 1 : 0)}개 적어요.` : '지난 2주 평균과 비슷해요.');
  document.querySelector('#weekly-task-title').textContent = reviewCount
    ? `지난주 새로 쌓인 리뷰가 ${reviewCount}개예요. 리뷰를 확인하고 답글을 남겨주세요.`
    : '이번 주 방문자 리뷰를 확인하고 답글을 남겨주세요.';
  document.querySelector('#weekly-task-previous').textContent = `${reviewCount}개`;
  document.querySelector('#weekly-task-average').textContent = average === null ? '비교 대기' : `${average.toFixed(average % 1 ? 1 : 0)}개`;
  document.querySelector('#weekly-task-note').textContent = '리뷰 답글 데이터는 연결 후 답글 관리율도 함께 표시됩니다.';
  document.querySelector('#weekly-task-evidence').textContent = `${weeklyReportLabel(report)}에 수집된 방문자 리뷰 증감과 예약 데이터를 기준으로 안내합니다.`;
  document.querySelector('#weekly-detail-reviews').textContent = `${reviewCount}건`;
  document.querySelector('#weekly-detail-reservations').textContent = `${report.reservations} / ${report.completions}`;
  document.querySelector('#weekly-previous-title').textContent = `지난 리포트 · ${reportMonthDay(report.issuedAt)} 발행`;
  renderWeeklyHistory(reports.slice(1), listView ? null : report);
}

function addLog(value = '', kind = 'note') {
  const text = typeof value === 'string' ? value || logInput.value.trim() || selectedQuickLog : logInput.value.trim() || selectedQuickLog;
  if (!text) { logInput.focus(); return false; }
  const logs = activityLogs();
  logs.unshift({ text, recordedAt: new Date().toISOString() });
  localStorage.setItem(ACTIVITY_LOG_STORAGE, JSON.stringify(logs.slice(0, 100)));
  renderActivityLogs();
  void syncActivity(kind, text).catch((error) => {
    console.warn(error.message);
    document.querySelector('.community-note').textContent = '기록은 이 브라우저에 저장됐어요. 서버 동기화를 다시 시도해 주세요.';
  });
  logInput.value = ''; selectedQuickLog = '';
  document.querySelectorAll('.log-chips button').forEach((item) => item.classList.remove('selected'));
  return true;
}
document.querySelector('#log-submit').addEventListener('click', () => addLog());
logInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') addLog(); });

function koreaYmdParts() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  return Object.fromEntries(parts.filter(({ type }) => type !== 'literal').map(({ type, value }) => [type, value]));
}

function koreaToday() {
  const { year, month, day } = koreaYmdParts();
  return `${year}-${month}-${day}`;
}

function ymdToUtcDay(ymd) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(ymd || ''));
  if (!match) return null;
  const [, year, month, day] = match;
  const value = Date.UTC(Number(year), Number(month) - 1, Number(day));
  return Number.isFinite(value) ? Math.floor(value / 86400000) : null;
}

// 매년 반복되는 매장 시즌표를 올해·내년의 실제 날짜로 펼친다.
// 따라서 연도별 시즌명을 다시 설정하지 않아도 가장 가까운 시즌 준비 미션이 선택된다.
function annualSeasonTimeline(storeProfile) {
  const profile = storeProfile && typeof storeProfile === 'object' ? storeProfile : {};
  const year = Number(koreaYmdParts().year);
  const seasonCalendar = Array.isArray(profile.season_calendar) ? profile.season_calendar : [];
  const seasons = seasonCalendar.flatMap((season) => {
    const month = Number(season.start_month);
    const day = Number(season.start_day);
    if (!Number.isInteger(month) || !Number.isInteger(day) || month < 1 || month > 12 || day < 1 || day > 31) return [];
    return [year - 1, year, year + 1].map((seasonYear) => ({
      ...season,
      start_date: `${seasonYear}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
      end_date: `${seasonYear + (Number(season.end_month) < month ? 1 : 0)}-${String(Number(season.end_month)).padStart(2, '0')}-${String(Number(season.end_day)).padStart(2, '0')}`,
    }));
  });
  return {
    industry_label: String(profile.industry_label || '').trim(),
    praise: true,
    seasons,
  };
}

function loadSeasonStageModule() {
  if (!seasonStageModulePromise) seasonStageModulePromise = import(SEASON_STAGE_MODULE_URL);
  return seasonStageModulePromise;
}

function seasonProgressState() {
  const saved = readStoredValue(SEASON_PROGRESS_STORAGE, {});
  return saved && typeof saved === 'object' ? saved : {};
}

function seasonProgressKey(season) {
  return `${season?.key || season?.name || 'season'}:${season?.start_date || ''}`;
}

function toggleSeasonStage(season, stage) {
  const all = seasonProgressState();
  const key = seasonProgressKey(season);
  const checked = new Set(Array.isArray(all[key]) ? all[key] : []);
  if (checked.has(stage.key)) checked.delete(stage.key); else checked.add(stage.key);
  all[key] = [...checked];
  localStorage.setItem(SEASON_PROGRESS_STORAGE, JSON.stringify(all));
  void renderSeasonGuide(annualSeasonTimeline(currentStoreProfile));
  void renderSeasonPlanner(annualSeasonTimeline(currentStoreProfile));
}

let currentStoreProfile = {};

async function renderSeasonGuide(seasonTimeline) {
  const seasons = Array.isArray(seasonTimeline?.seasons) ? seasonTimeline.seasons : [];
  const todayDay = ymdToUtcDay(koreaToday());
  const dated = seasons.map((season) => ({
    season,
    startDay: ymdToUtcDay(season.start_date),
    endDay: ymdToUtcDay(season.end_date),
  })).filter(({ startDay }) => startDay !== null);
  const active = dated.find(({ startDay, endDay }) => todayDay !== null && startDay <= todayDay && (endDay === null || todayDay <= endDay));
  const next = dated.filter(({ startDay }) => todayDay === null || startDay >= todayDay).sort((a, b) => a.startDay - b.startDay)[0];
  const highlighted = active || next;
  const title = document.querySelector('#season-guide-title');
  const list = document.querySelector('#season-calendar-list');
  const stageList = document.querySelector('#season-stage-list');
  if (!title || !list || !stageList) return;
  title.textContent = highlighted
    ? `${active ? '진행 중' : '다가오는'} ${highlighted.season.name} · ${Number(highlighted.season.start_month)}월 ${Number(highlighted.season.start_day)}일`
    : '연간 제철 일정을 확인해 주세요';
  const calendar = seasons
    .filter((season) => String(season.start_date || '').startsWith(`${koreaYmdParts().year}-`))
    .sort((left, right) => String(left.start_date).localeCompare(String(right.start_date)));
  list.replaceChildren(...calendar.map((season) => {
    const row = document.createElement('li');
    row.classList.toggle('current', highlighted?.season.start_date === season.start_date);
    const name = document.createElement('b');
    name.textContent = season.name;
    const date = document.createElement('span');
    date.textContent = `${Number(season.start_month)}월 ${Number(season.start_day)}일 시작`;
    row.append(name, date);
    return row;
  }));
  if (!highlighted) return;

  try {
    const { buildDashboardSeasonStageTimeline } = await loadSeasonStageModule();
    const daysUntil = highlighted.startDay - todayDay;
    const preparationWindow = daysUntil >= 0 && daysUntil <= Number(highlighted.season.d_minus);
    const guideTimeline = buildDashboardSeasonStageTimeline({
      season: {
        ...highlighted.season,
        dMinus: Number(highlighted.season.d_minus),
        industries: [String(seasonTimeline.industry_label || '')],
      },
      daysUntil: preparationWindow ? daysUntil : Number(highlighted.season.d_minus),
      seasonDay: highlighted.startDay,
      industryLabel: seasonTimeline.industry_label,
    });
    const stages = guideTimeline?.stages || [];
    const progressKey = seasonProgressKey(highlighted.season);
    const completed = new Set(seasonProgressState()[progressKey] || []);
    const progress = document.querySelector('#season-progress');
    const count = document.querySelector('#season-count');
    const progressBar = document.querySelector('.season-progress-track');
    const completeCount = stages.filter((stage) => completed.has(stage.key)).length;
    if (progress) progress.style.width = `${stages.length ? Math.round((completeCount / stages.length) * 100) : 0}%`;
    if (count) count.textContent = `완료 ${completeCount} / ${stages.length}`;
    if (progressBar) progressBar.setAttribute('aria-valuenow', String(completeCount));
    stageList.replaceChildren(...stages.map((stage) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      const done = completed.has(stage.key);
      const isCurrent = preparationWindow && stage.isCurrent;
      button.type = 'button';
      button.className = `season-stage-item${done ? ' done' : ''}${isCurrent ? ' current' : ''}`;
      button.setAttribute('aria-pressed', String(done));
      const when = document.createElement('time');
      when.textContent = stage.dateLabel || (stage.dDay ? `${stage.dDay}일 전` : '시작일');
      const copy = document.createElement('span');
      copy.textContent = stage.name;
      const status = document.createElement('em');
      status.textContent = done ? '완료' : (isCurrent ? '이번 단계' : (stage.date && stage.date < koreaToday() ? '지남' : '예정'));
      copy.append(status);
      button.append(when, copy);
      button.addEventListener('click', () => toggleSeasonStage(highlighted.season, stage));
      item.append(button);
      return item;
    }));
  } catch (error) {
    console.warn(error);
    stageList.replaceChildren();
  }
}

function seasonPlannerDate(value) {
  const date = new Date(`${value}T12:00:00+09:00`);
  return Number.isFinite(date.getTime()) ? date : null;
}

function seasonPlannerDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function seasonPlannerMonthLabel(monthKey) {
  const [year, month] = monthKey.split('-').map(Number);
  return `${year}년 ${month}월`;
}

function seasonPlannerStageDate(season, stage) {
  const start = seasonPlannerDate(season.start_date);
  if (!start) return null;
  start.setDate(start.getDate() - Number(stage.dDay || 0));
  return start;
}

async function buildSeasonPlannerStages(seasonTimeline, season) {
  const startDay = ymdToUtcDay(season.start_date);
  const todayDay = ymdToUtcDay(koreaToday());
  if (startDay === null || todayDay === null) return [];
  const { buildDashboardSeasonStageTimeline } = await loadSeasonStageModule();
  const timeline = buildDashboardSeasonStageTimeline({
    season: { ...season, dMinus: Number(season.d_minus), industries: [seasonTimeline.industry_label] },
    daysUntil: startDay - todayDay,
    seasonDay: startDay,
    industryLabel: seasonTimeline.industry_label,
  });
  return (timeline?.stages || []).map((stage) => ({ ...stage, plannerDate: seasonPlannerStageDate(season, stage) }));
}

function seasonPlannerFocus(seasonTimeline) {
  const todayDay = ymdToUtcDay(koreaToday());
  const seasons = Array.isArray(seasonTimeline?.seasons) ? seasonTimeline.seasons : [];
  const dated = seasons.map((season) => ({ season, startDay: ymdToUtcDay(season.start_date), endDay: ymdToUtcDay(season.end_date) }))
    .filter((item) => item.startDay !== null);
  const configured = dated.find((item) => `${item.season.key}:${item.season.start_date}` === seasonPlannerFocusKey);
  if (configured) return configured.season;
  const active = dated.find((item) => item.startDay <= todayDay && (item.endDay === null || item.endDay >= todayDay));
  const next = dated.filter((item) => item.startDay >= todayDay).sort((left, right) => left.startDay - right.startDay)[0];
  return (active || next || dated[0])?.season || null;
}

async function renderSeasonPlanner(seasonTimeline) {
  const page = document.querySelector('#season');
  if (!page) return;
  const year = Number(koreaYmdParts().year);
  const currentMonth = Number(koreaYmdParts().month);
  if (!seasonPlannerMonth) seasonPlannerMonth = `${year}-${String(currentMonth).padStart(2, '0')}`;
  const monthSelect = document.querySelector('#season-month');
  monthSelect.replaceChildren(...Array.from({ length: 12 }, (_, index) => {
    const option = document.createElement('option');
    option.value = `${year}-${String(index + 1).padStart(2, '0')}`;
    option.textContent = `${year}년 ${index + 1}월`;
    return option;
  }));
  monthSelect.value = seasonPlannerMonth;
  const seasons = (Array.isArray(seasonTimeline?.seasons) ? seasonTimeline.seasons : [])
    .filter((season) => String(season.start_date).startsWith(`${year}-`));
  const stageSets = await Promise.all(seasons.map(async (season) => ({ season, stages: await buildSeasonPlannerStages(seasonTimeline, season) })));
  const monthStages = stageSets.flatMap(({ season, stages }) => stages.map((stage) => ({ season, stage })))
    .filter(({ stage }) => stage.plannerDate && seasonPlannerDateKey(stage.plannerDate).startsWith(seasonPlannerMonth));
  const completed = stageSets.reduce((count, { season, stages }) => count + stages.filter((stage) => new Set(seasonProgressState()[seasonProgressKey(season)] || []).has(stage.key)).length, 0);
  const todayKey = koreaToday();
  document.querySelector('#season-planner-subtitle').textContent = `${seasonTimeline.industry_label || '내 가게'} · ${seasonPlannerMonthLabel(seasonPlannerMonth)}`;
  document.querySelector('#season-opportunity-count').textContent = `${monthStages.length}개`;
  document.querySelector('#season-complete-count').textContent = `${completed}개`;
  document.querySelector('#season-now-count').textContent = `${monthStages.filter(({ stage }) => seasonPlannerDateKey(stage.plannerDate) === todayKey).length}개`;
  document.querySelector('#season-calendar-title').textContent = seasonPlannerMonthLabel(seasonPlannerMonth);
  const [monthYear, monthNumber] = seasonPlannerMonth.split('-').map(Number);
  const first = new Date(monthYear, monthNumber - 1, 1);
  const offset = (first.getDay() + 6) % 7;
  const days = new Date(monthYear, monthNumber, 0).getDate();
  if (!seasonPlannerSelectedDate.startsWith(seasonPlannerMonth)) {
    const todayInSelectedMonth = koreaToday().startsWith(seasonPlannerMonth);
    seasonPlannerSelectedDate = todayInSelectedMonth ? koreaToday() : `${seasonPlannerMonth}-01`;
  }
  const grid = document.querySelector('#season-month-grid');
  grid.replaceChildren(...Array.from({ length: offset + days }, (_, index) => {
    const cell = document.createElement(index < offset ? 'i' : 'button');
    if (index < offset) return cell;
    const day = index - offset + 1;
    const date = new Date(monthYear, monthNumber - 1, day);
    const key = seasonPlannerDateKey(date);
    const events = monthStages.filter(({ stage }) => seasonPlannerDateKey(stage.plannerDate) === key);
    cell.type = 'button';
    cell.className = `season-day${key === todayKey ? ' today' : ''}${key === seasonPlannerSelectedDate ? ' selected' : ''}${events.length ? ' has-event' : ''}`;
    const number = document.createElement('b');
    number.textContent = String(day);
    cell.append(number);
    events.slice(0, 2).forEach(({ stage }) => {
      const label = document.createElement('span');
      label.textContent = stage.name;
      cell.append(label);
    });
    cell.addEventListener('click', () => { seasonPlannerSelectedDate = key; void renderSeasonPlanner(seasonTimeline); });
    return cell;
  }));
  const focus = seasonPlannerFocus(seasonTimeline);
  const selectedEvents = monthStages.filter(({ stage }) => seasonPlannerDateKey(stage.plannerDate) === seasonPlannerSelectedDate);
  const selectedDate = seasonPlannerDate(seasonPlannerSelectedDate);
  document.querySelector('#season-focus-badge').textContent = selectedDate ? `${reportMonthDay(selectedDate)} 할 일` : '준비 일정';
  document.querySelector('#season-focus-title').textContent = selectedEvents.length ? `${reportMonthDay(selectedDate)}에 준비할 일` : `${reportMonthDay(selectedDate)}에는 예정된 시즌 준비가 없어요`;
  document.querySelector('#season-focus-copy').textContent = selectedEvents.length
    ? '날짜를 바꾸면 그 날짜의 시즌 준비 단계만 보여드려요.'
    : '달력에서 파란 일정이 있는 날짜를 선택해 보세요.';
  const focusList = document.querySelector('#season-focus-stages');
  focusList.replaceChildren(...selectedEvents.map(({ season, stage }, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    const done = new Set(seasonProgressState()[seasonProgressKey(season)] || []).has(stage.key);
    button.type = 'button'; button.className = done ? 'done' : '';
    const title = document.createElement('b'); title.textContent = `${index + 1}. ${season.name} · ${stage.name}`;
    const date = document.createElement('span'); date.textContent = `${reportMonthDay(stage.plannerDate)} · ${done ? '완료' : '눌러서 완료'}`;
    button.append(title, date); button.addEventListener('click', () => toggleSeasonStage(season, stage));
    item.append(button); return item;
  }));
  const other = document.querySelector('#season-other-list');
  other.replaceChildren(...seasons.filter((season) => season.start_date !== focus?.start_date).map((season) => {
    const button = document.createElement('button'); button.type = 'button';
    const title = document.createElement('b'); title.textContent = season.name;
    const copy = document.createElement('span'); copy.textContent = `${Number(season.start_month)}월 ${Number(season.start_day)}일 시작`;
    button.append(title, copy); button.addEventListener('click', () => { seasonPlannerFocusKey = `${season.key}:${season.start_date}`; void renderSeasonPlanner(seasonTimeline); });
    return button;
  }));
  document.querySelector('#season-setting-industry').textContent = seasonTimeline.industry_label || '-';
  document.querySelector('#season-setting-seasons').textContent = seasons.map((season) => `${season.name} ${Number(season.start_month)}월 ${Number(season.start_day)}일`).join(' · ') || '-';
  const placeRows = placeDailyRows.filter((row) => String(row.collected_date).startsWith(seasonPlannerMonth));
  const sum = (field) => placeRows.reduce((total, row) => total + (Number(row[field]) || 0), 0);
  document.querySelector('#season-place-data').textContent = placeRows.length ? `방문 ${sum('place_visits_daily_delta').toLocaleString('ko-KR')} · 새 리뷰 ${sum('reviews_daily_delta')} · 예약 신청 ${sum('reservation_applications_daily_delta')}` : '선택한 달의 내 플레이스 수집 자료가 아직 없어요.';
}

function seasonCandidate(seasonTimeline) {
  const timeline = seasonTimeline && typeof seasonTimeline === 'object' ? seasonTimeline : {};
  const todayDay = ymdToUtcDay(koreaToday());
  if (todayDay === null) return null;
  const candidates = (Array.isArray(timeline.seasons) ? timeline.seasons : [])
    .map((season) => {
      const startDay = ymdToUtcDay(season.start_date || season.startDate);
      const dMinus = Number(season.d_minus ?? season.dMinus);
      const daysUntil = startDay === null ? NaN : startDay - todayDay;
      return { season, startDay, dMinus, daysUntil };
    })
    .filter(({ dMinus, daysUntil }) => Number.isFinite(dMinus) && daysUntil >= 0 && daysUntil <= dMinus)
    .sort((a, b) => a.daysUntil - b.daysUntil);
  return candidates[0] || null;
}

function setMissionUnavailable(message) {
  activeMission = null;
  document.querySelector('#mission-title').textContent = '오늘 할 일을 준비하고 있어요';
  document.querySelector('#mission-summary').textContent = message;
  document.querySelector('#mission-evidence').replaceChildren();
  document.querySelector('#mission-evidence-details').hidden = true;
  renderMissionState();
}

// 참조 대시보드의 renderQuestCard와 같은 오늘의 안내 문구 선택 규칙.
function missionBubbleSub(isPraise) {
  return isPraise ? '오늘은 기록 하나만 남겨도 충분해요' : '5분이면 다음 측정과 비교할 기록이 생겨요';
}

async function renderSeasonMission(seasonTimeline) {
  const candidate = seasonCandidate(seasonTimeline);
  if (!candidate) {
    setMissionUnavailable('다가오는 시즌을 설정하면 오늘 할 일을 안내합니다.');
    return;
  }
  try {
    const { buildDashboardSeasonStageTimeline } = await loadSeasonStageModule();
    const industryLabel = String(seasonTimeline.industry_label || seasonTimeline.industryLabel || '').trim();
    const season = {
      ...candidate.season,
      dMinus: candidate.dMinus,
      industries: candidate.season.industries || (industryLabel ? [industryLabel] : []),
    };
    const timeline = buildDashboardSeasonStageTimeline({
      season,
      daysUntil: candidate.daysUntil,
      seasonDay: candidate.startDay,
      industryLabel,
    });
    const mission = timeline?.current;
    if (!mission) throw new Error('현재 시즌 단계를 계산하지 못했습니다.');

    activeMission = {
      id: `${season.name}:${mission.key}:${candidate.startDay}`,
      name: mission.name,
      summary: mission.summary,
      aiTool: AI_TOOL_HINTS[mission.aiTool] ? mission.aiTool : '',
      prompt: [mission.summary, ...(mission.bodyLines || [])].filter(Boolean).join('\n'),
    };
    document.querySelector('#mission-title').textContent = mission.summary;
    document.querySelector('#mission-summary').textContent = missionBubbleSub(Boolean(seasonTimeline.praise));
    const evidence = document.querySelector('#mission-evidence');
    evidence.replaceChildren(...mission.bodyLines.map((line) => {
      const paragraph = document.createElement('p');
      paragraph.textContent = line;
      return paragraph;
    }));
    document.querySelector('#mission-evidence-details').hidden = false;
    document.querySelector('#ai-work-open').textContent = activeMission.aiTool ? `AI로 ${activeMission.aiTool} 만들기` : 'AI 작업실 열기';
    renderMissionState();
  } catch (error) {
    console.warn(error);
    setMissionUnavailable('오늘 할 일을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.');
  }
}

function missionState() {
  const saved = readStoredValue(MISSION_STATE_STORAGE, {});
  return saved && typeof saved === 'object' ? saved : {};
}

function renderMissionState() {
  const state = missionState()[koreaToday()] || {};
  const missionDone = document.querySelector('#mission-done');
  const completed = Boolean(activeMission && state.completedMissionId === activeMission.id);
  missionDone.classList.toggle('done', completed);
  missionDone.textContent = completed ? '기록했어요 ✓' : '했어요, 기록해 주세요';
  missionDone.disabled = !activeMission || completed;
  document.querySelectorAll('[data-feedback]').forEach((button) => {
    button.classList.toggle('selected', button.dataset.feedback === state.feedback);
  });
}

document.querySelector('#mission-done').addEventListener('click', () => {
  if (!activeMission) return;
  const allStates = missionState();
  const today = koreaToday();
  allStates[today] = {
    ...allStates[today], completedMissionId: activeMission.id, completedAt: new Date().toISOString(),
  };
  localStorage.setItem(MISSION_STATE_STORAGE, JSON.stringify(allStates));
  const activity = `오늘 할 일 완료 · ${activeMission.name}`;
  addLog(activity, 'mission_complete');
  renderMissionState();
});

document.querySelectorAll('[data-feedback]').forEach((button) => button.addEventListener('click', () => {
  const allStates = missionState();
  const today = koreaToday();
  allStates[today] = { ...allStates[today], feedback: button.dataset.feedback };
  localStorage.setItem(MISSION_STATE_STORAGE, JSON.stringify(allStates));
  const message = button.dataset.feedback === 'good' ? '오늘 할 일 평가 · 도움됐어요' : '오늘 할 일 평가 · 도움안돼요';
  void syncActivity('feedback', message).catch((error) => console.warn(error.message));
  renderMissionState();
}));

const aiWorkDialog = document.querySelector('#ai-work-dialog');
const aiWorkInput = document.querySelector('#ai-work-input');
const aiWorkDraft = document.querySelector('#ai-work-draft');
const aiWorkStatus = document.querySelector('#ai-work-status');
const aiWorkCopy = document.querySelector('#ai-work-copy');
const aiWorkTitle = document.querySelector('#ai-work-title');
const aiWorkDescription = document.querySelector('#ai-work-copy-description');
const aiWorkLabel = document.querySelector('#ai-work-label');
const aiWorkGenerate = document.querySelector('#ai-work-generate');

const AI_TOOL_HINTS = {
  메뉴네이밍: { description: '시즌 대표 메뉴의 이름과 소개 문구를 만듭니다.', label: '메뉴·손님 상황', placeholder: '예: 겨울 굴과 조개전골, 가족모임 손님' },
  상세설명: { description: '네이버 플레이스에 넣을 매장·메뉴 설명 초안을 만듭니다.', label: '강조할 메뉴·장점', placeholder: '예: 조개전골, 넓은 좌석, 가족모임' },
  리뷰답글: { description: '리뷰에 맞는 정중한 답글 초안을 만듭니다.', label: '리뷰 내용 또는 상황', placeholder: '예: 조개가 신선하고 가족과 편하게 먹었다는 리뷰' },
  광고문구: { description: '시즌 메뉴를 알리는 짧은 광고 문구를 만듭니다.', label: '홍보할 내용', placeholder: '예: 굴철 한정 조개전골, 주말 가족모임' },
  마케팅메시지: { description: '단골 손님에게 보낼 마케팅 메시지 초안을 만듭니다.', label: '알릴 내용', placeholder: '예: 쭈꾸미철 시작, 재방문 쿠폰 안내' },
  체험단의뢰: { description: '체험단 모집·의뢰에 쓸 안내 초안을 만듭니다.', label: '모집 조건과 메뉴', placeholder: '예: 대하철 체험단, 2인 메뉴 제공, 평일 방문' },
  소식문구: { description: '네이버 플레이스 소식에 올릴 문구 초안을 만듭니다.', label: '소식 내용', placeholder: '예: 굴철 시작, 시즌 대표 메뉴 안내' },
};

function currentAiTool() {
  return activeMission?.aiTool && AI_TOOL_HINTS[activeMission.aiTool] ? activeMission.aiTool : '상세설명';
}

function setAiWorkCopy(tool) {
  const copy = AI_TOOL_HINTS[tool];
  aiWorkTitle.textContent = `AI로 ${tool} 만들기`;
  aiWorkDescription.textContent = copy.description;
  aiWorkLabel.textContent = copy.label;
  aiWorkInput.placeholder = copy.placeholder;
  aiWorkDraft.setAttribute('aria-label', `${tool} AI 초안`);
}

function saveDescriptionDraft() {
  localStorage.setItem(DESCRIPTION_DRAFT_STORAGE, JSON.stringify({
    tool: currentAiTool(), focus: aiWorkInput.value.trim(), draft: aiWorkDraft.value, createdAt: new Date().toISOString(),
  }));
}

function restoreAiDraftForTool(tool) {
  const draft = readStoredValue(DESCRIPTION_DRAFT_STORAGE, {});
  const matchesTool = draft?.tool === tool;
  aiWorkInput.value = matchesTool && typeof draft.focus === 'string' ? draft.focus : '';
  aiWorkDraft.value = matchesTool && typeof draft.draft === 'string' ? draft.draft : '';
  aiWorkCopy.disabled = !aiWorkDraft.value;
  aiWorkStatus.textContent = '';
}

document.querySelector('#ai-work-open').addEventListener('click', () => {
  const tool = currentAiTool();
  setAiWorkCopy(tool);
  restoreAiDraftForTool(tool);
  if (activeMission?.prompt) {
    aiWorkDescription.textContent = activeMission.prompt;
  }
  aiWorkDialog.showModal();
  aiWorkInput.focus();
});

aiWorkGenerate.addEventListener('click', async () => {
  const request = aiWorkInput.value.trim() || activeMission?.summary || '';
  if (!request) {
    aiWorkStatus.textContent = '만들고 싶은 내용을 먼저 적어 주세요.';
    aiWorkInput.focus();
    return;
  }
  if (!keywordSyncEndpoint) {
    aiWorkStatus.textContent = 'AI 생성 서버가 아직 연결되지 않았습니다.';
    return;
  }
  const tool = currentAiTool();
  aiWorkGenerate.disabled = true;
  aiWorkCopy.disabled = true;
  aiWorkDraft.value = '';
  aiWorkStatus.textContent = 'AI가 초안을 만들고 있어요…';
  try {
    const response = await fetch(`${keywordSyncEndpoint}/ai/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-tracker-key': trackerAdminKey() },
      body: JSON.stringify({ tool, request, mission: activeMission?.prompt || activeMission?.name || '' }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.output) {
      if (response.status === 401) sessionStorage.removeItem(KEYWORD_SYNC_KEY_STORAGE);
      throw new Error(payload.error || 'AI 초안을 만들지 못했습니다.');
    }
    aiWorkDraft.value = payload.output;
    aiWorkCopy.disabled = false;
    aiWorkStatus.textContent = `${tool} 초안을 만들었어요. 확인한 뒤 복사해 사용해 보세요.`;
    saveDescriptionDraft();
    const activity = `AI 작업실 · ${tool} 초안 만들기`;
    addLog(activity, 'note');
  } catch (error) {
    aiWorkStatus.textContent = error.message || 'AI 초안을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.';
  } finally {
    aiWorkGenerate.disabled = false;
  }
});

aiWorkCopy.addEventListener('click', async () => {
  if (!aiWorkDraft.value) return;
  try {
    await navigator.clipboard.writeText(aiWorkDraft.value);
  } catch {
    aiWorkDraft.select();
    document.execCommand('copy');
  }
  aiWorkStatus.textContent = '초안을 복사했어요.';
});

setAiWorkCopy(currentAiTool());
restoreAiDraftForTool(currentAiTool());

document.querySelector('#performance-period').addEventListener('change', (event) => {
  performancePeriod = event.target.value;
  showAllPerformanceActivities = false;
  renderPerformance();
});

document.querySelector('#performance-activity-toggle').addEventListener('click', () => {
  showAllPerformanceActivities = !showAllPerformanceActivities;
  renderPerformance();
});

document.querySelector('#weekly-previous-link').addEventListener('click', (event) => {
  selectedWeeklyReport = '';
  renderWeeklyReport();
});

document.querySelector('#weekly-history-list').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-week-start]');
  if (!button) return;
  selectedWeeklyReport = button.dataset.weekStart;
  renderWeeklyReport();
});

document.querySelector('#season-month').addEventListener('change', (event) => {
  seasonPlannerMonth = event.target.value;
  void renderSeasonPlanner(annualSeasonTimeline(currentStoreProfile));
});

function renderPageRoute() {
  const performanceView = window.location.hash === '#performance';
  const weeklyReportView = window.location.hash === '#weekly';
  const seasonPlannerView = window.location.hash === '#season';
  document.body.classList.toggle('performance-view', performanceView);
  document.body.classList.toggle('weekly-report-view', weeklyReportView);
  document.body.classList.toggle('season-planner-view', seasonPlannerView);
  if (performanceView) {
    renderPerformance();
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  }
  if (weeklyReportView) {
    renderWeeklyReport();
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  }
  if (seasonPlannerView) {
    void renderSeasonPlanner(annualSeasonTimeline(currentStoreProfile));
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  }
}

window.addEventListener('hashchange', renderPageRoute);
renderActivityLogs();
renderMissionState();

renderKeywords();
loadServerTracker();
renderPageRoute();
