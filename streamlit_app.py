from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="택이네조개전골 장현점 바다를품다 · 광고 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


COLORS = {
    "플레이스 검색광고": "#03C75A",
    "지역소상공인 광고": "#7C5CFF",
    "파워링크": "#FF8F4D",
}

SAMPLE_WEEKLY_DATA = {
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


def load_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_csv_rows(path: str) -> list[dict[str, str]]:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


DASHBOARD_PAYLOAD = load_json("data/campaign_weekly.json")
CONNECTIONS = load_json("data/connections.json")
PLACE_LATEST = load_json("data/naver_place_latest.json")
PLACE_DAILY = load_csv_rows("data/naver_place_daily.csv")
LIVE_DATA = DASHBOARD_PAYLOAD.get("source") == "naver-searchad-api"

if DASHBOARD_PAYLOAD.get("weeks"):
    WEEKLY_DATA = {
        week["label"]: week.get("campaigns", [])
        for week in DASHBOARD_PAYLOAD["weeks"]
        if week.get("label") and week.get("campaigns")
    }
    DAILY_DATA = {
        week["label"]: week.get("daily", [])
        for week in DASHBOARD_PAYLOAD["weeks"]
        if week.get("label")
    }
else:
    WEEKLY_DATA = SAMPLE_WEEKLY_DATA
    DAILY_DATA = {}

if not WEEKLY_DATA:
    WEEKLY_DATA = SAMPLE_WEEKLY_DATA

WEEK_KEYS = list(WEEKLY_DATA)

DAY_DATA = {
    item["label"]: item.get("campaigns", [])
    for item in DASHBOARD_PAYLOAD.get("days", [])
    if item.get("label") and item.get("campaigns")
}
if not DAY_DATA:
    DAY_DATA = {
        "2026.07.31 (금)": [
            {"name": "플레이스 검색광고", "spend": 91_800, "impressions": 22_700, "clicks": 768},
            {"name": "지역소상공인 광고", "spend": 45_400, "impressions": 13_550, "clicks": 271},
            {"name": "파워링크", "spend": 146_400, "impressions": 34_020, "clicks": 926},
        ]
    }
DAY_KEYS = list(DAY_DATA)


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
    live_daily = [
        item for item in DAILY_DATA.get(week_label, [])
        if item.get("available", True)
    ]
    if live_daily:
        ordered = sorted(live_daily, key=lambda item: item.get("date", ""))
        days = [item.get("date", "")[-5:].replace("-", ".") for item in ordered]
        result = {
            name: {"clicks": [], "spend": []}
            for name in COLORS
        }
        for item in ordered:
            by_name = {
                campaign.get("name"): campaign
                for campaign in item.get("campaigns", [])
            }
            for name in COLORS:
                campaign = by_name.get(name, {})
                result[name]["clicks"].append(int(campaign.get("clicks", 0)))
                result[name]["spend"].append(int(campaign.get("spend", 0)))
        return days, result

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

    if LIVE_DATA:
        synced = str(DASHBOARD_PAYLOAD.get("generated_at", ""))[:19].replace("T", " ")
        st.success(f"네이버 검색광고 API 자동 연동 · 마지막 동기화 {synced}", icon="✅")
    else:
        st.info("첫 자동 수집 전까지 샘플 데이터를 표시합니다. 비밀키는 GitHub Actions Secrets에만 저장됩니다.", icon="ℹ️")

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


def render_daily(day_label: str, rows: list[dict], previous_rows: list[dict]) -> None:
    current = totals(rows)
    previous = totals(previous_rows)
    st.markdown(
        f"""
        <div class="page-heading">
          <span>DAILY ANALYSIS</span>
          <h1>하루의 성과를<br>정확하게.</h1>
          <p>{escape(day_label)} · 전일과 비교해 광고 효율 변화를 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            st.metric(label, value, f"{delta:+.2f}{suffix} 전일 대비")

    st.markdown("### 광고 유형별 일일 성과")
    campaign_cards(rows)

    left, right = st.columns(2)
    with left:
        st.markdown("### 클릭수")
        clicks = go.Figure(
            go.Bar(
                x=[row["name"] for row in rows],
                y=[row["clicks"] for row in rows],
                marker_color=[COLORS[row["name"]] for row in rows],
                text=[f"{row['clicks']:,}" for row in rows],
                textposition="outside",
                hovertemplate="%{x}<br>%{y:,} 클릭<extra></extra>",
            )
        )
        st.plotly_chart(plot_layout(clicks, 340), use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown("### 광고비")
        spend = go.Figure(
            go.Bar(
                x=[row["name"] for row in rows],
                y=[row["spend"] for row in rows],
                marker_color=[COLORS[row["name"]] for row in rows],
                text=[won(row["spend"]) for row in rows],
                textposition="outside",
                hovertemplate="%{x}<br>%{y:,.0f}원<extra></extra>",
            )
        )
        spend.update_yaxes(tickprefix="₩")
        st.plotly_chart(plot_layout(spend, 340), use_container_width=True, config={"displayModeBar": False})


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


def render_report(day_label: str, rows: list[dict]) -> None:
    current = totals(rows)
    best = max(rows, key=lambda item: item["ctr"])
    data_note = "네이버 API 자동 수집 데이터" if LIVE_DATA else "첫 자동 수집 전 샘플 데이터"
    st.markdown(
        """
        <div class="page-heading"><span>DAILY BRIEF</span><h1>숫자를 결론으로.</h1>
        <p>선택한 날짜의 핵심 성과를 Slack 리포트 형식으로 미리 봅니다.</p></div>
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
              <div class="slack-card__app"><i>택</i><div><b>택이네조개전골 장현점 바다를품다</b><small>앱 · 오전 8:30</small></div></div>
              <h3>📊 네이버 광고 일일 브리프</h3><p>{escape(day_label)}</p>
              <hr><p><b>총 광고비</b> {won(current['spend'])} · <b>클릭</b> {current['clicks']:,}</p>
              <p><b>전체 CTR</b> <mark>{current['ctr']:.2f}%</mark> · <b>평균 CPC</b> {won(current['cpc'])}</p>
              <hr><b>캠페인별 성과</b><ul>{lines}</ul>
              <b>이번 주 포인트</b><p>{escape(best['name'])}의 CTR이 {best['ctr']:.2f}%로 가장 높습니다. 전환은 측정하지 않으며 클릭 품질과 비용 효율을 중심으로 판단합니다.</p>
              <small>※ {data_note}</small>
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
              <li><b>03</b><div><strong>대시보드 갱신</strong><p>집계 JSON을 GitHub에 안전하게 저장</p></div></li>
              <li><b>04</b><div><strong>Slack 발송</strong><p>오전 8시 30분 지정 채널 전송</p></div></li></ol>
            </div>
            """,
            unsafe_allow_html=True,
        )


def as_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return None


def json_counts(value: object) -> dict[str, int]:
    try:
        parsed = value if isinstance(value, dict) else json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(name): count
        for name, raw in parsed.items()
        if (count := as_int(raw)) is not None
    }


def count_label(value: object) -> str:
    parsed = as_int(value)
    return f"{parsed:,}회" if parsed is not None else "—"


def delta_label(value: object) -> str | None:
    parsed = as_int(value)
    return f"오늘 +{parsed:,}회" if parsed is not None else None


def counts_chart(values: dict[str, int], color: str, height: int = 330) -> go.Figure:
    ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)[:10]
    figure = go.Figure(
        go.Bar(
            x=[value for _, value in ranked][::-1],
            y=[name for name, _ in ranked][::-1],
            orientation="h",
            marker_color=color,
            text=[f"{value:,}" for _, value in ranked][::-1],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,}회<extra></extra>",
        )
    )
    figure.update_xaxes(showgrid=True, gridcolor="#edf0ee", rangemode="tozero")
    figure.update_yaxes(showgrid=False)
    return plot_layout(figure, height)


def render_place_statistics() -> None:
    st.markdown(
        """
        <div class="page-heading"><span>NAVER SMARTPLACE</span><h1>플레이스 통계.</h1>
        <p>유입부터 예약 신청까지, 매일 쌓인 실제 운영 지표를 한 화면에서 봅니다.</p></div>
        """,
        unsafe_allow_html=True,
    )

    if not PLACE_LATEST:
        st.warning(
            "아직 네이버 플레이스 자동 수집 결과가 없습니다. 최초 로그인 세션과 통계 화면을 등록한 뒤 "
            "GitHub Actions의 ‘Naver SmartPlace daily statistics’를 실행해주세요.",
            icon="🔐",
        )
        st.markdown(
            """
            <div class="place-empty"><b>연결되면 자동으로 표시되는 항목</b>
            <p>플레이스 유입 · 예약/주문 신청 · 스마트콜 통화 · 리뷰 등록 · 유입채널 · 유입키워드</p>
            <p>예약 유입 · 신청 · 취소 · 완료 · 예약 유입채널 · 일별 유입트렌드</p></div>
            """,
            unsafe_allow_html=True,
        )
        return

    generated_at = str(PLACE_LATEST.get("generated_at") or "")[:19].replace("T", " ")
    st.caption(f"마지막 자동 수집: {generated_at or '확인 불가'} · 이번 주 월요일부터 현재까지 누적")
    metric_columns = st.columns(4)
    metric_specs = (
        ("플레이스 유입수", "place_visits_weekly", "place_visits_daily_delta"),
        ("예약·주문 신청수", "booking_orders_weekly", "booking_orders_daily_delta"),
        ("스마트콜 통화수", "smartcall_weekly", "smartcall_daily_delta"),
        ("리뷰 등록수", "reviews_weekly", "reviews_daily_delta"),
    )
    for column, (label, total_key, delta_key) in zip(metric_columns, metric_specs):
        column.metric(
            label,
            count_label(PLACE_LATEST.get(total_key)),
            delta=delta_label(PLACE_LATEST.get(delta_key)),
            delta_color="normal",
        )

    history = PLACE_DAILY or [
        {key: str(value) for key, value in PLACE_LATEST.items() if value is not None}
    ]
    period = st.selectbox("통계 기간", ["최근 7일", "최근 30일", "전체"], index=1)
    limit = {"최근 7일": 7, "최근 30일": 30}.get(period)
    visible = history[-limit:] if limit else history
    dates = [str(row.get("collected_date", ""))[5:] for row in visible]

    st.subheader("일별 유입트렌드")
    trend = go.Figure()
    for label, field, color in (
        ("플레이스 유입", "place_visits_daily_delta", "#03C75A"),
        ("예약·주문 신청", "booking_orders_daily_delta", "#7C5CFF"),
        ("스마트콜", "smartcall_daily_delta", "#FF8F4D"),
        ("리뷰 등록", "reviews_daily_delta", "#121413"),
    ):
        trend.add_trace(
            go.Scatter(
                x=dates,
                y=[as_int(row.get(field)) for row in visible],
                name=label,
                mode="lines+markers",
                line=dict(color=color, width=3),
                hovertemplate=f"{label}<br>%{{x}} · %{{y:,}}회<extra></extra>",
            )
        )
    trend.update_yaxes(rangemode="tozero", showgrid=True, gridcolor="#edf0ee")
    st.plotly_chart(plot_layout(trend, 350), use_container_width=True, config={"displayModeBar": False})

    channel_counts = json_counts(PLACE_LATEST.get("channels_json"))
    keyword_counts = json_counts(PLACE_LATEST.get("keywords_json"))
    channel_column, keyword_column = st.columns(2)
    with channel_column:
        st.subheader("유입채널")
        if channel_counts:
            st.plotly_chart(
                counts_chart(channel_counts, "#03C75A"),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info("수집 화면에서 유입채널을 확인하지 못했습니다.")
    with keyword_column:
        st.subheader("유입키워드")
        if keyword_counts:
            st.plotly_chart(
                counts_chart(keyword_counts, "#C9FF3D"),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info("수집 화면에서 유입키워드를 확인하지 못했습니다.")

    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)
    st.subheader("예약통계")
    reservation_fields = (
        ("예약 유입", "reservation_inflows_weekly", "reservation_inflows_daily_delta"),
        ("예약 신청", "reservation_applications_weekly", "reservation_applications_daily_delta"),
        ("예약 취소", "reservation_cancellations_weekly", "reservation_cancellations_daily_delta"),
        ("이용 완료", "reservation_completions_weekly", "reservation_completions_daily_delta"),
    )
    reservation_available = any(
        as_int(PLACE_LATEST.get(total_key)) is not None
        for _, total_key, _ in reservation_fields
    )
    if not reservation_available:
        st.info(
            "예약 통계 화면 연결 대기 중입니다. NAVER_PLACE_RESERVATION_STATS_URL Secret을 등록하면 "
            "예약 유입·신청·취소·완료와 유입채널이 표시됩니다."
        )
        return

    reservation_columns = st.columns(4)
    for column, (label, total_key, delta_key) in zip(reservation_columns, reservation_fields):
        column.metric(
            label,
            count_label(PLACE_LATEST.get(total_key)),
            delta=delta_label(PLACE_LATEST.get(delta_key)),
        )

    reservation_trend = go.Figure()
    for label, total_key, delta_key in reservation_fields[:3]:
        reservation_trend.add_trace(
            go.Scatter(
                x=dates,
                y=[as_int(row.get(delta_key)) for row in visible],
                name=label,
                mode="lines+markers",
                line=dict(width=3),
                hovertemplate=f"{label}<br>%{{x}} · %{{y:,}}회<extra></extra>",
            )
        )
    reservation_trend.update_yaxes(rangemode="tozero", showgrid=True, gridcolor="#edf0ee")
    reservation_left, reservation_right = st.columns([1.4, 1])
    with reservation_left:
        st.markdown("**예약 유입트렌드**")
        st.plotly_chart(
            plot_layout(reservation_trend, 330),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with reservation_right:
        st.markdown("**예약 유입채널**")
        reservation_channels = json_counts(PLACE_LATEST.get("reservation_channels_json"))
        if reservation_channels:
            st.plotly_chart(
                counts_chart(reservation_channels, "#7C5CFF", 330),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info("예약 유입채널 데이터가 아직 없습니다.")


def render_connections() -> None:
    naver = CONNECTIONS.get("naver", {})
    slack = CONNECTIONS.get("slack", {})
    naver_status = escape(str(naver.get("status", "첫 실행 대기")))
    slack_status = escape(str(slack.get("status", "첫 실행 대기")))
    naver_sync = str(naver.get("last_sync") or "아직 실행되지 않음")[:19].replace("T", " ")
    slack_delivery = str(slack.get("last_delivery") or "아직 발송되지 않음")[:19].replace("T", " ")
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
            f"""
            <div class="connection-card primary"><div><i>N</i><span>{naver_status}</span></div>
            <h3>네이버 검색광고 API</h3><p>광고비, 노출수, 클릭수, 클릭률, 평균 CPC를 자동 수집합니다.</p>
            <small>마지막 동기화 · {escape(naver_sync)}</small></div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="connection-card"><div><i>#</i><span>{slack_status}</span></div>
            <h3>Slack 데일리 리포트</h3><p>Incoming Webhook으로 계산된 리포트를 지정 채널에 전송합니다.</p>
            <small>최근 발송 · {escape(slack_delivery)} · 매일 08:30</small></div>
            """,
            unsafe_allow_html=True,
        )
    if naver.get("connected") and slack.get("connected"):
        st.success("API 키와 Webhook은 GitHub Actions Secrets에 보관되며, 이 화면에는 연결 상태만 표시됩니다.", icon="🔒")
    else:
        st.warning("Secrets 등록 후 GitHub Actions를 처음 실행하면 연결 상태가 자동으로 갱신됩니다.", icon="⏳")


st.markdown(
    """
    <style>
    :root { --ink:#121413; --muted:#717873; --line:#dde2df; --lime:#c9ff3d; --canvas:#f4f6f4; }
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display:none !important; }
    [data-testid="stAppViewContainer"], .stApp { background:var(--canvas); color:var(--ink); }
    .block-container { max-width:1440px; padding:1.7rem 3rem 5rem; }
    h1,h2,h3,p { letter-spacing:-.025em; }
    .top-brand { display:flex; align-items:center; justify-content:space-between; padding:.3rem 0 1.25rem; border-bottom:1px solid var(--line); margin-bottom:1rem; }
    .top-brand__name { display:flex; align-items:center; gap:.7rem; font-size:1rem; font-weight:900; line-height:1.25; }
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
    .place-empty { margin-top:1rem; padding:1.5rem; border:1px solid var(--line); border-radius:18px; background:white; }
    .place-empty b { font-size:1rem; }.place-empty p { margin:.65rem 0 0; color:var(--muted); font-size:.76rem; }
    .section-rule { height:1px; margin:2.2rem 0; background:var(--line); }
    @media(max-width:760px){
      .block-container{padding:1rem 1rem 4rem}.top-brand__status{display:none}.top-brand__name{font-size:.78rem}
      [data-testid="stHorizontalBlock"]{gap:.5rem}.hero-copy{padding:1.7rem 0 1rem}
      .hero-copy h1,.page-heading h1{font-size:2.8rem;line-height:1.08}
      [data-testid="stRadio"] div[role="radiogroup"]{width:100%;overflow-x:auto}
      [data-testid="stRadio"] div[role="radiogroup"] label{padding:.4rem .55rem;white-space:nowrap;font-size:.72rem}
      [data-testid="stMetric"]{min-height:125px}.campaign-card{min-height:155px}
    }
    </style>
    <div class="top-brand"><div class="top-brand__name"><span class="top-brand__mark"><i></i><i></i><i></i></span>택이네조개전골 장현점 바다를품다</div><div class="top-brand__status">● PYTHON · STLITE</div></div>
    """,
    unsafe_allow_html=True,
)

nav_col, filter_col = st.columns([2.8, 1.2], vertical_alignment="bottom")
with nav_col:
    page = st.radio(
        "메뉴",
        ["대시보드", "캠페인 분석", "일일 분석", "플레이스 통계", "데일리 리포트", "데이터 연동"],
        horizontal=True,
        label_visibility="collapsed",
    )

selected_week = WEEK_KEYS[0]
selected_day = DAY_KEYS[0]
with filter_col:
    if page in {"일일 분석", "데일리 리포트"}:
        selected_day = st.selectbox("분석 일자", DAY_KEYS, index=0)
    elif page not in {"플레이스 통계", "데이터 연동"}:
        selected_week = st.selectbox("분석 주간 (월—일)", WEEK_KEYS, index=0)
    elif page == "플레이스 통계":
        st.caption("매일 09:10 자동 수집")
    else:
        st.caption("매일 08:30 자동 연동")

selected_index = WEEK_KEYS.index(selected_week)
previous_index = min(selected_index + 1, len(WEEK_KEYS) - 1)
selected_rows = enrich(WEEKLY_DATA[selected_week])
previous_rows = enrich(WEEKLY_DATA[WEEK_KEYS[previous_index]])

selected_day_index = DAY_KEYS.index(selected_day)
previous_day_index = min(selected_day_index + 1, len(DAY_KEYS) - 1)
selected_day_rows = enrich(DAY_DATA[selected_day])
previous_day_rows = enrich(DAY_DATA[DAY_KEYS[previous_day_index]])

if page == "대시보드":
    render_overview(selected_week, selected_rows, previous_rows)
elif page == "캠페인 분석":
    render_campaigns(selected_week, selected_rows)
elif page == "일일 분석":
    render_daily(selected_day, selected_day_rows, previous_day_rows)
elif page == "플레이스 통계":
    render_place_statistics()
elif page == "데일리 리포트":
    render_report(selected_day, selected_day_rows)
else:
    render_connections()
