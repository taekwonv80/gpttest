const DATA = {
  7: {
    label: "2026.07.25 — 07.31",
    previousLabel: "직전 7일 대비",
    totals: { spend: 1985300, impressions: 491370, clicks: 13751, ctr: 2.8, cpc: 144 },
    changes: { spend: 8.4, impressions: 12.1, clicks: 15.7, ctr: 0.09, cpc: -6.3 },
    campaigns: [
      { name: "플레이스 검색광고", spend: 642800, impressions: 158420, clicks: 5374, ctr: 3.39, cpc: 120, color: "#03c75a" },
      { name: "지역소상공인 광고", spend: 318000, impressions: 94850, clicks: 1897, ctr: 2.0, cpc: 168, color: "#7c5cff" },
      { name: "파워링크", spend: 1024500, impressions: 238100, clicks: 6480, ctr: 2.72, cpc: 158, color: "#ff8f4d" }
    ],
    trend: [
      { day: "07.25", clicks: 1660, spend: 242000, ctr: 2.51 },
      { day: "07.26", clicks: 1820, spend: 262400, ctr: 2.63 },
      { day: "07.27", clicks: 1745, spend: 259100, ctr: 2.58 },
      { day: "07.28", clicks: 2010, spend: 288500, ctr: 2.81 },
      { day: "07.29", clicks: 1946, spend: 291300, ctr: 2.76 },
      { day: "07.30", clicks: 2210, spend: 319200, ctr: 3.02 },
      { day: "07.31", clicks: 2360, spend: 322800, ctr: 3.18 }
    ]
  },
  30: {
    label: "2026.07.02 — 07.31",
    previousLabel: "직전 30일 대비",
    totals: { spend: 7938200, impressions: 2014760, clicks: 55214, ctr: 2.74, cpc: 144 },
    changes: { spend: 6.1, impressions: 9.8, clicks: 13.2, ctr: 0.08, cpc: -6.2 },
    campaigns: [
      { name: "플레이스 검색광고", spend: 2604900, impressions: 651820, clicks: 21965, ctr: 3.37, cpc: 119, color: "#03c75a" },
      { name: "지역소상공인 광고", spend: 1267800, impressions: 396500, clicks: 7519, ctr: 1.9, cpc: 169, color: "#7c5cff" },
      { name: "파워링크", spend: 4065500, impressions: 966440, clicks: 25730, ctr: 2.66, cpc: 158, color: "#ff8f4d" }
    ],
    trend: [
      { day: "1주", clicks: 12840, spend: 1843000, ctr: 2.55 },
      { day: "2주", clicks: 13290, spend: 1924800, ctr: 2.68 },
      { day: "3주", clicks: 13980, spend: 2006300, ctr: 2.79 },
      { day: "4주", clicks: 15104, spend: 2164100, ctr: 2.96 }
    ]
  }
};

const viewTitles = {
  overview: "마케팅 대시보드",
  campaigns: "캠페인 분석",
  report: "데일리 리포트",
  connections: "데이터 연동"
};

let currentPeriod = 7;
let currentChartMetric = "clicks";

const number = new Intl.NumberFormat("ko-KR");
const won = value => `${number.format(value)}원`;

function changeMarkup(value, unit = "%") {
  const positive = value >= 0;
  const arrow = positive ? "↑" : "↓";
  return `<span class="${positive ? "up" : "down"}">${arrow} ${Math.abs(value)}${unit}</span> ${DATA[currentPeriod].previousLabel}`;
}

function renderMetrics() {
  const { totals, changes } = DATA[currentPeriod];
  document.querySelector("#metric-spend").textContent = won(totals.spend);
  document.querySelector("#metric-impressions").textContent = number.format(totals.impressions);
  document.querySelector("#metric-clicks").textContent = number.format(totals.clicks);
  document.querySelector("#metric-ctr").textContent = `${totals.ctr.toFixed(2)}%`;
  document.querySelector("#metric-cpc").textContent = won(totals.cpc);
  document.querySelector("#metric-spend-change").innerHTML = changeMarkup(changes.spend);
  document.querySelector("#metric-impressions-change").innerHTML = changeMarkup(changes.impressions);
  document.querySelector("#metric-clicks-change").innerHTML = changeMarkup(changes.clicks);
  document.querySelector("#metric-ctr-change").innerHTML = changeMarkup(changes.ctr, "%p");
  document.querySelector("#metric-cpc-change").innerHTML = changeMarkup(changes.cpc);
  document.querySelectorAll(".date-range").forEach(el => { el.textContent = DATA[currentPeriod].label; });
}

function renderChart() {
  const svg = document.querySelector("#trend-chart");
  const points = DATA[currentPeriod].trend;
  const values = points.map(item => item[currentChartMetric]);
  const min = Math.min(...values) * 0.85;
  const max = Math.max(...values) * 1.08;
  const width = 700;
  const height = 240;
  const xStep = width / Math.max(points.length - 1, 1);
  const toY = value => height - ((value - min) / (max - min || 1)) * (height - 26) - 10;
  const coords = values.map((value, index) => [index * xStep, toY(value)]);
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `M ${coords[0][0]} ${height} L ${coords.map(([x, y]) => `${x} ${y}`).join(" L ")} L ${coords.at(-1)[0]} ${height} Z`;
  const labels = { clicks: "클릭수", spend: "광고비", ctr: "클릭률" };

  svg.setAttribute("aria-label", `${labels[currentChartMetric]} 추이`);
  svg.innerHTML = `
    <defs><linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#c9ff3d" stop-opacity=".72"/><stop offset="1" stop-color="#c9ff3d" stop-opacity="0"/></linearGradient></defs>
    ${[0, 60, 120, 180, 240].map(y => `<line class="chart-grid-line" x1="0" y1="${y}" x2="700" y2="${y}"/>`).join("")}
    <path class="trend-area" d="${area}"/>
    <polyline class="trend-line" points="${line}"/>
    ${coords.map(([x, y], index) => `<circle class="trend-dot" cx="${x}" cy="${y}" r="${index === coords.length - 1 ? 7 : 4}"/>`).join("")}
  `;
  document.querySelector("#chart-labels").innerHTML = points.map(item => `<span>${item.day}</span>`).join("");
}

function renderCampaigns() {
  const campaigns = DATA[currentPeriod].campaigns;
  const maxClicks = Math.max(...campaigns.map(item => item.clicks));
  document.querySelector("#campaign-cards").innerHTML = campaigns.map(item => `
    <article class="campaign-mini">
      <div class="campaign-mini-head"><strong>${item.name}</strong><span class="campaign-color" style="background:${item.color}"></span></div>
      <div class="campaign-mini-value"><strong>${item.ctr.toFixed(2)}%</strong><span>CTR · ${number.format(item.clicks)} 클릭</span></div>
      <div class="mini-track"><i style="width:${Math.max(18, item.clicks / maxClicks * 100)}%;background:${item.color}"></i></div>
    </article>
  `).join("");

  document.querySelector("#campaign-table-body").innerHTML = campaigns.map(item => `
    <tr><td>${item.name}</td><td>${won(item.spend)}</td><td>${number.format(item.impressions)}</td><td>${number.format(item.clicks)}</td><td><strong>${item.ctr.toFixed(2)}%</strong></td><td>${won(item.cpc)}</td></tr>
  `).join("");

  const maxCtr = Math.max(...campaigns.map(item => item.ctr));
  document.querySelector("#efficiency-bars").innerHTML = campaigns.map(item => `
    <div class="efficiency-row"><strong>${item.name}</strong><div class="efficiency-track"><i style="width:${item.ctr / maxCtr * 100}%;background:${item.color}"></i></div><strong>${item.ctr.toFixed(2)}% CTR</strong></div>
  `).join("");
}

function renderInsights() {
  const campaigns = DATA[currentPeriod].campaigns;
  const bestCtr = [...campaigns].sort((a, b) => b.ctr - a.ctr)[0];
  const bestCpc = [...campaigns].sort((a, b) => a.cpc - b.cpc)[0];
  const largestSpend = [...campaigns].sort((a, b) => b.spend - a.spend)[0];
  const insights = [
    `${bestCtr.name}의 클릭률이 ${bestCtr.ctr.toFixed(2)}%로 가장 높습니다.`,
    `${bestCpc.name}의 평균 CPC가 ${won(bestCpc.cpc)}으로 가장 효율적입니다.`,
    `${largestSpend.name}가 전체 광고비 중 가장 큰 비중을 차지합니다.`
  ];
  document.querySelector("#insight-list").innerHTML = insights.map((text, index) => `<div class="insight-item"><span>0${index + 1}</span><p>${text}</p></div>`).join("");
}

function reportText() {
  const { totals, campaigns, label } = DATA[currentPeriod];
  const best = [...campaigns].sort((a, b) => b.ctr - a.ctr)[0];
  return `📊 네이버 광고 데일리 브리프 (${label})\n\n총 광고비 ${won(totals.spend)} · 노출 ${number.format(totals.impressions)} · 클릭 ${number.format(totals.clicks)}\n전체 CTR ${totals.ctr.toFixed(2)}% · 평균 CPC ${won(totals.cpc)}\n\n캠페인별 성과\n${campaigns.map(item => `• ${item.name}: CTR ${item.ctr.toFixed(2)}% / 평균 CPC ${won(item.cpc)}`).join("\n")}\n\n오늘의 포인트\n• ${best.name}의 CTR이 ${best.ctr.toFixed(2)}%로 가장 높습니다.\n• 전환 지표는 현재 측정하지 않습니다. 클릭 품질과 비용 효율을 중심으로 판단하세요.\n\n※ 현재 화면은 샘플 데이터입니다.`;
}

function renderReport() {
  const { totals, campaigns, label } = DATA[currentPeriod];
  const best = [...campaigns].sort((a, b) => b.ctr - a.ctr)[0];
  document.querySelector("#report-content").innerHTML = `
    <h3>📊 네이버 광고 데일리 브리프</h3>
    <p>${label}</p>
    <div class="report-divider"></div>
    <p><strong>총 광고비</strong> ${won(totals.spend)} · <strong>클릭</strong> ${number.format(totals.clicks)}</p>
    <p><strong>전체 CTR</strong> <mark>${totals.ctr.toFixed(2)}%</mark> · <strong>평균 CPC</strong> ${won(totals.cpc)}</p>
    <div class="report-divider"></div>
    <strong>캠페인별 성과</strong>
    <ul>${campaigns.map(item => `<li>${item.name} — CTR ${item.ctr.toFixed(2)}% / 평균 CPC ${won(item.cpc)}</li>`).join("")}</ul>
    <strong>오늘의 포인트</strong>
    <p>${best.name}의 CTR이 ${best.ctr.toFixed(2)}%로 가장 높습니다. 전환은 측정하지 않으며 클릭 품질과 비용 효율을 중심으로 판단합니다.</p>
    <p><small>※ 현재 화면은 샘플 데이터입니다.</small></p>
  `;
}

function renderAll() {
  renderMetrics();
  renderChart();
  renderCampaigns();
  renderInsights();
  renderReport();
}

function showView(view) {
  document.querySelectorAll("[data-view-panel]").forEach(panel => {
    const active = panel.dataset.viewPanel === view;
    panel.hidden = !active;
    panel.classList.toggle("is-visible", active);
  });
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    if (active && button.closest(".main-nav")) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelector("#page-title").textContent = viewTitles[view];
  history.replaceState(null, "", `#${view}`);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelectorAll("[data-view-link]").forEach(button => button.addEventListener("click", () => showView(button.dataset.viewLink)));

document.querySelectorAll("[data-period]").forEach(button => button.addEventListener("click", () => {
  currentPeriod = Number(button.dataset.period);
  document.querySelectorAll("[data-period]").forEach(item => item.classList.toggle("is-active", item === button));
  renderAll();
}));

document.querySelectorAll("[data-chart-metric]").forEach(button => button.addEventListener("click", () => {
  currentChartMetric = button.dataset.chartMetric;
  document.querySelectorAll("[data-chart-metric]").forEach(item => item.classList.toggle("is-active", item === button));
  renderChart();
}));

document.querySelector("#copy-report").addEventListener("click", async () => {
  const feedback = document.querySelector("#copy-feedback");
  try {
    await navigator.clipboard.writeText(reportText());
    feedback.textContent = "복사했습니다.";
  } catch {
    feedback.textContent = "브라우저에서 복사를 허용해 주세요.";
  }
  window.setTimeout(() => { feedback.textContent = ""; }, 2500);
});

window.addEventListener("hashchange", () => {
  const requestedView = location.hash.slice(1);
  if (viewTitles[requestedView]) showView(requestedView);
});

const initialView = location.hash.slice(1);
renderAll();
showView(viewTitles[initialView] ? initialView : "overview");
