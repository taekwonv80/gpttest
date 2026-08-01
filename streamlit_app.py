from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Localight · 네이버 마케팅 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


COLORS = {
    "플레이스 검색광고": "#03C75A",
    "지역소상공인 광고": "#7C5CFF",
    "파워링크": "#FF8F4D",
}

WEEKLY_DATA = {
    "2026.07.25 — 07.31": [
        {"name": "플레이스 검색광고", "spend": 642_800, "impressions": 158_420, "clicks": 5_374},
        {"name": "지역소상공인 광고", "spend": 318_000, "impressions": 94_850, "clicks": 1_897},
        {"name": "파워링크", "spend": 1_024_500, "impressions": 238_100, "clicks": 6_480},
    ],
    "2026.07.18 — 07.24": [
        {"name": "플레이스 검색광고", "spend": 598_200, "impressions": 151_300, "clicks": 4_864},
        {"name": "지역소상공인 광고", "spend": 315_000, "impressions": 93_600, "clicks": 1_724},
        {"name": "파워링크", "spend": 982_400, "impressions": 232_500, "clicks": 5_940},
    ],
    "2026.07.11 — 07.17": [
        {"name": "플레이스 검색광고", "spend": 621_500, "impressions": 160_100, "clicks": 5_123},
        {"name": "지역소상공인 광고", "spend": 306_000, "impressions": 91_250, "clicks": 1_630},
        {"name": "파워링크", "spend": 1_001_200, "impressions": 241_200, "clicks": 6_102},
    ],
    "2026.07.04 — 07.10": [
        {"name": "플레이스 검색광고", "spend": 574_300, "impressions": 149_500, "clicks": 4_710},
        {"name": "지역소상공인 광고", "spend": 298_000, "impressions": 89_700, "clicks": 1_588},
        {"name": "파워링크", "spend": 956_800, "impressions": 229_800, "clicks": 5_735},
    ],
    "2026.06.27 — 07.03": [
        {"name": "플레이스 검색광고", "spend": 552_700, "impressions": 145_800, "clicks": 4_542},
        {"name": "지역소상공인 광고", "spend": 287_000, "impressions": 87_200, "clicks": 1_501},
        {"name": "파워링크", "spend": 925_600, "impressions": 224_300, "clicks": 5_481},
    ],
}

WEEK_KEYS = list(WEEKLY_DATA)


def won(value: float) -> str:
    return f"{value:,.0f}원"


def enrich(rows: list[dict]) -> list[dict]:
    return [
        {
            **row,
            "ctr": row["clicks"] / row["impressions"] * 100 if row["impressions"] else 0,
            "cpc": row["spend"] / row["clicks"] if row["clicks"] else 0,
        }
        for row in rows
    ]


def totals(rows: list[dict]) -> dict:
    spend = sum(row["spend"] for row in rows)
    impressions = sum(row["impressions"] for row in rows)
    clicks = sum(row["clicks"] for row in rows)
    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": clicks / impressions * 100 if impressions else 0,
        "cpc": spend / clicks if clicks else 0,
    }


def pct_change(current: float, previous: float) -> float:
    return (current - previous) / previous * 100 if previous else 0


def allocate(total: int, weights: list[float]) -> list[int]:
    normalized = [weight / sum(weights) for weight in weights]
    values = [round(total * weight) for weight in normalized[:-1]]
    values.append(total - sum(values))
    return values


def daily_series(week_label: str, rows: list[dict]) -> tuple[list[str], dict]:
    start_text = week_label.split(" — ")[0]
    start = datetime.strptime(start_text, "%Y.%m.%d")
    days = [(start + timedelta(days=index)).strftime("%m.%d") for index in range(7)]
    click_weights = {
        "플레이스 검색광고": [0.11, 0.13, 0.12, 0.15, 0.14, 0.17, 0.18],
        "지역소상공인 광고": [0.13, 0.12, 0.15, 0.14, 0.15, 0.16, 0.15],
        "파워링크": [0.12, 0.14, 0.13, 0.15, 0.14, 0.16, 0.16],
    }
    spend_weights = [0.12, 0.13, 0.13, 0.15, 0.14, 0.16, 0.17]
    result = {}
    for row in rows:
        result[row["name"]] = {
            "clicks": allocate(row["clicks"], click_weights[row["name"]]),
            "spend": allocate(row["spend"], spend_weights),
        }
    return days, result


def plot_layout(fig: go.Figure, height: int = 350) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=28, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#4D5550", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="#121413", font_color="#FFFFFF"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#E4E8E5", zeroline=False)
    return fig


def campaign_cards(rows: list[dict]) -> None:
    cols = st.columns(3)
    for col, row in zip(cols, rows):
        color = COLORS[row["name"]]
        with col:
            st.markdown(
                f"""
                <div class="campaign-card" style="--campaign:{color}">
                  <div class="campaign-card__top"><span>{escape(row['name'])}</span><i></i></div>
                  <strong>{row['ctr']:.2f}%</strong>
                  <p>CTR · {row['clicks']:,} 클릭</p>
                  <div class="campaign-card__meta"><span>광고비 {won(row['spend'])}</span><span>평균 CPC {won(row['cpc'])}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_overview(week_label: str, rows: list[dict], previous_rows: list[dict]) -> None:
    current = totals(rows)
    previous = totals(previous_rows)
    st.markdown(
        """
        <div class="hero-copy">
          <span>PERFORMANCE OVERVIEW</span>
          <h1>오늘의 광고 흐름을<br><em>한눈에.</em></h1>
          <p>세 가지 네이버 광고 유형의 핵심 성과와 다음 액션을 Python으로 계산합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info("현재 공개 화면은 샘플 데이터입니다. 네이버 API 비밀키는 GitHub Pages에 저장하지 않습니다.", icon="ℹ️")

    metric_cols = st.columns(5)
    metrics = [
        ("총 광고비", won(current["spend"]), pct_change(current["spend"], previous["spend"]), "%"),
        ("노출수", f"{current['impressions']:,}", pct_change(current["impressions"], previous["impressions"]), "%"),
        ("클릭수", f"{current['clicks']:,}", pct_change(current["clicks"], previous["clicks"]), "%"),
        ("클릭률", f"{current['ctr']:.2f}%", current["ctr"] - previous["ctr"], "%p"),
        ("평균 CPC", won(current["cpc"]), pct_change(current["cpc"], previous["cpc"]), "%"),
    ]
    for col, (label, value, delta, suffix) in zip(metric_cols, metrics):
        with col:
            st.metric(label, value, f"{delta:+.2f}{suffix} 이전 주 대비")

    left, right = st.columns([1.8, 1])
    days, series = daily_series(week_label, rows)
    with left:
        st.markdown("### 일별 클릭 추이")
        fig = go.Figure()
        for row in rows:
            fig.add_trace(
                go.Scatter(
                    x=days,
                    y=series[row["name"]]["clicks"],
                    name=row["name"],
                    mode="lines+markers",
                    line=dict(color=COLORS[row["name"]], width=3),
                    marker=dict(size=7),
                    hovertemplate=f"{row['name']}<br>%{{x}} · %{{y:,}} 클릭<extra></extra>",
                )
            )
        st.plotly_chart(plot_layout(fig, 365), use_container_width=True, config={"displayModeBar": False})
    with right:
        best_ctr = max(rows, key=lambda item: item["ctr"])
        best_cpc = min(rows, key=lambda item: item["cpc"])
        biggest = max(rows, key=lambda item: item["spend"])
        st.markdown(
            f"""
            <div class="signal-card">
              <span>✦ TODAY'S SIGNAL</span>
              <h3>데이터가 말하는<br>이번 주 포인트</h3>
              <ol>
                <li><b>{escape(best_ctr['name'])}</b> CTR {best_ctr['ctr']:.2f}%로 가장 높음</li>
                <li><b>{escape(best_cpc['name'])}</b> 평균 CPC {won(best_cpc['cpc'])}으로 가장 낮음</li>
                <li><b>{escape(biggest['name'])}</b> 광고비 비중이 가장 큼</li>
              </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### 캠페인별 성과")
    campaign_cards(rows)


def render_campaigns(week_label: str, rows: list[dict]) -> None:
    st.markdown(
        f"""
        <div class="page-heading">
          <span>CAMPAIGN ANALYSIS</span>
          <h1>광고 유형별 성과</h1>
          <p>{week_label} · 선택한 주간의 효율을 같은 기준으로 비교합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    campaign_cards(rows)

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("### 클릭률 vs 평균 CPC")
        fig = go.Figure()
        for row in rows:
            fig.add_trace(
                go.Scatter(
                    x=[row["cpc"]],
                    y=[row["ctr"]],
                    name=row["name"],
                    text=[row["name"]],
                    mode="markers+text",
                    textposition="top center",
                    marker=dict(
                        size=32 + row["spend"] / max(item["spend"] for item in rows) * 28,
                        color=COLORS[row["name"]],
                        opacity=0.9,
                        line=dict(color="#FFFFFF", width=3),
                    ),
                    hovertemplate=f"{row['name']}<br>CTR {row['ctr']:.2f}%<br>평균 CPC {won(row['cpc'])}<extra></extra>",
                )
            )
        fig.update_xaxes(title="평균 CPC (원)", tickprefix="₩")
        fig.update_yaxes(title="클릭률 (%)", ticksuffix="%")
        st.plotly_chart(plot_layout(fig, 390), use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown("### 광고비 구성")
        donut = go.Figure(
            go.Pie(
                labels=[row["name"] for row in rows],
                values=[row["spend"] for row in rows],
                hole=0.67,
                marker=dict(colors=[COLORS[row["name"]] for row in rows]),
                textinfo="percent",
                hovertemplate="%{label}<br>%{value:,.0f}원<extra></extra>",
            )
        )
        donut.update_layout(annotations=[dict(text="광고비", x=0.5, y=0.5, showarrow=False, font_size=16)])
        st.plotly_chart(plot_layout(donut, 390), use_container_width=True, config={"displayModeBar": False})

    st.markdown("### 핵심 지표 비교")
    table_rows = "".join(
        f"""
        <tr>
          <td><span class="table-dot" style="background:{COLORS[row['name']]}"></span>{escape(row['name'])}</td>
          <td>{won(row['spend'])}</td><td>{row['impressions']:,}</td><td>{row['clicks']:,}</td>
          <td><b>{row['ctr']:.2f}%</b></td><td>{won(row['cpc'])}</td>
        </tr>
        """
        for row in rows
    )
    st.markdown(
        f"""
        <div class="data-table-wrap"><table class="data-table">
          <thead><tr><th>캠페인 분류</th><th>광고비</th><th>노출수</th><th>클릭수</th><th>클릭률</th><th>평균 CPC</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table></div>
        <div class="calculation-note"><b>평균 CPC</b> = 광고비 ÷ 클릭수. 지역소상공인 광고는 노출 과금형이므로 노출수와 클릭률을 함께 확인하세요.</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 최근 5주 클릭률 변화")
    history = go.Figure()
    chronological = list(reversed(WEEK_KEYS))
    for campaign_name in COLORS:
        ctr_values = []
        for key in chronological:
            item = next(row for row in enrich(WEEKLY_DATA[key]) if row["name"] == campaign_name)
            ctr_values.append(item["ctr"])
        history.add_trace(
            go.Scatter(
                x=[key.replace("2026.", "") for key in chronological],
                y=ctr_values,
                name=campaign_name,
                mode="lines+markers",
                line=dict(color=COLORS[campaign_name], width=3),
                hovertemplate=f"{campaign_name}<br>%{{x}} · %{{y:.2f}}%<extra></extra>",
            )
        )
    history.add_vline(x=week_label.replace("2026.", ""), line_dash="dot", line_color="#121413")
    history.update_yaxes(ticksuffix="%")
    st.plotly_chart(plot_layout(history, 340), use_container_width=True, config={"displayModeBar": False})


def render_report(week_label: str, rows: list[dict]) -> None:
    current = totals(rows)
    best = max(rows, key=lambda item: item["ctr"])
    st.markdown(
        """
        <div class="page-heading"><span>DAILY BRIEF</span><h1>숫자를 결론으로.</h1>
        <p>선택한 주간의 핵심 성과를 Slack 리포트 형식으로 미리 봅니다.</p></div>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.4, 1])
    with left:
        lines = "".join(
            f"<li>{escape(row['name'])} — CTR {row['ctr']:.2f}% / 평균 CPC {won(row['cpc'])}</li>"
            for row in rows
        )
        st.markdown(
            f"""
            <div class="slack-card">
              <div class="slack-card__app"><i>L</i><div><b>Localight Report</b><small>앱 · 오전 8:30</small></div></div>
              <h3>📊 네이버 광고 주간 브리프</h3><p>{week_label}</p>
              <hr><p><b>총 광고비</b> {won(current['spend'])} · <b>클릭</b> {current['clicks']:,}</p>
              <p><b>전체 CTR</b> <mark>{current['ctr']:.2f}%</mark> · <b>평균 CPC</b> {won(current['cpc'])}</p>
              <hr><b>캠페인별 성과</b><ul>{lines}</ul>
              <b>이번 주 포인트</b><p>{escape(best['name'])}의 CTR이 {best['ctr']:.2f}%로 가장 높습니다. 전환은 측정하지 않으며 클릭 품질과 비용 효율을 중심으로 판단합니다.</p>
              <small>※ 현재 화면은 샘플 데이터입니다.</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="flow-card"><span>AUTOMATION FLOW</span><h3>매일 자동화 흐름</h3>
              <ol><li><b>01</b><div><strong>데이터 수집</strong><p>검색광고 API에서 전일 지표 수집</p></div></li>
              <li><b>02</b><div><strong>성과 계산</strong><p>Python으로 CTR·평균 CPC 계산</p></div></li>
              <li><b>03</b><div><strong>인사이트 생성</strong><p>검증된 수치만 GPT에 전달</p></div></li>
              <li><b>04</b><div><strong>Slack 발송</strong><p>오전 8시 30분 지정 채널 전송</p></div></li></ol>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_connections() -> None:
    st.markdown(
        """
        <div class="page-heading"><span>DATA CONNECTIONS</span><h1>자동화 연결 설계</h1>
        <p>공식 API와 안전한 비밀키 보관을 전제로 단계별로 연결합니다.</p></div>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    with left:
        st.markdown(
            """
            <div class="connection-card primary"><div><i>N</i><span>1순위 · 연결 가능</span></div>
            <h3>네이버 검색광고 API</h3><p>광고비, 노출수, 클릭수, 클릭률, 평균 CPC를 자동 수집합니다.</p>
            <small>Customer ID · Access License · Secret Key</small></div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="connection-card"><div><i>#</i><span>2순위 · 준비</span></div>
            <h3>Slack 데일리 리포트</h3><p>Incoming Webhook으로 계산된 리포트를 지정 채널에 전송합니다.</p>
            <small>Webhook URL · 채널 · 발송 시각 08:30</small></div>
            """,
            unsafe_allow_html=True,
        )
    st.warning("GitHub Pages에서 실행되는 stlite에는 비밀키를 저장할 수 없습니다. 실제 자동 수집은 GitHub Actions Secrets 또는 외부 실행 환경이 필요합니다.", icon="🔒")


st.markdown(
    """
    <style>
    :root { --ink:#121413; --muted:#717873; --line:#dde2df; --lime:#c9ff3d; --canvas:#f4f6f4; }
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display:none !important; }
    [data-testid="stAppViewContainer"], .stApp { background:var(--canvas); color:var(--ink); }
    .block-container { max-width:1440px; padding:1.7rem 3rem 5rem; }
    h1,h2,h3,p { letter-spacing:-.025em; }
    .top-brand { display:flex; align-items:center; justify-content:space-between; padding:.3rem 0 1.25rem; border-bottom:1px solid var(--line); margin-bottom:1rem; }
    .top-brand__name { display:flex; align-items:center; gap:.7rem; font-size:1.15rem; font-weight:900; }
    .top-brand__mark { display:inline-flex; gap:3px; transform:skew(-8deg); }
    .top-brand__mark i { width:7px; height:28px; background:var(--lime); border-radius:2px; display:block; }
    .top-brand__mark i:nth-child(2) { transform:translateY(5px); }
    .top-brand__status { padding:.45rem .7rem; border:1px solid var(--line); border-radius:999px; background:white; font-size:.67rem; font-weight:800; }
    [data-testid="stRadio"] > label { display:none; }
    [data-testid="stRadio"] div[role="radiogroup"] { gap:.3rem; background:#171a18; padding:.3rem; border-radius:12px; width:max-content; }
    [data-testid="stRadio"] div[role="radiogroup"] label { padding:.45rem .85rem; border-radius:8px; color:#a8afab; }
    [data-testid="stRadio"] div[role="radiogroup"] label > div:first-child { display:none; }
    [data-testid="stRadio"] div[role="radiogroup"] label p { color:#a8afab !important; }
    [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) { background:var(--lime); color:var(--ink); }
    [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) p { color:var(--ink) !important; }
    [data-testid="stSelectbox"] label p { font-size:.68rem; font-weight:800; color:var(--muted); }
    [data-baseweb="select"] > div { background:white; border-color:var(--line); border-radius:11px; }
    .hero-copy, .page-heading { padding:2.5rem 0 1.6rem; }
    .hero-copy > span, .page-heading > span, .signal-card > span, .flow-card > span { color:var(--muted); font-size:.62rem; font-weight:900; letter-spacing:.18em; }
    .hero-copy h1, .page-heading h1 { margin:.8rem 0 .7rem; font-size:clamp(2.8rem,5vw,5.2rem); line-height:1; letter-spacing:-.065em; }
    .hero-copy h1 em { font-style:normal; color:transparent; -webkit-text-stroke:1.4px var(--ink); }
    .hero-copy p, .page-heading p { color:var(--muted); font-size:.84rem; }
    [data-testid="stAlert"] { border-radius:13px; border:1px solid #cfe1d4; background:#edf6ef; }
    [data-testid="stMetric"] { min-height:150px; padding:1.25rem; border:1px solid var(--line); border-radius:18px; background:white; }
    [data-testid="stMetricLabel"] p { color:var(--muted); font-size:.72rem; font-weight:800; }
    [data-testid="stMetricValue"] { margin-top:1.6rem; font-weight:900; letter-spacing:-.055em; }
    [data-testid="stMetricDelta"] { font-size:.66rem; }
    [data-testid="stPlotlyChart"] { padding:.8rem; border:1px solid var(--line); border-radius:20px; background:white; }
    .campaign-card { min-height:170px; padding:1.25rem; border:1px solid var(--line); border-radius:17px; background:white; }
    .campaign-card__top { display:flex; justify-content:space-between; font-size:.75rem; font-weight:850; }
    .campaign-card__top i { width:10px; height:10px; border-radius:50%; background:var(--campaign); }
    .campaign-card > strong { display:block; margin-top:1.5rem; font-size:2rem; letter-spacing:-.06em; }
    .campaign-card > p { margin:.1rem 0 .8rem; color:var(--muted); font-size:.68rem; }
    .campaign-card__meta { display:flex; justify-content:space-between; padding-top:.7rem; border-top:1px solid var(--line); color:var(--muted); font-size:.6rem; }
    .signal-card { min-height:365px; padding:1.7rem; border:1px solid #a9ec00; border-radius:20px; background:var(--lime); }
    .signal-card h3 { margin:1.8rem 0 1.2rem; font-size:1.7rem; line-height:1.15; }
    .signal-card ol { margin:0; padding-left:1.2rem; }
    .signal-card li { padding:.75rem 0; border-top:1px solid rgba(0,0,0,.14); font-size:.75rem; line-height:1.55; }
    .data-table-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:18px; background:white; }
    .data-table { width:100%; min-width:760px; border-collapse:collapse; font-size:.76rem; }
    .data-table th,.data-table td { padding:1rem; border-bottom:1px solid var(--line); text-align:right; }
    .data-table th:first-child,.data-table td:first-child { text-align:left; font-weight:800; }
    .table-dot { display:inline-block; width:8px; height:8px; margin-right:.55rem; border-radius:50%; }
    .data-table td b { padding:.25rem .45rem; border-radius:5px; background:#effbd1; }
    .calculation-note { margin:.7rem 0 1.8rem; padding:.7rem .9rem; border-radius:10px; background:#e9ecea; color:var(--muted); font-size:.68rem; }
    .slack-card { padding:1.8rem; border:1px solid var(--line); border-radius:22px; background:white; box-shadow:0 18px 50px rgba(23,30,26,.07); font-size:.78rem; line-height:1.7; }
    .slack-card__app { display:flex; gap:.7rem; align-items:center; padding-bottom:1rem; border-bottom:1px solid var(--line); }
    .slack-card__app i { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; background:var(--ink); color:var(--lime); font-style:normal; font-weight:900; }
    .slack-card__app small { display:block; color:var(--muted); }
    .slack-card hr { border:0; border-top:1px solid var(--line); margin:1rem 0; }
    .slack-card mark { padding:.15rem .35rem; border-radius:4px; background:#eaffb0; }
    .flow-card { padding:1.8rem; border-radius:22px; background:var(--ink); color:white; }
    .flow-card h3 { margin:.8rem 0 1.4rem; font-size:1.6rem; }
    .flow-card ol { list-style:none; margin:0; padding:0; }
    .flow-card li { display:grid; grid-template-columns:32px 1fr; gap:.6rem; padding:.9rem 0; border-top:1px solid #343936; }
    .flow-card li > b { color:var(--lime); font:italic .65rem Georgia,serif; }
    .flow-card strong { font-size:.75rem; }.flow-card p { margin:.25rem 0 0; color:#9ba19e; font-size:.67rem; }
    .connection-card { min-height:230px; padding:1.6rem; border:1px solid var(--line); border-radius:20px; background:white; }
    .connection-card.primary { background:var(--lime); border-color:#a9ec00; }
    .connection-card > div { display:flex; align-items:center; justify-content:space-between; }
    .connection-card i { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; background:var(--ink); color:var(--lime); font-style:normal; font-weight:900; }
    .connection-card span { padding:.35rem .55rem; border:1px solid rgba(0,0,0,.18); border-radius:999px; font-size:.58rem; font-weight:800; }
    .connection-card h3 { margin:1.6rem 0 .6rem; }.connection-card p { color:var(--muted); font-size:.75rem; }.connection-card small { font-weight:800; }
    @media(max-width:760px){
      .block-container{padding:1rem 1rem 4rem}.top-brand__status{display:none}
      [data-testid="stHorizontalBlock"]{gap:.5rem}.hero-copy{padding:1.7rem 0 1rem}
      .hero-copy h1,.page-heading h1{font-size:2.8rem;line-height:1.08}
      [data-testid="stRadio"] div[role="radiogroup"]{width:100%;overflow-x:auto}
      [data-testid="stRadio"] div[role="radiogroup"] label{padding:.4rem .55rem;white-space:nowrap;font-size:.72rem}
      [data-testid="stMetric"]{min-height:125px}.campaign-card{min-height:155px}
    }
    </style>
    <div class="top-brand"><div class="top-brand__name"><span class="top-brand__mark"><i></i><i></i><i></i></span>localight</div><div class="top-brand__status">● PYTHON · STLITE</div></div>
    """,
    unsafe_allow_html=True,
)

nav_col, week_col = st.columns([2.8, 1.2], vertical_alignment="bottom")
with nav_col:
    page = st.radio(
        "메뉴",
        ["대시보드", "캠페인 분석", "데일리 리포트", "데이터 연동"],
        horizontal=True,
        label_visibility="collapsed",
    )
with week_col:
    selected_week = st.selectbox("분석 주간", WEEK_KEYS, index=0)

selected_index = WEEK_KEYS.index(selected_week)
previous_index = min(selected_index + 1, len(WEEK_KEYS) - 1)
selected_rows = enrich(WEEKLY_DATA[selected_week])
previous_rows = enrich(WEEKLY_DATA[WEEK_KEYS[previous_index]])

if page == "대시보드":
    render_overview(selected_week, selected_rows, previous_rows)
elif page == "캠페인 분석":
    render_campaigns(selected_week, selected_rows)
elif page == "데일리 리포트":
    render_report(selected_week, selected_rows)
else:
    render_connections()
