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


def metric(row: dict[str, Any], name: str) -> float:
    try:
        return float(row.get(name) or 0)
    except (TypeError, ValueError):
        return 0.0


def enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    impressions = metric(row, "impressions")
    clicks = metric(row, "clicks")
    spend = metric(row, "spend")
    return {
        **row,
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
        "ctr": clicks / impressions * 100 if impressions else 0.0,
        "cpc": spend / clicks if clicks else 0.0,
    }


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
) -> dict[str, Any]:
    item = enrich_row(row)
    value = str(item.get("value") or "").strip()
    impressions, clicks = item["impressions"], item["clicks"]
    ctr, cpc = item["ctr"], item["cpc"]
    kind = intent(value)
    confidence_label, confidence_score = confidence(impressions, clicks)

    action, reason, proposal, priority = "유지", "성과 표본을 더 수집합니다.", "현재 설정 유지", 25
    if source == "실제 검색어" and kind == "무관 의도":
        action, reason, proposal, priority = (
            "제외",
            "매장 방문보다 정보·구매·구직 의도가 강한 검색어입니다.",
            "제외 검색어 등록 검토",
            96 if clicks else 88,
        )
    elif source == "등록 키워드" and impressions == 0:
        action, reason, proposal, priority = (
            "중지",
            "최근 분석기간 동안 노출이 없습니다.",
            "계절·브랜드 키워드가 아니면 OFF",
            74,
        )
    elif impressions >= 500 and ctr < 0.3:
        if kind in {"브랜드", "방문 의도"}:
            action, reason, proposal = "개선", "관련성은 높지만 충분히 노출된 뒤에도 클릭 반응이 낮습니다.", "전용 광고그룹·소재·랜딩 개선"
        else:
            action, reason, proposal = "감액", "노출은 충분하지만 CTR이 0.3% 미만입니다.", "입찰 -20% 또는 일시중지 검토"
        priority = 86
    elif impressions < 200 or clicks < 10:
        reason = f"판단 표본이 부족합니다(노출 {impressions:,.0f}·클릭 {clicks:,.0f})."
        proposal, priority = "최소 노출 200·클릭 10까지 관찰", 18
    elif source == "실제 검색어" and kind in {"브랜드", "방문 의도"} and ctr >= max(cohort_ctr * 1.25, 1.0):
        action, reason, proposal, priority = (
            "확대",
            "방문 의도가 높고 같은 유형보다 클릭 반응이 좋습니다.",
            "일치 키워드 추가 또는 입찰 +10~15%",
            84,
        )
    elif ctr >= max(cohort_ctr * 1.35, 1.2) and cpc <= max(cohort_cpc * 1.15, 1):
        action, reason, proposal, priority = (
            "확대",
            "CTR이 기준보다 높고 CPC도 안정적입니다.",
            "입찰 +10~15% 후 7일 관찰",
            80,
        )
    elif cohort_ctr and ctr < cohort_ctr * 0.5:
        if kind in {"브랜드", "방문 의도"}:
            action, reason, proposal = "개선", "같은 유형의 CTR 중앙값보다 50% 이상 낮습니다.", "문구·확장소재·연결 URL 점검"
        else:
            action, reason, proposal = "감액", "같은 유형보다 클릭 반응이 크게 낮습니다.", "입찰 -15~20%"
        priority = 76
    elif cohort_cpc and cpc > cohort_cpc * 1.5:
        action, reason, proposal, priority = (
            "감액",
            "평균 CPC가 같은 유형의 1.5배를 넘습니다.",
            "입찰 -15% 후 7일 관찰",
            70,
        )
    elif kind in {"브랜드", "방문 의도"} and ctr >= cohort_ctr:
        reason, proposal, priority = "방문 의도와 클릭 반응이 안정적입니다.", "현재 입찰 유지", 38

    # Low-confidence positive/negative optimizations should be reviewed later.
    adjusted_priority = priority if action == "제외" else round(priority * (0.65 + confidence_score * 0.0035))
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
        result.append(
            recommend(
                row,
                source=source,
                cohort_ctr=median(ctr_values) if ctr_values else 0,
                cohort_cpc=median(cpc_values) if cpc_values else 0,
            )
        )
    return sorted(
        result,
        key=lambda row: (-row["priority"], ACTION_META[row["action"]]["order"], -row["spend"]),
    )
