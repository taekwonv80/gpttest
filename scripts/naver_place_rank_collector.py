#!/usr/bin/env python3
"""Record a Naver Map Place result position for configured keywords.

This reads only the public Naver Map search-result list.  It does not log in
or retain any Naver account credentials.  Naver may personalise results by
location and device, therefore every measurement is labelled with its source
and capture time instead of being represented as an absolute universal rank.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 local verification compatibility
    ZoneInfo = None


SEOUL = ZoneInfo("Asia/Seoul") if ZoneInfo else timezone(timedelta(hours=9))
CONFIG_PATH = Path("data/tracker_config.json")
HISTORY_PATH = Path("data/rank_history.json")
MAP_SEARCH_URL = "https://map.naver.com/p/search/{query}"
MAX_HISTORY = 3650


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
    """Find the first matching visible result and retain whether it was an ad."""
    normalized_targets = [normalize(name) for name in target_names if normalize(name)]
    for index, text in enumerate(card_texts, start=1):
        name = card_name(text)
        normalized_name = normalize(name)
        if normalized_name and any(target in normalized_name for target in normalized_targets):
            return {
                "rank": index,
                "matched_name": name,
                "is_ad": "광고" in text,
                "visible_result_count": len(card_texts),
            }
    return None


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


async def public_result_cards(keyword: str) -> list[str]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = await context.new_page()
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
                    cards = frame.locator("li.UEzoS")
                    try:
                        await cards.first.wait_for(timeout=5_000)
                        texts = await collect_scrolled_cards(frame)
                        if texts:
                            return texts
                    except Exception:
                        pass
                await page.wait_for_timeout(1_000)
        finally:
            await context.close()
            await browser.close()
    raise RankCollectionError(f"검색 결과를 읽지 못했습니다: {keyword}")


async def collect_scrolled_cards(frame: Any) -> list[str]:
    """Accumulate virtualized Map result cards instead of only the first viewport."""
    cards = frame.locator("li.UEzoS")
    seen: list[str] = []
    seen_texts: set[str] = set()
    unchanged_rounds = 0

    for _ in range(30):
        texts = [text.strip() for text in await cards.all_inner_texts() if text.strip()]
        before = len(seen)
        for text in texts:
            if text not in seen_texts:
                seen_texts.add(text)
                seen.append(text)

        # Naver Map virtualizes the list: moving the last rendered row into view
        # loads the next rows while older rows can disappear from the DOM.
        try:
            await cards.last.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            break
        await frame.wait_for_timeout(700)

        unchanged_rounds = unchanged_rounds + 1 if len(seen) == before else 0
        if unchanged_rounds >= 3:
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
    measurements = []
    for keyword in keywords:
        cards = await public_result_cards(keyword)
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
                "status": "found" if match else "not_found_in_visible_results",
                **volumes[keyword],
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
        if rank is None:
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
