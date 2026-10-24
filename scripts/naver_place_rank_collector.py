#!/usr/bin/env python3
"""Record a Naver Map Place result position for configured keywords.

This reads only the public Naver Map search-result list.  It does not log in
or retain any Naver account credentials.  Naver may personalise results by
location and device, therefore every measurement is labelled with its source
and capture time instead of being represented as an absolute universal rank.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python 3.8 local verification compatibility
    ZoneInfo = None
    ZoneInfoNotFoundError = ValueError


try:
    SEOUL = ZoneInfo("Asia/Seoul") if ZoneInfo else timezone(timedelta(hours=9))
except ZoneInfoNotFoundError:  # Minimal local Python builds can omit tzdata.
    SEOUL = timezone(timedelta(hours=9))
CONFIG_PATH = Path("data/tracker_config.json")
HISTORY_PATH = Path("data/rank_history.json")
MAP_SEARCH_URL = "https://map.naver.com/p/search/{query}"
PUBLIC_TREND_URL = "https://datalab.naver.com/keyword/trendSearch.naver"
MAX_HISTORY = 3650
MAX_TRACKED_RANK = 100
# Naver Map's generated CSS classes can change.  Keep the previous selector
# during rollout, but prefer the class used by the current public result list.
RESULT_CARD_SELECTOR = "li.VLTHu, li.UEzoS"


class RankCollectionError(RuntimeError):
    pass


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback
    return value if isinstance(value, dict) else fallback


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", value.casefold())


def card_name(card_text: str) -> str:
    return next((line.strip() for line in card_text.splitlines() if line.strip()), "")


def find_rank(card_texts: list[str], target_names: list[str]) -> dict[str, Any] | None:
    """Find the first matching non-ad result and count only non-ad results."""
    normalized_targets = [normalize(name) for name in target_names if normalize(name)]
    organic_rank = 0
    for text in card_texts:
        if "광고" in text:
            continue
        organic_rank += 1
        name = card_name(text)
        normalized_name = normalize(name)
        if normalized_name and any(target in normalized_name for target in normalized_targets):
            return {
                "rank": organic_rank,
                "matched_name": name,
                "is_ad": False,
                "visible_result_count": len(card_texts),
            }
    return None


def rank_status(match: dict[str, Any] | None, checked_count: int) -> str:
    if match:
        return "found"
    # "100위 밖"은 실제로 100개 결과를 모두 확인했을 때만 확정한다.
    return "outside_top_100" if checked_count >= MAX_TRACKED_RANK else "not_found_in_visible_results"


def numeric_volume(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"[\d,]+", value.strip()):
        return int(value.replace(",", ""))
    return None


def search_volume(rows: list[dict[str, Any]], keyword: str) -> dict[str, int | None]:
    """Pick the exact Keyword Tool row rather than a related-keyword suggestion."""
    match = next(
        (row for row in rows if normalize(str(row.get("relKeyword") or "")) == normalize(keyword)),
        None,
    )
    if not match:
        return {"monthly_pc_searches": None, "monthly_mobile_searches": None, "monthly_searches": None}
    pc = numeric_volume(match.get("monthlyPcQcCnt"))
    mobile = numeric_volume(match.get("monthlyMobileQcCnt"))
    return {
        "monthly_pc_searches": pc,
        "monthly_mobile_searches": mobile,
        "monthly_searches": pc + mobile if pc is not None and mobile is not None else None,
    }


def pending_volume() -> dict[str, int | None]:
    return {"monthly_pc_searches": None, "monthly_mobile_searches": None, "monthly_searches": None}


def collect_keyword_volumes(keywords: list[str]) -> dict[str, dict[str, int | None]]:
    """Use the existing signed SearchAd credentials, never expose them to Pages."""
    # GitHub Actions invokes this file directly (``python scripts/...py``),
    # where ``scripts`` is not an importable top-level package.
    try:
        from scripts.naver_daily_report import IntegrationError, NaverSearchAdClient, required_env
    except ModuleNotFoundError as error:
        if error.name != "scripts":
            raise
        from naver_daily_report import IntegrationError, NaverSearchAdClient, required_env

    try:
        client = NaverSearchAdClient(
            customer_id=required_env("NAVER_CUSTOMER_ID"),
            api_key=required_env("NAVER_ACCESS_LICENSE"),
            secret_key=required_env("NAVER_SECRET_KEY"),
        )
    except IntegrationError as error:
        print(f"검색량 수집 건너뜀: {error}")
        return {keyword: pending_volume() for keyword in keywords}

    volumes = {}
    for index, keyword in enumerate(keywords):
        try:
            volumes[keyword] = search_volume(client.keyword_tool(keyword), keyword)
        except IntegrationError as error:
            print(f"검색량 수집 건너뜀: {keyword} · {error}")
            volumes[keyword] = pending_volume()
        if index < len(keywords) - 1:
            # Keyword Tool has a lower rate limit than other SearchAd APIs.
            import time
            time.sleep(3)
    return volumes


def monthly_trend_from_xlsx(content: bytes) -> list[dict[str, Any]]:
    """Read date/value rows from the public trend page's downloaded workbook."""
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        strings_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        strings = ["".join(item.itertext()) for item in strings_root.findall(f"{namespace}si")]
        sheet_root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    trend = []
    for row in sheet_root.findall(f".//{namespace}row"):
        values = []
        for cell in row.findall(f"{namespace}c"):
            raw = cell.findtext(f"{namespace}v")
            values.append(strings[int(raw)] if cell.get("t") == "s" and raw is not None else raw)
        if len(values) < 2 or not re.fullmatch(r"\d{4}-\d{2}-01", str(values[0] or "")):
            continue
        try:
            ratio = float(str(values[1]).replace(",", ""))
        except (TypeError, ValueError):
            continue
        trend.append({"month": values[0][:7], "ratio": ratio})
    return trend


async def collect_keyword_trends(keywords: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Collect public monthly search indices with no account or API credentials."""
    from playwright.async_api import async_playwright

    trends = {keyword: [] for keyword in keywords}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = await context.new_page()
        try:
            for keyword in keywords:
                try:
                    await page.goto(PUBLIC_TREND_URL, wait_until="networkidle", timeout=45_000)
                    await page.locator("#item_keyword1").fill(keyword)
                    await page.locator("#item_sub_keyword1_1").fill(keyword)
                    # The public page's one-year default contains the latest
                    # twelve completed monthly values, including last year's
                    # months when this month's value is not final yet.
                    await page.locator("#timeDimensionTitle").click()
                    await page.locator("#timeDimensionDiv ._item_month a").click()
                    async with page.expect_navigation(wait_until="networkidle", timeout=45_000):
                        await page.locator("a._trend_search_detail_query").click()
                    async with page.expect_download(timeout=30_000) as download_info:
                        await page.locator("a.sp_btn_file_down").click()
                    download = await download_info.value
                    download_path = await download.path()
                    if not download_path:
                        raise RankCollectionError("월별 검색지수 파일을 받지 못했습니다.")
                    trends[keyword] = monthly_trend_from_xlsx(Path(download_path).read_bytes())
                except Exception as error:
                    print(f"월별 검색 추이 수집 건너뜀: {keyword} · {type(error).__name__}: {error}")
        finally:
            await context.close()
            await browser.close()
    return trends


async def public_result_cards(keyword: str) -> list[str]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = await context.new_page()
        last_error: Exception | None = None
        try:
            await page.goto(
                MAP_SEARCH_URL.format(query=quote(keyword)),
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            await page.wait_for_selector("iframe#searchIframe", timeout=30_000)
            for _ in range(30):
                frame = next(
                    (item for item in page.frames if "pcmap.place.naver.com" in item.url),
                    None,
                )
                if frame:
                    cards = frame.locator(RESULT_CARD_SELECTOR)
                    try:
                        await cards.first.wait_for(timeout=5_000)
                        texts = await collect_scrolled_cards(frame)
                        if texts:
                            return texts
                    except Exception as error:
                        last_error = error
                await page.wait_for_timeout(1_000)
        finally:
            await context.close()
            await browser.close()
    detail = f" ({type(last_error).__name__}: {last_error})" if last_error else ""
    raise RankCollectionError(f"검색 결과를 읽지 못했습니다: {keyword}{detail}")


async def collect_scrolled_cards(frame: Any) -> list[str]:
    """Accumulate unique virtualized Map result cards across scrolling."""
    cards = frame.locator(RESULT_CARD_SELECTOR)
    seen: list[str] = []
    seen_places: set[str] = set()
    unchanged_rounds = 0

    # Keep requesting additional virtualized rows until the tracked top-100
    # range is filled. Map can delay list loading after a scroll.
    for _ in range(80):
        texts = [text.strip() for text in await cards.all_inner_texts() if text.strip()]
        before = len(seen)
        for text in texts:
            # The virtualized list re-renders the same place with changing
            # review/menu text. Count the place once, not each rendering.
            place_key = normalize(card_name(text))
            if place_key and place_key not in seen_places:
                seen_places.add(place_key)
                seen.append(text)

        if len(seen) >= MAX_TRACKED_RANK:
            return seen[:MAX_TRACKED_RANK]

        # Naver Map virtualizes the list: moving the last rendered row into view
        # loads the next rows while older rows can disappear from the DOM.
        try:
            await cards.last.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            break
        await frame.wait_for_timeout(1_000)

        unchanged_rounds = unchanged_rounds + 1 if len(seen) == before else 0
        # Only conclude that the list ended after several full seconds without
        # any new row. This avoids mistaking delayed lazy-loading for the end.
        if unchanged_rounds >= 8:
            break

    return seen


async def collect_measurements(config: dict[str, Any]) -> list[dict[str, Any]]:
    place = config.get("place") or {}
    primary_name = str(place.get("name") or "").strip()
    aliases = [str(item).strip() for item in place.get("aliases") or []]
    targets = [primary_name, *aliases]
    keywords = [str(item).strip() for item in config.get("keywords") or [] if str(item).strip()]
    if not targets or not primary_name or not keywords:
        raise RankCollectionError("tracker_config.json에 업체명과 키워드를 등록해 주세요.")

    measured_at = datetime.now(SEOUL).isoformat(timespec="seconds")
    volumes = collect_keyword_volumes(keywords)
    trends = await collect_keyword_trends(keywords)
    measurements = []
    for keyword in keywords:
        cards = (await public_result_cards(keyword))[:MAX_TRACKED_RANK]
        match = find_rank(cards, targets)
        measurements.append(
            {
                "keyword": keyword,
                "measured_at": measured_at,
                "source": "naver-map-public-search",
                "rank": match["rank"] if match else None,
                "matched_name": match["matched_name"] if match else None,
                "is_ad": match["is_ad"] if match else None,
                "visible_result_count": match["visible_result_count"] if match else len(cards),
                "status": rank_status(match, len(cards)),
                **volumes[keyword],
                "monthly_trend": trends[keyword],
            }
        )
    return measurements


def append_history(history: dict[str, Any], measurements: list[dict[str, Any]], place_id: str) -> dict[str, Any]:
    existing = list(history.get("measurements") or [])
    captured_keywords = {item["keyword"] for item in measurements}
    captured_at = measurements[0]["measured_at"] if measurements else ""
    existing = [
        item for item in existing
        if not (item.get("keyword") in captured_keywords and item.get("measured_at") == captured_at)
    ]
    merged = (existing + measurements)[-MAX_HISTORY:]
    return {
        "schema_version": 1,
        "place_id": place_id,
        "updated_at": captured_at,
        "measurements": merged,
    }


def previous_rank(history: dict[str, Any], keyword: str) -> int | None:
    for item in reversed(history.get("measurements") or []):
        if item.get("keyword") == keyword and isinstance(item.get("rank"), int):
            return item["rank"]
    return None


def slack_payload(measurements: list[dict[str, Any]], previous: dict[str, Any], dashboard_url: str) -> dict[str, Any]:
    lines = []
    for item in measurements:
        rank = item["rank"]
        prior = previous_rank(previous, item["keyword"])
        if item.get("status") == "outside_top_100":
            result = "100위 밖"
        elif rank is None:
            result = "상위 공개 결과에서 찾지 못함"
        elif prior is None:
            result = f"{rank}위 · 첫 측정"
        else:
            change = prior - rank
            result = f"{rank}위 · {'▲' if change > 0 else '▼' if change < 0 else '—'} {abs(change)}단계"
        ad_mark = " · 광고" if item.get("is_ad") else ""
        volume = item.get("monthly_searches")
        volume_mark = f" · 월 검색량 {volume:,}" if isinstance(volume, int) else " · 검색량 확인 중"
        lines.append(f"• *{item['keyword']}* — {result}{ad_mark}{volume_mark}")
    return {
        "text": "네이버 플레이스 키워드 순위 리포트",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "📍 네이버 플레이스 순위"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
            {"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "대시보드 열기"}, "url": dashboard_url}]},
        ],
    }


def send_slack(webhook_url: str, payload: dict[str, Any]) -> None:
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RankCollectionError(f"Slack 전송 실패: HTTP {response.status}")


def main() -> None:
    config = read_json(CONFIG_PATH, {})
    history = read_json(HISTORY_PATH, {"schema_version": 1, "measurements": []})
    measurements = asyncio.run(collect_measurements(config))
    dashboard_url = os.environ.get("DASHBOARD_URL", "https://taekwonv80.github.io/gpttest")
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if webhook_url:
        send_slack(webhook_url, slack_payload(measurements, history, dashboard_url))
    place_id = str((config.get("place") or {}).get("id") or "")
    write_json(HISTORY_PATH, append_history(history, measurements, place_id))
    print(f"순위 측정 완료: {', '.join(item['keyword'] for item in measurements)}")


if __name__ == "__main__":
    main()
