#!/usr/bin/env python3
"""Collect the signed-in owner's Naver SmartPlace weekly statistics.

The collector reads only rendered text from the statistics page.  A Playwright
storage-state secret is used for authentication; the Naver password is never
stored in this repository.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from playwright.sync_api import Page


SEOUL = ZoneInfo("Asia/Seoul")
DATA_PATH = Path("data/naver_place_daily.csv")
SNAPSHOT_PATH = Path("data/naver_place_latest.json")
DEBUG_PATH = Path("artifacts/naver-place-debug.png")
SESSION_PATH = Path(".naver-place-session.json")
FIELDS = (
    "collected_date",
    "week_start",
    "place_visits_weekly",
    "booking_orders_weekly",
    "smartcall_weekly",
    "reviews_weekly",
    "place_visits_daily_delta",
    "booking_orders_daily_delta",
    "smartcall_daily_delta",
    "reviews_daily_delta",
    "naver_map_weekly",
    "naver_search_weekly",
    "naver_blog_weekly",
    "instagram_weekly",
    "facebook_weekly",
    "place_ads_weekly",
    "local_smb_ads_weekly",
    "naver_talktalk_weekly",
    "website_weekly",
    "channels_json",
    "keywords_json",
    "reservation_inflows_weekly",
    "reservation_applications_weekly",
    "reservation_cancellations_weekly",
    "reservation_completions_weekly",
    "reservation_inflows_daily_delta",
    "reservation_applications_daily_delta",
    "reservation_cancellations_daily_delta",
    "reservation_completions_daily_delta",
    "reservation_channels_json",
)
DAILY_METRIC_PAIRS = (
    ("place_visits_weekly", "place_visits_daily_delta"),
    ("booking_orders_weekly", "booking_orders_daily_delta"),
    ("smartcall_weekly", "smartcall_daily_delta"),
    ("reviews_weekly", "reviews_daily_delta"),
    ("reservation_inflows_weekly", "reservation_inflows_daily_delta"),
    ("reservation_applications_weekly", "reservation_applications_daily_delta"),
    ("reservation_cancellations_weekly", "reservation_cancellations_daily_delta"),
    ("reservation_completions_weekly", "reservation_completions_daily_delta"),
)


class CollectionError(RuntimeError):
    pass


MetricNumber = int | float


def normalize_metric_text(value: str) -> str:
    """Normalize whitespace and the visually similar middle dots used by SmartPlace."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans("・∙⋅•ㆍ", "·····"))
    normalized = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def metric_label_pattern(label: str) -> str:
    """Allow SmartPlace to split a visible metric label across nested DOM nodes."""
    parts = re.split(r"(·|\s+)", normalize_metric_text(label))
    return "".join(
        r"\s*·\s*" if part == "·" else r"\s*" if part.isspace() else re.escape(part)
        for part in parts
        if part
    )


def metric_number(raw_value: str) -> MetricNumber:
    normalized = raw_value.replace(",", "")
    return float(normalized) if "." in normalized else int(normalized)


def is_smartplace_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "smartplace.naver.com" or hostname.endswith(".smartplace.naver.com")
    )


def current_week_url(url: str, collected_date: date) -> str:
    """Move a saved statistics URL to Monday-through-today at collection time."""
    week_start = collected_date.fromordinal(
        collected_date.toordinal() - collected_date.weekday()
    )
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["startDate"] = week_start.isoformat()
    query["endDate"] = collected_date.isoformat()
    return urlunparse(parsed._replace(query=urlencode(query)))


def statistics_range_url(url: str, start_date: date, end_date: date, term: str) -> str:
    """Move a saved statistics URL to an explicit Naver statistics range."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["startDate"] = start_date.isoformat()
    query["endDate"] = end_date.isoformat()
    query["term"] = term
    return urlunparse(parsed._replace(query=urlencode(query)))


def number_after(text: str, labels: tuple[str, ...]) -> int | None:
    normalized = normalize_metric_text(text)
    for label in labels:
        pattern = (
            rf"{metric_label_pattern(label)}"
            rf"(?:\s*(?:도움말|정보|[?ⓘ]))*\s*(?:은|는|이|가)?\s*([\d,]+)"
            rf"(?:\s*(?:회|건|명))?(?=\s|$)"
        )
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def channel_number(text: str, label: str) -> MetricNumber | None:
    match = re.search(
        rf"{re.escape(label)}\s*([\d,.]+)\s*(?:%|회|건|명)?(?=\s|$)", text
    )
    return metric_number(match.group(1)) if match else None


def channel_value(
    channels: dict[str, MetricNumber], text: str, *labels: str
) -> MetricNumber | None:
    for label in labels:
        if label in channels:
            return channels[label]
    for label in labels:
        value = channel_number(text, label)
        if value is not None:
            return value
    return None


def is_ranked_name(name: str) -> bool:
    """Reject UI chrome and adjacent demographic values from ranked lists."""
    if name in {
        "도움말",
        "지난 주",
        "이번 주",
        "유입",
        "신청",
        "이용완료",
        "이용 완료",
        "취소",
        "확정",
    }:
        return False
    if re.fullmatch(r"[\d,.]+%?", name):
        return False
    if re.fullmatch(r"(?:남자|여자|\d+대)", name):
        return False
    return True


def parse_ranked_section(text: str, start: str, end: str) -> dict[str, MetricNumber]:
    match = re.search(rf"(?:{start})(?P<section>.*?)(?:{end}|$)", text, flags=re.DOTALL)
    section = match.group("section") if match else ""
    values: dict[str, MetricNumber] = {}
    for name, raw_value in re.findall(
        r"(?:^|\n)\s*(?:\d+[.)]?\s+)?([^\n\d][^\n]*?)\s+([\d,.]+)\s*(?:%|회|건|명)?\s*(?=\n|$)",
        section,
    ):
        cleaned = re.sub(r"\s+", " ", name).strip(" -")
        if cleaned and is_ranked_name(cleaned):
            values[cleaned] = metric_number(raw_value)
    lines = [re.sub(r"\s+", " ", line).strip() for line in section.splitlines() if line.strip()]
    for name, raw_value in zip(lines, lines[1:]):
        value_match = re.fullmatch(r"([\d,.]+)\s*(?:%|회|건|명)?", raw_value)
        cleaned = re.sub(r"^\d+[.)]?\s+", "", name).strip(" -")
        if value_match and cleaned and is_ranked_name(cleaned):
            values.setdefault(cleaned, metric_number(value_match.group(1)))
    return values


def parse_channels(text: str) -> dict[str, MetricNumber]:
    """Read every ranked channel shown between the channel and keyword tabs."""
    return parse_ranked_section(
        text,
        r"유입\s*채널",
        r"유입\s*키워드|한 주간 리뷰|스마트콜 통화|예약[·・/]주문",
    )


def parse_keywords(text: str) -> dict[str, MetricNumber]:
    """Read ranked Place inflow keywords and their displayed ratios."""
    return parse_ranked_section(
        text,
        r"유입\s*키워드",
        r"성별|연령|유입\s*고객|한 주간 리뷰|스마트콜 통화|예약[·・/]주문|방문 후 지표",
    )


def parse_summary_metrics(text: str) -> dict[str, int | str]:
    normalized = re.sub(r"[ \t]+", " ", text)
    metrics = {
        "place_visits_weekly": number_after(
            normalized,
            (
                "플레이스 상세페이지 유입 수",
                "플레이스 상세페이지 유입수",
                "플레이스 조회 수",
                "플레이스 조회수",
                "플레이스 유입 수",
                "플레이스 유입수",
                "플레이스 유입",
                "유입 수·매출액",
                "유입수·매출액",
                "유입 수",
                "유입수",
            ),
        ),
        "booking_orders_weekly": number_after(
            normalized,
            ("예약·주문 신청", "예약・주문 신청", "예약/주문 신청", "예약 신청"),
        ),
        "smartcall_weekly": number_after(
            normalized,
            ("스마트콜 통화", "누적 통화 연결", "통화 연결", "총 통화 수", "총 통화수"),
        ),
        "reviews_weekly": number_after(
            normalized, ("리뷰 등록 수", "리뷰 등록", "신규 리뷰", "리뷰 수", "리뷰수")
        ),
    }
    return {key: value if value is not None else "" for key, value in metrics.items()}


def parse_rendered_text(
    text: str, collected_date: date, require_place_visits: bool = True
) -> dict[str, Any]:
    normalized = re.sub(r"[ \t]+", " ", text)
    channels = parse_channels(normalized)
    keywords = parse_keywords(normalized)
    metrics = {
        **parse_summary_metrics(normalized),
        "naver_map_weekly": channel_value(channels, normalized, "네이버지도", "네이버 지도"),
        "naver_search_weekly": channel_value(channels, normalized, "네이버검색", "네이버 검색"),
        "naver_blog_weekly": channel_value(channels, normalized, "네이버블로그", "네이버 블로그"),
        "instagram_weekly": channel_value(channels, normalized, "인스타그램"),
        "facebook_weekly": channel_value(channels, normalized, "페이스북"),
        "place_ads_weekly": channel_value(channels, normalized, "네이버 플레이스광고", "네이버플레이스광고"),
        "local_smb_ads_weekly": channel_value(
            channels,
            normalized,
            "네이버 지역소상공인광고",
            "네이버지역소상공인광고",
            "지역소상공인광고",
            "지역소상공인 광고",
        ),
        "naver_talktalk_weekly": channel_value(channels, normalized, "네이버톡톡", "네이버 톡톡"),
        "website_weekly": channel_value(channels, normalized, "웹사이트"),
    }
    if require_place_visits and metrics["place_visits_weekly"] in (None, ""):
        raise CollectionError("필수 통계 항목을 찾지 못했습니다: place_visits_weekly")

    return {
        "collected_date": collected_date.isoformat(),
        "week_start": collected_date.fromordinal(
            collected_date.toordinal() - collected_date.weekday()
        ).isoformat(),
        **{key: value if value is not None else "" for key, value in metrics.items()},
        "channels_json": json.dumps(channels, ensure_ascii=False, separators=(",", ":")),
        "keywords_json": json.dumps(keywords, ensure_ascii=False, separators=(",", ":")),
    }


def parse_smartcall_text(text: str) -> dict[str, int | str]:
    normalized = re.sub(r"[ \t]+", " ", text)
    value = number_after(
        normalized,
        (
            "스마트콜 통화",
            "누적 통화 연결",
            "통화 연결",
            "연결된 통화",
            "총 통화 수",
            "총 통화수",
            "총 통화",
        ),
    )
    return {"smartcall_weekly": value if value is not None else ""}


def parse_review_text(text: str) -> dict[str, int | str]:
    normalized = re.sub(r"[ \t]+", " ", text)
    value = number_after(
        normalized,
        ("리뷰 등록 수", "리뷰 등록", "신규 리뷰", "등록된 리뷰", "새 리뷰", "리뷰 수", "리뷰수"),
    )
    if value is None:
        review_types = ("영수증", "POS", "Npay커넥트", "예약", "주문", "결제내역")
        values = [number_after(normalized, (label,)) for label in review_types]
        if any(item is not None for item in values):
            value = sum(item or 0 for item in values)
    return {"reviews_weekly": value if value is not None else ""}


def parse_reservation_text(text: str) -> dict[str, Any]:
    """Parse the owner's booking/order statistics page.

    SmartPlace labels have changed over time, so each metric accepts the labels
    used by both the booking and order views. Missing optional metrics stay blank
    instead of being misreported as zero.
    """
    normalized = re.sub(r"[ \t]+", " ", text)
    channels = parse_ranked_section(
        normalized,
        r"유입\s*채널",
        r"고객\s*분석|검색\s*키워드|예약\s*현황|$",
    )
    if not channels:
        channels = parse_ranked_section(
            normalized,
            r"유입\s*경로",
            r"유입\s*트렌드|검색\s*키워드|예약\s*현황|$",
        )
    metrics = {
        "reservation_inflows_weekly": number_after(
            normalized, ("예약 페이지 유입", "예약 유입", "유입")
        ),
        "reservation_applications_weekly": number_after(
            normalized, ("예약 신청", "신청")
        ),
        "reservation_cancellations_weekly": number_after(
            normalized, ("예약 취소", "취소")
        ),
        "reservation_completions_weekly": number_after(
            normalized, ("이용 완료", "이용완료", "예약 완료", "완료")
        ),
    }
    return {
        **{key: value if value is not None else "" for key, value in metrics.items()},
        "reservation_channels_json": json.dumps(
            channels, ensure_ascii=False, separators=(",", ":")
        ),
    }


def merge_present(row: dict[str, Any], values: dict[str, Any]) -> None:
    """Merge a tab result without erasing valid values with missing fields."""
    for key, value in values.items():
        if value not in (None, "", "{}"):
            row[key] = value


def merge_missing(row: dict[str, Any], values: dict[str, Any]) -> None:
    """Use a detail tab only when the report tab did not provide the metric."""
    for key, value in values.items():
        if row.get(key) in (None, "", "{}") and value not in (None, "", "{}"):
            row[key] = value


def load_rows(path: Path = DATA_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add_daily_deltas(row: dict[str, Any], previous: dict[str, str] | None) -> None:
    same_week = previous and previous.get("week_start") == row["week_start"]
    for total_key, delta_key in DAILY_METRIC_PAIRS:
        if row.get(total_key, "") in (None, ""):
            row[delta_key] = ""
            continue
        current = int(row[total_key])
        prior = int(previous.get(total_key) or 0) if same_week else 0
        row[delta_key] = max(0, current - prior)


def build_daily_history_row(
    report_text: str, reservation_text: str, collected_date: date
) -> dict[str, Any]:
    """Build one exact daily history row from single-day Naver report pages."""
    report = parse_summary_metrics(report_text)
    reservation = parse_reservation_text(reservation_text)
    totals = {**report, **reservation}
    result: dict[str, Any] = {
        "collected_date": collected_date.isoformat(),
        "week_start": (collected_date - timedelta(days=collected_date.weekday())).isoformat(),
    }
    for total_key, delta_key in DAILY_METRIC_PAIRS:
        value = totals.get(total_key, "")
        result[delta_key] = value if value not in (None, "") else ""
    return result


def upsert_row(
    row: dict[str, Any],
    path: Path = DATA_PATH,
    daily_rows: list[dict[str, Any]] | None = None,
) -> None:
    rows = load_rows(path)
    previous = next(
        (
            item
            for item in reversed(rows)
            if item["collected_date"] < row["collected_date"]
            and any(item.get(total_key) not in (None, "") for total_key, _ in DAILY_METRIC_PAIRS)
        ),
        None,
    )
    add_daily_deltas(row, previous)
    by_date = {item["collected_date"]: dict(item) for item in rows}
    by_date[row["collected_date"]] = {key: row.get(key, "") for key in FIELDS}
    for daily in daily_rows or []:
        daily_date = str(daily["collected_date"])
        target = by_date.setdefault(daily_date, {key: "" for key in FIELDS})
        target["collected_date"] = daily_date
        target["week_start"] = daily.get("week_start", target.get("week_start", ""))
        for _, delta_key in DAILY_METRIC_PAIRS:
            value = daily.get(delta_key, "")
            if value not in (None, ""):
                target[delta_key] = value
                if daily_date == row["collected_date"]:
                    row[delta_key] = value
    rows = sorted(by_date.values(), key=lambda item: item["collected_date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def session_from_env() -> None:
    raw = os.environ.get("NAVER_PLACE_STORAGE_STATE_B64", "").strip()
    if not raw:
        raise CollectionError("GitHub Secret NAVER_PLACE_STORAGE_STATE_B64가 없습니다.")
    try:
        SESSION_PATH.write_bytes(base64.b64decode(raw, validate=True))
        json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise CollectionError("로그인 세션 Secret 형식이 올바르지 않습니다.") from exc


def collect_page_text(
    page: "Page",
    url: str,
    markers: tuple[str, ...],
    tab_name: str,
    debug_name: str,
    wait_ms: int = 8_000,
) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(wait_ms)
    if "nid.naver.com" in page.url or "login" in page.url.lower():
        raise CollectionError("네이버 로그인 세션이 만료되었습니다. 세션 Secret을 갱신해주세요.")
    text = page.locator("body").inner_text(timeout=30_000)
    (DEBUG_PATH.parent / f"naver-place-{debug_name}.txt").write_text(
        text, encoding="utf-8"
    )
    page.screenshot(
        path=str(DEBUG_PATH.parent / f"naver-place-{debug_name}.png"),
        full_page=True,
    )
    if not any(marker in text for marker in markers):
        raise CollectionError(
            f"{tab_name} 통계 화면이 열리지 않았습니다. 저장된 URL 또는 업체 선택 상태를 확인해주세요."
        )
    return text


def collect_current_week_daily(
    page: "Page", report_url: str, reservation_url: str, today: date
) -> list[dict[str, Any]]:
    """Backfill exact daily metrics from Monday through today."""
    week_start = today - timedelta(days=today.weekday())
    daily_rows: list[dict[str, Any]] = []
    for offset in range((today - week_start).days + 1):
        target = week_start + timedelta(days=offset)
        debug_date = target.strftime("%Y%m%d")
        report_text = collect_page_text(
            page,
            statistics_range_url(report_url, target, target, "daily"),
            ("리포트", "플레이스 유입", "방문 전 지표"),
            f"{target.isoformat()} 리포트",
            f"daily-report-{debug_date}",
            wait_ms=4_000,
        )
        reservation_text = collect_page_text(
            page,
            statistics_range_url(reservation_url, target, target, "daily"),
            ("유입 트렌드", "예약 지표", "예약지표", "예약주문"),
            f"{target.isoformat()} 예약주문",
            f"daily-booking-{debug_date}",
            wait_ms=4_000,
        )
        daily = build_daily_history_row(report_text, reservation_text, target)
        if daily.get("place_visits_daily_delta") in (None, ""):
            raise CollectionError(f"{target.isoformat()} 플레이스 일별 유입을 찾지 못했습니다.")
        daily_rows.append(daily)
    return daily_rows


def validate_daily_totals(
    daily_rows: list[dict[str, Any]], weekly_row: dict[str, Any]
) -> None:
    """Reject a daily query if Naver returned the weekly card for every date."""
    for total_key, delta_key in DAILY_METRIC_PAIRS:
        weekly = weekly_row.get(total_key, "")
        values = [item.get(delta_key, "") for item in daily_rows]
        if weekly in (None, "") or any(value in (None, "") for value in values):
            continue
        daily_total = sum(int(value) for value in values)
        if daily_total != int(weekly):
            raise CollectionError(
                f"일별 합계 검증 실패: {delta_key}={daily_total}, 주간={weekly}"
            )


def main() -> None:
    from playwright.sync_api import sync_playwright

    tab_urls = {
        "리포트": os.environ.get("NAVER_PLACE_REPORT_URL", "").strip(),
        "플레이스": os.environ.get("NAVER_PLACE_STATS_URL", "").strip(),
        "스마트콜": os.environ.get("NAVER_PLACE_SMARTCALL_STATS_URL", "").strip(),
        "예약주문": os.environ.get("NAVER_PLACE_RESERVATION_STATS_URL", "").strip(),
        "리뷰": os.environ.get("NAVER_PLACE_REVIEW_STATS_URL", "").strip(),
    }
    missing_urls = [name for name, url in tab_urls.items() if not url]
    if missing_urls:
        raise CollectionError("통계 탭 URL Secret이 없습니다: " + ", ".join(missing_urls))
    invalid_urls = [name for name, url in tab_urls.items() if not is_smartplace_url(url)]
    if invalid_urls:
        raise CollectionError("통계 탭 URL 형식이 올바르지 않습니다: " + ", ".join(invalid_urls))
    session_from_env()
    today = datetime.now(SEOUL).date()
    tab_urls = {name: current_week_url(url, today) for name, url in tab_urls.items()}
    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_PATH), locale="ko-KR", timezone_id="Asia/Seoul")
        page = context.new_page()
        try:
            report_text = collect_page_text(
                page,
                tab_urls["리포트"],
                ("리포트", "플레이스 유입", "방문 전 지표"),
                "리포트",
                "report",
            )
            place_text = collect_page_text(
                page,
                tab_urls["플레이스"],
                ("플레이스 유입", "유입채널", "유입 채널", "유입키워드"),
                "플레이스",
                "place",
            )
            smartcall_text = collect_page_text(
                page,
                tab_urls["스마트콜"],
                ("스마트콜", "통화 연결", "통화내역"),
                "스마트콜",
                "smartcall",
            )
            reservation_text = collect_page_text(
                page,
                tab_urls["예약주문"],
                ("유입트렌드", "유입 트렌드", "예약 통계", "예약통계", "예약주문"),
                "예약주문",
                "booking",
            )
            review_text = collect_page_text(
                page,
                tab_urls["리뷰"],
                ("리뷰", "방문자 리뷰", "블로그 리뷰"),
                "리뷰",
                "review",
            )

            row = parse_rendered_text(place_text, today, require_place_visits=False)
            merge_present(row, parse_summary_metrics(report_text))
            merge_missing(row, parse_smartcall_text(smartcall_text))
            reservation_values = parse_reservation_text(reservation_text)
            merge_present(row, reservation_values)
            if not row.get("booking_orders_weekly"):
                row["booking_orders_weekly"] = reservation_values.get(
                    "reservation_applications_weekly", ""
                )
            merge_missing(row, parse_review_text(review_text))
            if row.get("place_visits_weekly") in (None, ""):
                raise CollectionError(
                    "플레이스 탭과 리포트 탭 모두에서 유입 수를 찾지 못했습니다."
                )
            daily_rows = collect_current_week_daily(
                page, tab_urls["리포트"], tab_urls["예약주문"], today
            )
            validate_daily_totals(daily_rows, row)
            upsert_row(row, daily_rows=daily_rows)
            SNAPSHOT_PATH.write_text(
                json.dumps({"generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"), **row}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"스마트플레이스 5개 탭 수집 완료: {today.isoformat()} · "
                f"유입 {row['place_visits_weekly']}회"
            )
        except Exception:
            page.screenshot(path=str(DEBUG_PATH), full_page=True)
            raise
        finally:
            context.close()
            browser.close()
            SESSION_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
