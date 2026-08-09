"""Transparent, recommendation-only rules for Naver Powerlink keywords."""

from __future__ import annotations

from statistics import median
from typing import Any


ACTIONS = ("제외", "중지", "감액", "개선", "유지", "확대")
ACTION_META = {
    "제외": {"color": "#ff5f57", "label": "제외 검색어", "order": 0},
    "중지": {"color": "#8b9290", "label": "일시중지", "order": 1},
    "감액": {"color": "#ff9f43", "label": "입찰 감액", "order": 2},
    "개선": {"color": "#7c5cff", "label": "소재 개선", "order": 3},
    "유지": {"color": "#4d5a55", "label": "유지·관찰", "order": 4},
    "확대": {"color": "#03c75a", "label": "확대 후보", "order": 5},
}

# Only unambiguous non-visit intent is automatically recommended for exclusion.
# Region mismatches and competitor names require human review.
IRRELEVANT_TOKENS = (
    "레시피", "만들기", "만드는법", "밀키트", "택배", "배송", "도매",
    "창업", "가맹", "프랜차이즈", "채용", "구인", "알바", "칼로리",
    "재료", "소스", "뜻", "영어로",
)
BRAND_TOKENS = ("택이네", "바다를품다")
HIGH_INTENT_TOKENS = (
    "장현", "장곡", "능곡", "시흥", "조개전골", "샤브샤브", "해물",
    "맛집", "회식", "가족외식", "모임", "예약",
)

MIN_DECISION_IMPRESSIONS = 200
MIN_DECISION_CLICKS = 10
STRONG_IMPRESSIONS = 500
LOW_CTR_PERCENT = 0.3


def metric(row: dict[str, Any], name: str) -> float:
    try:
        return float(row.get(name) or 0)
    except (TypeError, ValueError):
        return 0.0


def normalized_metrics(row: dict[str, Any]) -> dict[str, float]:
    impressions = metric(row, "impressions")
    clicks = metric(row, "clicks")
    spend = metric(row, "spend")
    return {
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
        "ctr": clicks / impressions * 100 if impressions else 0.0,
        "cpc": spend / clicks if clicks else 0.0,
    }


def window_metrics(row: dict[str, Any], label: str) -> dict[str, float] | None:
    windows = row.get("windows")
    if isinstance(windows, dict) and isinstance(windows.get(label), dict):
        return normalized_metrics(windows[label])
    if label == "30":
        return normalized_metrics(row)
    return None


def enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    primary = window_metrics(row, "30") or normalized_metrics(row)
    windows = {
        label: stats
        for label in ("7", "previous_7", "30", "90")
        if (stats := window_metrics(row, label)) is not None
    }
    return {**row, **primary, "metric_windows": windows}


def trend_signal(item: dict[str, Any]) -> tuple[str, str]:
    windows = item.get("metric_windows") or {}
    current = windows.get("7")
    previous = windows.get("previous_7")
    if not current or not previous:
        return "확인 불가", "직전 7일 비교 데이터가 없습니다."
    if (
        min(current["impressions"], previous["impressions"]) < 100
        and min(current["clicks"], previous["clicks"]) < 5
    ):
        return "표본 부족", "7일 추세를 판단할 표본이 부족합니다."
    if previous["clicks"] == 0 and current["clicks"] >= 5:
        return "상승", "최근 7일 클릭 반응이 새로 발생했습니다."
    if current["clicks"] == 0 and previous["clicks"] >= 5:
        return "하락", "최근 7일 클릭 반응이 사라졌습니다."
    if previous["ctr"] <= 0:
        return "보합", "직전 7일 CTR이 0이라 증감률을 확정하기 어렵습니다."
    ratio = current["ctr"] / previous["ctr"]
    if ratio >= 1.25:
        return "상승", f"최근 7일 CTR이 직전 7일보다 {(ratio - 1) * 100:.0f}% 높습니다."
    if ratio <= 0.75:
        return "하락", f"최근 7일 CTR이 직전 7일보다 {(1 - ratio) * 100:.0f}% 낮습니다."
    return "보합", "최근 7일 CTR이 직전 7일과 비슷합니다."


def decision_metrics(item: dict[str, Any]) -> tuple[str, dict[str, float]]:
    windows = item.get("metric_windows") or {}
    primary = windows.get("30") or normalized_metrics(item)
    if (
        primary["impressions"] >= MIN_DECISION_IMPRESSIONS
        and primary["clicks"] >= MIN_DECISION_CLICKS
    ):
        return "최근 30일", primary
    long_term = windows.get("90")
    if long_term and (
        long_term["impressions"] >= MIN_DECISION_IMPRESSIONS
        and long_term["clicks"] >= MIN_DECISION_CLICKS
    ):
        return "최근 90일", long_term
    return "최근 30일", primary


def intent(value: str) -> str:
    compact = value.replace(" ", "").casefold()
    if any(token in compact for token in IRRELEVANT_TOKENS):
        return "무관 의도"
    if any(token in compact for token in BRAND_TOKENS):
        return "브랜드"
    if any(token in compact for token in HIGH_INTENT_TOKENS):
        return "방문 의도"
    return "일반 탐색"


def confidence(impressions: float, clicks: float) -> tuple[str, int]:
    score = min(100, round(min(impressions / 500, 1) * 55 + min(clicks / 20, 1) * 45))
    if score >= 75:
        return "높음", score
    if score >= 40:
        return "보통", score
    return "낮음", score


def recommend(
    row: dict[str, Any],
    *,
    source: str,
    cohort_ctr: float,
    cohort_cpc: float,
    cohort_ctr_90: float = 0,
    cohort_cpc_90: float = 0,
) -> dict[str, Any]:
    item = enrich_row(row)
    value = str(item.get("value") or "").strip()
    decision_period, evidence = decision_metrics(item)
    impressions, clicks = evidence["impressions"], evidence["clicks"]
    ctr, cpc = evidence["ctr"], evidence["cpc"]
    comparison_ctr = cohort_ctr_90 if decision_period == "최근 90일" else cohort_ctr
    comparison_cpc = cohort_cpc_90 if decision_period == "최근 90일" else cohort_cpc
    kind = intent(value)
    confidence_label, confidence_score = confidence(impressions, clicks)
    trend, trend_reason = trend_signal(item)
    long_term = (item.get("metric_windows") or {}).get("90")

    action, reason, proposal, priority = "유지", "성과 표본을 더 수집합니다.", "현재 설정 유지", 25
    if source == "실제 검색어" and kind == "무관 의도":
        action, reason, proposal, priority = (
            "제외",
            "매장 방문보다 정보·구매·구직 의도가 강한 검색어입니다.",
            "제외 검색어 등록 검토",
            96 if clicks else 88,
        )
    elif source == "등록 키워드" and long_term is not None and long_term["impressions"] == 0:
        action, reason, proposal, priority = (
            "중지",
            "최근 90일 동안 노출이 없습니다.",
            "신규 등록·광고 상태·입찰가 확인 후 OFF",
            74,
        )
        decision_period = "최근 90일"
    elif impressions >= STRONG_IMPRESSIONS and ctr < LOW_CTR_PERCENT:
        if kind in {"브랜드", "방문 의도"}:
            action, reason, proposal = "개선", f"관련성은 높지만 {decision_period} 클릭 반응이 낮습니다.", "전용 광고그룹·소재·랜딩 개선"
        elif trend == "상승":
            action, reason, proposal = "유지", "장기 CTR은 낮지만 최근 7일 반응이 회복 중입니다.", "7일 추가 관찰 후 감액 재판정"
        else:
            action, reason, proposal = "감액", f"{decision_period} 노출은 충분하지만 CTR이 0.3% 미만입니다.", "입찰 -15~20% 후 7일 관찰"
        priority = 86
    elif impressions < MIN_DECISION_IMPRESSIONS or clicks < MIN_DECISION_CLICKS:
        reason = (
            f"30일과 90일 모두 판단 표본이 부족합니다(선택 표본 노출 {impressions:,.0f}·클릭 {clicks:,.0f})."
            if long_term is not None
            else f"최근 30일 표본이 부족합니다(노출 {impressions:,.0f}·클릭 {clicks:,.0f}). 90일 지표는 다음 수집 후 적용됩니다."
        )
        proposal, priority = "노출 200·클릭 10까지 유지·관찰", 18
    elif source == "실제 검색어" and kind in {"브랜드", "방문 의도"} and ctr >= max(comparison_ctr * 1.25, 1.0) and trend != "하락":
        action, reason, proposal, priority = (
            "확대",
            f"{decision_period} 방문 의도와 클릭 반응이 좋고 7일 추세도 꺾이지 않았습니다.",
            "일치 키워드 추가 또는 입찰 +10~15%",
            84,
        )
    elif ctr >= max(comparison_ctr * 1.35, 1.2) and cpc <= max(comparison_cpc * 1.15, 1) and trend != "하락":
        action, reason, proposal, priority = (
            "확대",
            f"{decision_period} CTR이 기준보다 높고 CPC와 7일 추세도 안정적입니다.",
            "입찰 +10~15% 후 7일 관찰",
            80,
        )
    elif comparison_ctr and ctr < comparison_ctr * 0.5:
        if kind in {"브랜드", "방문 의도"}:
            action, reason, proposal = "개선", "같은 유형의 CTR 중앙값보다 50% 이상 낮습니다.", "문구·확장소재·연결 URL 점검"
        elif trend == "상승":
            action, reason, proposal = "유지", "같은 유형보다 CTR은 낮지만 최근 7일 반응이 상승 중입니다.", "7일 추가 관찰"
        else:
            action, reason, proposal = "감액", "같은 유형보다 클릭 반응이 크게 낮습니다.", "입찰 -15~20%"
        priority = 76
    elif comparison_cpc and cpc > comparison_cpc * 1.5 and trend != "상승":
        action, reason, proposal, priority = (
            "감액",
            f"{decision_period} 평균 CPC가 같은 유형의 1.5배를 넘고 7일 회복 신호가 없습니다.",
            "입찰 -15% 후 7일 관찰",
            70,
        )
    elif kind in {"브랜드", "방문 의도"} and ctr >= comparison_ctr:
        reason, proposal, priority = "방문 의도와 클릭 반응이 안정적입니다.", "현재 입찰 유지", 38

    # Low-confidence positive/negative optimizations should be reviewed later.
    adjusted_priority = priority if action == "제외" else round(priority * (0.65 + confidence_score * 0.0035))
    window_7 = (item.get("metric_windows") or {}).get("7") or {}
    window_30 = (item.get("metric_windows") or {}).get("30") or normalized_metrics(item)
    window_90 = (item.get("metric_windows") or {}).get("90") or {}
    return {
        **item,
        "source": source,
        "intent": kind,
        "action": action,
        "action_label": ACTION_META[action]["label"],
        "reason": reason,
        "proposal": proposal,
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "priority": min(100, adjusted_priority),
        "decision_period": decision_period,
        "trend": trend,
        "trend_reason": trend_reason,
        "impressions_7": window_7.get("impressions", 0),
        "clicks_7": window_7.get("clicks", 0),
        "ctr_7": window_7.get("ctr", 0),
        "impressions_30": window_30.get("impressions", 0),
        "clicks_30": window_30.get("clicks", 0),
        "ctr_30": window_30.get("ctr", 0),
        "spend_30": window_30.get("spend", 0),
        "impressions_90": window_90.get("impressions", 0),
        "clicks_90": window_90.get("clicks", 0),
        "ctr_90": window_90.get("ctr", 0),
        "spend_90": window_90.get("spend", 0),
        "has_90_window": bool(window_90),
    }


def build_action_plan(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    enriched = [enrich_row(row) for row in rows]
    cohorts: dict[str, list[dict[str, Any]]] = {}
    for row in enriched:
        cohorts.setdefault(str(row.get("category") or "미분류"), []).append(row)

    result: list[dict[str, Any]] = []
    for row in enriched:
        peers = cohorts[str(row.get("category") or "미분류")]
        ctr_values = [peer["ctr"] for peer in peers if peer["impressions"] >= 100]
        cpc_values = [peer["cpc"] for peer in peers if peer["clicks"] > 0]
        peer_90 = [peer["metric_windows"].get("90") for peer in peers]
        ctr_values_90 = [stats["ctr"] for stats in peer_90 if stats and stats["impressions"] >= 100]
        cpc_values_90 = [stats["cpc"] for stats in peer_90 if stats and stats["clicks"] > 0]
        result.append(
            recommend(
                row,
                source=source,
                cohort_ctr=median(ctr_values) if ctr_values else 0,
                cohort_cpc=median(cpc_values) if cpc_values else 0,
                cohort_ctr_90=median(ctr_values_90) if ctr_values_90 else 0,
                cohort_cpc_90=median(cpc_values_90) if cpc_values_90 else 0,
            )
        )
    return sorted(
        result,
        key=lambda row: (-row["priority"], ACTION_META[row["action"]]["order"], -row["spend"]),
    )
