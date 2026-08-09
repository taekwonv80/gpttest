#!/usr/bin/env python3
"""Collect Naver SearchAd metrics and send a daily Slack report.

Only aggregate advertising metrics are written to the public ``data`` folder.
Credentials are read from environment variables and are never persisted.
"""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import hmac
import html
import io
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_URL = "https://api.searchad.naver.com"
SEOUL = ZoneInfo("Asia/Seoul")
CATEGORIES = ("플레이스 검색광고", "지역소상공인 광고", "파워링크")
FIELDS = ("impCnt", "clkCnt", "salesAmt", "ctr", "cpc")
DATA_PATH = Path("data/campaign_weekly.json")
KEYWORD_DATA_PATH = Path("data/keyword_analysis.json")
CONNECTIONS_PATH = Path("data/connections.json")
DEFAULT_DASHBOARD_URL = "https://taekwonv80.github.io/gpttest"
STATS_BATCH_SIZE = 100
STATS_MAX_RANGE_DAYS = 30
API_MAX_WORKERS = 4
KEYWORD_STATS_MAX_WORKERS = 8
KEYWORD_RETENTION_DAYS = 90
KEYWORD_PRIMARY_WINDOW_DAYS = 30
KEYWORD_WINDOWS = ("7", "previous_7", "30", "90")
STAT_REPORT_POLL_SECONDS = 2
STAT_REPORT_MAX_POLLS = 30


class IntegrationError(RuntimeError):
    """An external integration failed without exposing a credential."""


def query_string(params: dict[str, Any] | None = None) -> str:
    """Encode repeated query keys the same way as Naver's requests example."""
    return urlencode(params or {}, doseq=True)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise IntegrationError(f"필수 GitHub Secret이 없습니다: {name}")
    return value


def signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}".encode("utf-8")
    digest = hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class NaverSearchAdClient:
    def __init__(self, customer_id: str, api_key: str, secret_key: str) -> None:
        self.customer_id = customer_id
        self.api_key = api_key
        self.secret_key = secret_key
        self._campaigns_cache: list[dict[str, Any]] | None = None
        self._adgroups_cache: dict[str, list[dict[str, Any]]] = {}

    def _headers(self, method: str, uri: str) -> dict[str, str]:
        timestamp = str(round(time.time() * 1000))
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "gpttest-daily-report/1.0",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Signature": signature(timestamp, method, uri, self.secret_key),
        }

    def get(self, uri: str, params: dict[str, Any] | None = None) -> Any:
        query = query_string(params)
        request = Request(
            f"{BASE_URL}{uri}{'?' + query if query else ''}",
            headers=self._headers("GET", uri),
            method="GET",
        )
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with urlopen(request, timeout=40) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")[:500]
                if error.code == 429 and attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise IntegrationError(
                    f"네이버 SearchAd API 오류: HTTP {error.code} · {body}"
                ) from None
            except (URLError, TimeoutError) as error:
                last_error = error
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
        raise IntegrationError(f"네이버 SearchAd API 연결 실패: {last_error}")

    def post(self, uri: str, payload: dict[str, Any]) -> Any:
        request = Request(
            f"{BASE_URL}{uri}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers("POST", uri),
            method="POST",
        )
        try:
            with urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:500]
            raise IntegrationError(
                f"네이버 SearchAd API 오류: HTTP {error.code} · {body}"
            ) from None
        except (URLError, TimeoutError) as error:
            raise IntegrationError(f"네이버 SearchAd API 연결 실패: {error}") from None

    def campaigns(self) -> list[dict[str, Any]]:
        if self._campaigns_cache is not None:
            return list(self._campaigns_cache)
        result = self.get("/ncc/campaigns")
        if not isinstance(result, list):
            raise IntegrationError("네이버 캠페인 응답 형식이 예상과 다릅니다.")
        self._campaigns_cache = [item for item in result if isinstance(item, dict)]
        return list(self._campaigns_cache)

    def adgroups(self, campaign_id: str) -> list[dict[str, Any]]:
        if campaign_id in self._adgroups_cache:
            return list(self._adgroups_cache[campaign_id])
        result = self.get(
            "/ncc/adgroups",
            {"nccCampaignId": campaign_id, "recordSize": 1000},
        )
        if not isinstance(result, list):
            raise IntegrationError("네이버 광고그룹 응답 형식이 예상과 다릅니다.")
        self._adgroups_cache[campaign_id] = [
            item for item in result if isinstance(item, dict)
        ]
        return list(self._adgroups_cache[campaign_id])

    def keywords(self, adgroup_id: str) -> list[dict[str, Any]]:
        result = self.get(
            "/ncc/keywords",
            {"nccAdgroupId": adgroup_id, "recordSize": 1000},
        )
        if not isinstance(result, list):
            raise IntegrationError("네이버 키워드 응답 형식이 예상과 다릅니다.")
        return [item for item in result if isinstance(item, dict)]

    def place_search_terms(self, adgroup_id: str) -> list[dict[str, Any]]:
        result = self.get(
            "/stats",
            {"id": adgroup_id, "statType": "NPLA_SCH_KEYWORD"},
        )
        if not isinstance(result, list):
            raise IntegrationError("네이버 플레이스 검색어 응답 형식이 예상과 다릅니다.")
        return [item for item in result if isinstance(item, dict)]

    def create_stat_report(self, report_type: str, stat_date: date) -> dict[str, Any]:
        result = self.post(
            "/stat-reports",
            {"reportTp": report_type, "statDt": stat_date.strftime("%Y%m%d")},
        )
        if not isinstance(result, dict):
            raise IntegrationError("네이버 대용량 보고서 생성 응답 형식이 예상과 다릅니다.")
        return result

    def stat_report(self, report_job_id: int | str) -> dict[str, Any]:
        result = self.get(f"/stat-reports/{report_job_id}")
        if not isinstance(result, dict):
            raise IntegrationError("네이버 대용량 보고서 조회 응답 형식이 예상과 다릅니다.")
        return result

    def summary_stats(
        self, entity_ids: list[str], since: date, until: date
    ) -> list[dict[str, Any]]:
        result = self.get(
            "/stats",
            {
                "ids": entity_ids,
                "fields": json.dumps(FIELDS, separators=(",", ":")),
                "timeRange": json.dumps(
                    {"since": since.isoformat(), "until": until.isoformat()},
                    separators=(",", ":"),
                ),
                "timeIncrement": "allDays",
            },
        )
        return flatten_stat_rows(result)


def flatten_stat_rows(payload: Any) -> list[dict[str, Any]]:
    """Accept both flat and nested variants returned by the stats endpoint."""
    if isinstance(payload, dict):
        for response_key in ("summaryStatResponse", "dailyStatResponse"):
            response = payload.get(response_key)
            if isinstance(response, dict):
                payload = response
                break
        for key in ("data", "items", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]

    rows: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return rows
    for item in payload:
        if not isinstance(item, dict):
            continue
        nested = item.get("data")
        if isinstance(nested, list):
            parent = {key: value for key, value in item.items() if key != "data"}
            for child in nested:
                if isinstance(child, dict):
                    rows.append({**parent, **child})
        else:
            rows.append(item)
    return rows


def classify_campaign(campaign: dict[str, Any]) -> str | None:
    campaign_type = str(
        campaign.get("campaignTp")
        or campaign.get("campaignType")
        or campaign.get("type")
        or ""
    ).upper()
    name = str(campaign.get("name") or campaign.get("campaignName") or "")

    if campaign_type in {"1", "WEB_SITE", "WEBSITE"}:
        return "파워링크"
    if not campaign_type and ("파워링크" in name or "사이트검색" in name):
        return "파워링크"
    return None


def is_place_campaign(campaign: dict[str, Any]) -> bool:
    campaign_type = str(
        campaign.get("campaignTp")
        or campaign.get("campaignType")
        or campaign.get("type")
        or ""
    ).upper()
    name = str(campaign.get("name") or campaign.get("campaignName") or "")
    if campaign_type:
        return "PLACE" in campaign_type
    return "플레이스" in name


def classify_place_adgroup(adgroup: dict[str, Any]) -> str | None:
    """Classify a Place campaign's adgroup using Naver's official type value."""
    adgroup_type = str(
        adgroup.get("adgroupType")
        or adgroup.get("adGroupType")
        or adgroup.get("type")
        or ""
    ).upper()
    name = str(adgroup.get("name") or adgroup.get("adgroupName") or "")

    if adgroup_type:
        if adgroup_type in {"DOOH", "DIGITAL_OUTDOOR"}:
            return None
        # Naver's legacy type names are counterintuitive: LOCAL_AD was
        # introduced as "플레이스 검색", while PLACE represents Local SMB.
        if adgroup_type in {"PLACE", "LOCAL_SMB", "SMB"}:
            return "지역소상공인 광고"
        if adgroup_type in {"LOCAL_AD", "PLACE_SEARCH"}:
            return "플레이스 검색광고"
        return None

    if "옥외" in name:
        return None
    if "소상공인" in name:
        return "지역소상공인 광고"
    if "플레이스검색" in name:
        return "플레이스 검색광고"
    return None


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def stat_date(row: dict[str, Any]) -> date | None:
    raw = (
        row.get("date")
        or row.get("dateStart")
        or row.get("dateEnd")
        or row.get("statDate")
        or row.get("key")
    )
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def blank_metrics(name: str) -> dict[str, Any]:
    return {"name": name, "spend": 0, "impressions": 0, "clicks": 0}


def add_row(target: dict[str, Any], row: dict[str, Any]) -> None:
    target["spend"] += round(number(row.get("salesAmt")))
    target["impressions"] += round(number(row.get("impCnt")))
    target["clicks"] += round(number(row.get("clkCnt")))


def collect_daily_metrics(
    client: NaverSearchAdClient,
    report_date: date,
    weeks: int = 5,
) -> tuple[dict[date, dict[str, dict[str, Any]]], list[dict[str, Any]]]:
    current_week_start = report_date - timedelta(days=report_date.weekday())
    since = current_week_start - timedelta(days=(weeks - 1) * 7)
    days = (report_date - since).days + 1
    daily: dict[date, dict[str, dict[str, Any]]] = {
        since + timedelta(days=offset): {
            category: blank_metrics(category) for category in CATEGORIES
        }
        for offset in range(days)
    }

    campaigns = client.campaigns()
    matched: list[dict[str, Any]] = []
    adgroup_category_by_id: dict[str, str] = {}
    campaign_category_by_id: dict[str, str] = {}
    excluded_place_adgroups = 0
    for campaign in campaigns:
        campaign_id = str(campaign.get("nccCampaignId") or campaign.get("id") or "")
        if not campaign_id:
            continue

        if is_place_campaign(campaign):
            place_campaign_matched = False
            for adgroup in client.adgroups(campaign_id):
                adgroup_id = str(adgroup.get("nccAdgroupId") or adgroup.get("id") or "")
                category = classify_place_adgroup(adgroup)
                if not category or not adgroup_id:
                    excluded_place_adgroups += 1
                    continue
                adgroup_category_by_id[adgroup_id] = category
                place_campaign_matched = True
            if place_campaign_matched:
                matched.append(campaign)
            continue

        category = classify_campaign(campaign)
        if category:
            matched.append(campaign)
            campaign_category_by_id[campaign_id] = category

    if not matched:
        available = ", ".join(
            sorted(
                {
                    str(item.get("campaignTp") or item.get("campaignType") or "미분류")
                    for item in campaigns
                }
            )
        )
        raise IntegrationError(
            "플레이스·지역소상공인·파워링크 캠페인을 찾지 못했습니다. "
            f"계정의 캠페인 유형: {available or '없음'}"
        )

    target_maps = (adgroup_category_by_id, campaign_category_by_id)
    batches = [
        (category_by_id, entity_ids[start : start + STATS_BATCH_SIZE])
        for category_by_id in target_maps
        for entity_ids in [list(category_by_id)]
        for start in range(0, len(entity_ids), STATS_BATCH_SIZE)
    ]
    target_count = sum(len(category_by_id) for category_by_id in target_maps)
    def fetch_day(target_day: date) -> tuple[date, dict[str, dict[str, Any]]]:
        day_metrics = {category: blank_metrics(category) for category in CATEGORIES}
        for category_by_id, batch in batches:
            try:
                rows = client.summary_stats(batch, target_day, target_day)
            except IntegrationError as exc:
                raise IntegrationError(
                    f"{target_day.isoformat()} 광고 통계 묶음 조회 실패: {exc}"
                ) from None
            for row in rows:
                entity_id = str(
                    row.get("id")
                    or row.get("nccAdgroupId")
                    or row.get("nccCampaignId")
                    or ""
                )
                category = category_by_id.get(entity_id)
                if category:
                    add_row(day_metrics[category], row)
        return target_day, day_metrics

    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        fetched_days = executor.map(fetch_day, sorted(daily))
        for target_day, day_metrics in fetched_days:
            daily[target_day] = day_metrics
            print(
                f"네이버 통계 수집: {target_day.isoformat()} "
                f"({target_count}개 통계 대상, {len(batches)}개 묶음)",
                flush=True,
            )
    print(
        "플레이스 광고그룹 분류: "
        f"플레이스검색 {sum(value == '플레이스 검색광고' for value in adgroup_category_by_id.values())}개, "
        f"지역소상공인 {sum(value == '지역소상공인 광고' for value in adgroup_category_by_id.values())}개, "
        f"제외 {excluded_place_adgroups}개"
    )
    return daily, matched


def collect_adgroup_catalog(client: NaverSearchAdClient) -> list[dict[str, str]]:
    """Return every reportable ad group with its dashboard category."""
    catalog: list[dict[str, str]] = []
    candidates: list[tuple[dict[str, Any], str, str, bool, str | None]] = []
    for campaign in client.campaigns():
        campaign_id = str(campaign.get("nccCampaignId") or campaign.get("id") or "")
        if not campaign_id:
            continue
        campaign_name = str(campaign.get("name") or campaign.get("campaignName") or "")
        place_campaign = is_place_campaign(campaign)
        campaign_category = classify_campaign(campaign)
        if not place_campaign and not campaign_category:
            continue
        candidates.append(
            (campaign, campaign_id, campaign_name, place_campaign, campaign_category)
        )

    def fetch_campaign_groups(
        candidate: tuple[dict[str, Any], str, str, bool, str | None]
    ) -> list[dict[str, str]]:
        _, campaign_id, campaign_name, place_campaign, campaign_category = candidate
        groups: list[dict[str, str]] = []
        for adgroup in client.adgroups(campaign_id):
            adgroup_id = str(adgroup.get("nccAdgroupId") or adgroup.get("id") or "")
            if not adgroup_id:
                continue
            category = classify_place_adgroup(adgroup) if place_campaign else campaign_category
            if not category:
                continue
            groups.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "adgroup_id": adgroup_id,
                    "adgroup_name": str(
                        adgroup.get("name") or adgroup.get("adgroupName") or ""
                    ),
                    "category": category,
                }
            )
        return groups

    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        for groups in executor.map(fetch_campaign_groups, candidates):
            catalog.extend(groups)
    return catalog


def analysis_record(
    category: str,
    value: str,
    impressions: Any,
    clicks: Any,
    spend: Any,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "category": category,
        "value": value.strip(),
        "impressions": round(number(impressions)),
        "clicks": round(number(clicks)),
        "spend": round(number(spend)),
        **extra,
    }


def aggregate_analysis_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate duplicate terms at advertising-group-type level."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        category = str(row.get("category") or "").strip()
        value = str(row.get("value") or "").strip()
        if not category or not value or value == "-":
            continue
        key = (category, value)
        target = grouped.setdefault(
            key,
            analysis_record(category, value, 0, 0, 0),
        )
        target["impressions"] += round(number(row.get("impressions")))
        target["clicks"] += round(number(row.get("clicks")))
        target["spend"] += round(number(row.get("spend")))
        row_match_types = list(row.get("match_types") or [])
        match_type = str(row.get("match_type") or "").strip()
        if match_type:
            row_match_types.append(match_type)
        for match_type in row_match_types:
            match_type = str(match_type).strip()
            if not match_type:
                continue
            target.setdefault("match_types", [])
            if match_type not in target["match_types"]:
                target["match_types"].append(match_type)
    return sorted(
        grouped.values(),
        key=lambda item: (-item["spend"], -item["clicks"], item["value"]),
    )


def collect_registered_keyword_rows(
    client: NaverSearchAdClient,
    catalog: list[dict[str, str]],
    since: date,
    until: date,
) -> list[dict[str, Any]]:
    keyword_by_id: dict[str, dict[str, Any]] = {}
    for group in catalog:
        try:
            keywords = client.keywords(group["adgroup_id"])
        except IntegrationError as exc:
            print(f"키워드 목록 건너뜀: {group['adgroup_name']} · {exc}")
            continue
        for keyword in keywords:
            keyword_id = str(keyword.get("nccKeywordId") or keyword.get("id") or "")
            value = str(keyword.get("keyword") or keyword.get("name") or "").strip()
            if not keyword_id or not value:
                continue
            keyword_by_id[keyword_id] = analysis_record(
                group["category"], value, 0, 0, 0
            )

    keyword_ids = list(keyword_by_id)
    for start in range(0, len(keyword_ids), STATS_BATCH_SIZE):
        batch = keyword_ids[start : start + STATS_BATCH_SIZE]
        for row in client.summary_stats(batch, since, until):
            keyword_id = str(row.get("id") or row.get("nccKeywordId") or "")
            target = keyword_by_id.get(keyword_id)
            if target:
                target["impressions"] += round(number(row.get("impCnt")))
                target["clicks"] += round(number(row.get("clkCnt")))
                target["spend"] += round(number(row.get("salesAmt")))
        time.sleep(0.2)
    # Keep zero-cost and zero-impression registered keywords so the action
    # board can identify stale keywords instead of hiding them.
    return aggregate_analysis_rows(list(keyword_by_id.values()))


def keyword_window_ranges(report_date: date) -> dict[str, tuple[date, date]]:
    """Return non-overlapping trend and long-term decision ranges."""
    return {
        "7": (report_date - timedelta(days=6), report_date),
        "previous_7": (report_date - timedelta(days=13), report_date - timedelta(days=7)),
        "30": (report_date - timedelta(days=29), report_date),
        "90": (report_date - timedelta(days=89), report_date),
    }


def date_range_chunks(
    since: date, until: date, max_days: int = STATS_MAX_RANGE_DAYS
) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = since
    while current <= until:
        chunk_until = min(current + timedelta(days=max_days - 1), until)
        chunks.append((current, chunk_until))
        current = chunk_until + timedelta(days=1)
    return chunks


def collect_registered_keyword_windows(
    client: NaverSearchAdClient,
    catalog: list[dict[str, str]],
    report_date: date,
) -> dict[str, list[dict[str, Any]]]:
    """Collect all registered keywords once, then request metrics per window."""
    keyword_by_id: dict[str, dict[str, Any]] = {}
    def fetch_group_keywords(group: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
        try:
            keywords = client.keywords(group["adgroup_id"])
        except IntegrationError as exc:
            print(f"키워드 목록 건너뜀: {group['adgroup_name']} · {exc}")
            return []
        result: list[tuple[str, dict[str, Any]]] = []
        for keyword in keywords:
            keyword_id = str(keyword.get("nccKeywordId") or keyword.get("id") or "")
            value = str(keyword.get("keyword") or keyword.get("name") or "").strip()
            if keyword_id and value:
                result.append(
                    (
                        keyword_id,
                        analysis_record(group["category"], value, 0, 0, 0),
                    )
                )
        return result

    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        for group_keywords in executor.map(fetch_group_keywords, catalog):
            for keyword_id, row in group_keywords:
                keyword_by_id[keyword_id] = row
    print(
        f"등록 키워드 목록 완료: 광고그룹 {len(catalog)}개 "
        f"· 키워드 {len(keyword_by_id)}개",
        flush=True,
    )

    result: dict[str, list[dict[str, Any]]] = {}
    keyword_ids = list(keyword_by_id)
    for label, (since, until) in keyword_window_ranges(report_date).items():
        metrics = {keyword_id: dict(row) for keyword_id, row in keyword_by_id.items()}
        requests = [
            (keyword_ids[start : start + STATS_BATCH_SIZE], chunk_since, chunk_until)
            for chunk_since, chunk_until in date_range_chunks(since, until)
            for start in range(0, len(keyword_ids), STATS_BATCH_SIZE)
        ]

        def fetch_keyword_stats(
            request: tuple[list[str], date, date],
        ) -> list[dict[str, Any]]:
            batch, chunk_since, chunk_until = request
            return client.summary_stats(batch, chunk_since, chunk_until)

        with ThreadPoolExecutor(max_workers=KEYWORD_STATS_MAX_WORKERS) as executor:
            for rows in executor.map(fetch_keyword_stats, requests):
                for row in rows:
                    keyword_id = str(row.get("id") or row.get("nccKeywordId") or "")
                    target = metrics.get(keyword_id)
                    if target:
                        target["impressions"] += round(number(row.get("impCnt")))
                        target["clicks"] += round(number(row.get("clkCnt")))
                        target["spend"] += round(number(row.get("salesAmt")))
        result[label] = aggregate_analysis_rows(list(metrics.values()))
        print(
            f"등록 키워드 {label}일 통계 완료: API 요청 {len(requests)}회",
            flush=True,
        )
    return result


def rows_for_date_range(
    days: list[dict[str, Any]], since: date, until: date
) -> list[dict[str, Any]]:
    return aggregate_analysis_rows(
        [
            row
            for day in days
            if isinstance(day, dict)
            and since.isoformat() <= str(day.get("date") or "") <= until.isoformat()
            for row in day.get("rows", [])
            if isinstance(row, dict)
        ]
    )


def attach_metric_windows(
    primary_rows: list[dict[str, Any]],
    window_rows: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Attach available period metrics without inventing unavailable windows."""
    indexes = {
        label: {
            (str(row.get("category") or ""), str(row.get("value") or "")): row
            for row in rows
        }
        for label, rows in window_rows.items()
    }
    result: list[dict[str, Any]] = []
    for primary in primary_rows:
        key = (str(primary.get("category") or ""), str(primary.get("value") or ""))
        windows: dict[str, dict[str, int]] = {}
        for label, index in indexes.items():
            row = index.get(key)
            if row is not None:
                windows[label] = {
                    "impressions": round(number(row.get("impressions"))),
                    "clicks": round(number(row.get("clicks"))),
                    "spend": round(number(row.get("spend"))),
                }
        result.append({**primary, "windows": windows})
    return result


def collect_place_search_term_rows(
    client: NaverSearchAdClient, catalog: list[dict[str, str]]
) -> list[dict[str, Any]]:
    def fetch_group_terms(group: dict[str, str]) -> list[dict[str, Any]]:
        try:
            search_terms = client.place_search_terms(group["adgroup_id"])
        except IntegrationError as exc:
            print(f"플레이스 검색어 건너뜀: {group['adgroup_name']} · {exc}")
            return []
        group_rows: list[dict[str, Any]] = []
        for item in search_terms:
            term = str(item.get("schKeyword") or item.get("searchKeyword") or "").strip()
            if term and term != "-":
                group_rows.append(
                    analysis_record(
                        group["category"],
                        term,
                        item.get("impCnt"),
                        item.get("clkCnt"),
                        item.get("salesAmt"),
                    )
                )
        return group_rows

    rows: list[dict[str, Any]] = []
    place_groups = [group for group in catalog if group["category"] != "파워링크"]
    with ThreadPoolExecutor(max_workers=API_MAX_WORKERS) as executor:
        for group_rows in executor.map(fetch_group_terms, place_groups):
            rows.extend(group_rows)
    return [row for row in aggregate_analysis_rows(rows) if row["spend"] > 0]


def decode_stat_report(content: bytes) -> str:
    if content.startswith(b"\x1f\x8b"):
        content = gzip.decompress(content)
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def normalize_report_download_url(download_url: str) -> str:
    """Safely encode Naver's one-time token and require the current file format."""
    parsed = urlsplit(html.unescape(download_url.strip()))
    query_parts: list[str] = []
    has_file_version = False
    for part in parsed.query.split("&"):
        if not part:
            continue
        key, separator, value = part.partition("=")
        decoded_key = unquote(key)
        has_file_version = has_file_version or decoded_key.lower() == "fileversion"
        encoded_key = quote(decoded_key, safe="")
        encoded_value = quote(unquote(value), safe="") if separator else ""
        query_parts.append(
            f"{encoded_key}={encoded_value}" if separator else encoded_key
        )
    if not has_file_version:
        query_parts.append("fileVersion=v2")
    scheme = "https" if parsed.scheme in {"", "http", "https"} else parsed.scheme
    return urlunsplit(
        (scheme, parsed.netloc, parsed.path, "&".join(query_parts), parsed.fragment)
    )


def parse_expkeyword_report(
    text: str, powerlink_adgroup_ids: set[str], powerlink_campaign_ids: set[str]
) -> list[dict[str, Any]]:
    """Parse Naver's headerless 12-column Powerlink search-term report."""
    rows: list[dict[str, Any]] = []
    match_types = {"0": "일치", "5": "일치", "1": "확장", "2": "유사"}
    for columns in csv.reader(io.StringIO(text), delimiter="\t"):
        if len(columns) < 12:
            continue
        campaign_id, adgroup_id = columns[2].strip(), columns[3].strip()
        if (
            adgroup_id not in powerlink_adgroup_ids
            and campaign_id not in powerlink_campaign_ids
        ):
            continue
        term = columns[4].strip()
        if not term or term == "-":
            continue
        rows.append(
            analysis_record(
                "파워링크",
                term,
                columns[8],
                columns[9],
                columns[10],
                match_type=match_types.get(columns[7].strip(), columns[7].strip()),
            )
        )
    return [row for row in aggregate_analysis_rows(rows) if row["spend"] > 0]


def collect_powerlink_search_term_rows(
    client: NaverSearchAdClient,
    catalog: list[dict[str, str]],
    report_date: date,
) -> list[dict[str, Any]]:
    powerlink_groups = [group for group in catalog if group["category"] == "파워링크"]
    if not powerlink_groups:
        print("파워링크 검색어 보고서: 대상 광고그룹이 없습니다.", flush=True)
        return []
    print(
        f"파워링크 검색어 보고서 생성 요청: {report_date.isoformat()} "
        f"· 광고그룹 {len(powerlink_groups)}개",
        flush=True,
    )
    job = client.create_stat_report("EXPKEYWORD", report_date)
    report_job_id = job.get("reportJobId")
    if not report_job_id:
        raise IntegrationError("EXPKEYWORD 보고서 작업 ID가 없습니다.")

    for _ in range(STAT_REPORT_MAX_POLLS):
        current = client.stat_report(report_job_id)
        status = str(current.get("status") or "").upper()
        download_url = str(current.get("downloadUrl") or "").strip()
        if status == "BUILT" and download_url:
            try:
                request = Request(
                    normalize_report_download_url(download_url),
                    headers={"Accept": "*/*", "User-Agent": "naver-report-dashboard/1.0"},
                )
                with urlopen(request, timeout=60) as response:
                    text = decode_stat_report(response.read())
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace").strip()
                detail = re.sub(
                    r'(?i)(authtoken["\'=:\s]+)[^&"\'\s<]+',
                    r"\1[redacted]",
                    detail,
                )
                if len(detail) > 500:
                    detail = detail[:500] + "…"
                suffix = f" · {detail}" if detail else ""
                raise IntegrationError(
                    f"EXPKEYWORD 보고서 다운로드 실패: HTTP {error.code}{suffix}"
                ) from None
            except (URLError, TimeoutError) as error:
                raise IntegrationError(f"EXPKEYWORD 보고서 다운로드 실패: {error}") from None
            rows = parse_expkeyword_report(
                text,
                {group["adgroup_id"] for group in powerlink_groups},
                {group["campaign_id"] for group in powerlink_groups},
            )
            raw_rows = sum(1 for columns in csv.reader(io.StringIO(text), delimiter="\t") if columns)
            print(
                f"파워링크 검색어 보고서 완료: 원본 {raw_rows}행 "
                f"· 유효 검색어 {len(rows)}개",
                flush=True,
            )
            return rows
        if status in {"ERROR", "NONE"}:
            raise IntegrationError(f"EXPKEYWORD 보고서 생성 실패: {status}")
        time.sleep(STAT_REPORT_POLL_SECONDS)
    raise IntegrationError("EXPKEYWORD 보고서 생성 시간이 초과되었습니다.")


def merge_powerlink_days(
    existing_days: list[dict[str, Any]],
    report_date: date,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cutoff = report_date - timedelta(days=KEYWORD_RETENTION_DAYS - 1)
    merged = [
        item
        for item in existing_days
        if isinstance(item, dict)
        and cutoff.isoformat() <= str(item.get("date") or "") <= report_date.isoformat()
        and str(item.get("date")) != report_date.isoformat()
    ]
    merged.append({"date": report_date.isoformat(), "rows": rows})
    return sorted(merged, key=lambda item: str(item.get("date") or ""))


def build_keyword_analysis_payload(
    client: NaverSearchAdClient,
    report_date: date,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}
    catalog = collect_adgroup_catalog(client)
    since = report_date - timedelta(days=KEYWORD_RETENTION_DAYS - 1)
    keyword_windows = collect_registered_keyword_windows(client, catalog, report_date)
    keywords = attach_metric_windows(keyword_windows["30"], keyword_windows)
    place_terms = collect_place_search_term_rows(client, catalog)

    powerlink_days = list(existing.get("powerlink_days") or [])
    try:
        powerlink_today = collect_powerlink_search_term_rows(client, catalog, report_date)
        powerlink_days = merge_powerlink_days(powerlink_days, report_date, powerlink_today)
    except IntegrationError as exc:
        print(f"파워링크 검색어 보고서 건너뜀: {exc}", flush=True)

    ranges = keyword_window_ranges(report_date)
    powerlink_windows = {
        label: rows_for_date_range(powerlink_days, window_since, window_until)
        for label, (window_since, window_until) in ranges.items()
    }
    search_term_windows = {
        **powerlink_windows,
        "30": aggregate_analysis_rows(place_terms + powerlink_windows["30"]),
    }
    search_terms = attach_metric_windows(search_term_windows["30"], search_term_windows)
    coverage_dates = [str(day.get("date")) for day in powerlink_days if day.get("date")]
    return {
        "schema_version": 2,
        "source": "naver-searchad-api",
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "report_date": report_date.isoformat(),
        "period": {"since": since.isoformat(), "until": report_date.isoformat()},
        "coverage": {
            "keywords": "최근 7일·직전 7일·30일·90일 비교",
            "place_search_terms": "네이버 제공 최근 30일",
            "powerlink_search_terms": (
                f"{coverage_dates[0]} ~ {coverage_dates[-1]} · {len(coverage_dates)}일 누적"
                if coverage_dates
                else "첫 수집 대기"
            ),
        },
        "decision_windows": {
            label: {"since": window_since.isoformat(), "until": window_until.isoformat()}
            for label, (window_since, window_until) in ranges.items()
        },
        "adgroup_counts": {
            category: sum(group["category"] == category for group in catalog)
            for category in CATEGORIES
        },
        "keywords": keywords,
        "search_terms": search_terms,
        "powerlink_days": powerlink_days,
    }


def campaign_rows_for_period(
    daily: dict[date, dict[str, dict[str, Any]]], since: date, until: date
) -> list[dict[str, Any]]:
    totals = {category: blank_metrics(category) for category in CATEGORIES}
    current = since
    while current <= until:
        for category in CATEGORIES:
            add_row(totals[category], {
                "salesAmt": daily[current][category]["spend"],
                "impCnt": daily[current][category]["impressions"],
                "clkCnt": daily[current][category]["clicks"],
            })
        current += timedelta(days=1)
    return [totals[category] for category in CATEGORIES]


def build_dashboard_payload(
    daily: dict[date, dict[str, dict[str, Any]]],
    matched_campaigns: list[dict[str, Any]],
    report_date: date,
) -> dict[str, Any]:
    weeks: list[dict[str, Any]] = []
    current_week_start = report_date - timedelta(days=report_date.weekday())
    for index in range(5):
        since = current_week_start - timedelta(days=index * 7)
        until = since + timedelta(days=6)
        observed_until = min(until, report_date)
        daily_rows = [
            {
                "date": day.isoformat(),
                "available": day <= report_date,
                "campaigns": [
                    daily.get(day, {name: blank_metrics(name) for name in CATEGORIES})[category]
                    for category in CATEGORIES
                ],
            }
            for day in (since + timedelta(days=offset) for offset in range(7))
        ]
        progress = " · 진행 중" if until > report_date else ""
        weeks.append(
            {
                "label": f"{since:%Y.%m.%d} — {until:%m.%d}{progress}",
                "since": since.isoformat(),
                "until": until.isoformat(),
                "observed_until": observed_until.isoformat(),
                "campaigns": campaign_rows_for_period(daily, since, observed_until),
                "daily": daily_rows,
            }
        )

    weekday_names = ("월", "화", "수", "목", "금", "토", "일")
    days = [
        {
            "date": day.isoformat(),
            "label": f"{day:%Y.%m.%d} ({weekday_names[day.weekday()]})",
            "campaigns": [daily[day][category] for category in CATEGORIES],
        }
        for day in sorted(daily, reverse=True)
    ]

    return {
        "schema_version": 1,
        "source": "naver-searchad-api",
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "report_date": report_date.isoformat(),
        "matched_campaign_count": len(matched_campaigns),
        "weeks": weeks,
        "days": days,
        "daily_report": {
            "date": report_date.isoformat(),
            "campaigns": [daily[report_date][category] for category in CATEGORIES],
        },
    }


def calculated(rows: list[dict[str, Any]]) -> dict[str, float]:
    spend = sum(number(row.get("spend")) for row in rows)
    impressions = sum(number(row.get("impressions")) for row in rows)
    clicks = sum(number(row.get("clicks")) for row in rows)
    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": clicks / impressions * 100 if impressions else 0,
        "cpc": spend / clicks if clicks else 0,
    }


def won(value: float) -> str:
    return f"{value:,.0f}원"


def slack_payload(payload: dict[str, Any], dashboard_url: str) -> dict[str, Any]:
    daily = payload["daily_report"]
    rows = daily["campaigns"]
    total = calculated(rows)
    fields = []
    for row in rows:
        metrics = calculated([row])
        fields.append(
            {
                "type": "mrkdwn",
                "text": (
                    f"*{row['name']}*\n"
                    f"광고비 {won(metrics['spend'])} · 클릭 {metrics['clicks']:,.0f}\n"
                    f"CTR {metrics['ctr']:.2f}% · CPC {won(metrics['cpc'])}"
                ),
            }
        )

    return {
        "text": f"택이네조개전골 장현점 바다를품다 광고 리포트 · {daily['date']}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 택이네조개전골 장현점 광고 리포트"},
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"*기준일* {daily['date']} · 전일 확정 데이터"}],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*총 광고비* {won(total['spend'])}\n"
                        f"*노출* {total['impressions']:,.0f} · *클릭* {total['clicks']:,.0f}\n"
                        f"*CTR* {total['ctr']:.2f}% · *평균 CPC* {won(total['cpc'])}"
                    ),
                },
            },
            {"type": "divider"},
            {"type": "section", "fields": fields},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "대시보드 열기"},
                        "url": dashboard_url,
                        "style": "primary",
                    }
                ],
            },
        ],
    }


def send_to_slack(webhook_url: str, payload: dict[str, Any]) -> None:
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or body.strip().lower() != "ok":
                raise IntegrationError(f"Slack 전송 실패: HTTP {response.status}")
    except HTTPError as error:
        raise IntegrationError(f"Slack 전송 실패: HTTP {error.code}") from None
    except (URLError, TimeoutError) as error:
        raise IntegrationError(f"Slack 연결 실패: {error}") from None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_report_date() -> date:
    raw = os.environ.get("REPORT_DATE", "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise IntegrationError("REPORT_DATE는 YYYY-MM-DD 형식이어야 합니다.") from None
    return datetime.now(SEOUL).date() - timedelta(days=1)


def main() -> None:
    client = NaverSearchAdClient(
        customer_id=required_env("NAVER_CUSTOMER_ID"),
        api_key=required_env("NAVER_ACCESS_LICENSE"),
        secret_key=required_env("NAVER_SECRET_KEY"),
    )
    webhook_url = required_env("SLACK_WEBHOOK_URL")
    report_date = parse_report_date()
    dashboard_url = os.environ.get("DASHBOARD_URL", DEFAULT_DASHBOARD_URL).strip()

    daily, matched = collect_daily_metrics(client, report_date)
    dashboard = build_dashboard_payload(daily, matched, report_date)
    send_to_slack(webhook_url, slack_payload(dashboard, dashboard_url))

    existing_keyword_data = read_json(KEYWORD_DATA_PATH)
    try:
        keyword_dashboard = build_keyword_analysis_payload(
            client, report_date, existing_keyword_data
        )
    except IntegrationError as exc:
        keyword_dashboard = existing_keyword_data
        print(f"키워드 분석 갱신 건너뜀: {exc}")

    write_json(DATA_PATH, dashboard)
    if keyword_dashboard:
        write_json(KEYWORD_DATA_PATH, keyword_dashboard)
    generated_at = dashboard["generated_at"]
    write_json(
        CONNECTIONS_PATH,
        {
            "generated_at": generated_at,
            "naver": {
                "connected": True,
                "status": "연결됨",
                "last_sync": generated_at,
                "campaign_count": len(matched),
            },
            "slack": {
                "connected": True,
                "status": "연결됨",
                "last_delivery": generated_at,
                "send_time": "08:30",
            },
        },
    )
    print(
        f"완료: {report_date.isoformat()} · 매칭 캠페인 {len(matched)}개 · "
        "대시보드·키워드 JSON 갱신 및 Slack 전송"
    )


if __name__ == "__main__":
    main()
