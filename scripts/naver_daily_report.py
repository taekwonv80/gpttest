#!/usr/bin/env python3
"""Collect Naver SearchAd metrics and send a daily Slack report.

Only aggregate advertising metrics are written to the public ``data`` folder.
Credentials are read from environment variables and are never persisted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_URL = "https://api.searchad.naver.com"
SEOUL = ZoneInfo("Asia/Seoul")
CATEGORIES = ("플레이스 검색광고", "지역소상공인 광고", "파워링크")
FIELDS = ("impCnt", "clkCnt", "salesAmt", "ctr", "cpc")
DATA_PATH = Path("data/campaign_weekly.json")
CONNECTIONS_PATH = Path("data/connections.json")
DEFAULT_DASHBOARD_URL = "https://eklove.pages.dev"
STATS_BATCH_SIZE = 100


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

    def campaigns(self) -> list[dict[str, Any]]:
        result = self.get("/ncc/campaigns")
        if not isinstance(result, list):
            raise IntegrationError("네이버 캠페인 응답 형식이 예상과 다릅니다.")
        return [item for item in result if isinstance(item, dict)]

    def summary_stats(
        self, campaign_ids: list[str], since: date, until: date
    ) -> list[dict[str, Any]]:
        result = self.get(
            "/stats",
            {
                "ids": campaign_ids,
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

    if "PLACE" in campaign_type or "플레이스" in name:
        return "플레이스 검색광고"
    if (
        campaign_type == "6"
        or "LOCAL" in campaign_type
        or "SMB" in campaign_type
        or "소상공인" in name
    ):
        return "지역소상공인 광고"
    if (
        campaign_type in {"1", "WEB_SITE", "WEBSITE"}
        or "파워링크" in name
        or "사이트검색" in name
    ):
        return "파워링크"
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
    category_by_id: dict[str, str] = {}
    for campaign in campaigns:
        category = classify_campaign(campaign)
        campaign_id = str(campaign.get("nccCampaignId") or campaign.get("id") or "")
        if not category or not campaign_id:
            continue
        matched.append(campaign)
        category_by_id[campaign_id] = category

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

    campaign_ids = list(category_by_id)
    batches = [
        campaign_ids[start : start + STATS_BATCH_SIZE]
        for start in range(0, len(campaign_ids), STATS_BATCH_SIZE)
    ]
    for target_day in sorted(daily):
        for batch in batches:
            try:
                rows = client.summary_stats(batch, target_day, target_day)
            except IntegrationError as exc:
                raise IntegrationError(
                    f"{target_day.isoformat()} 캠페인 통계 묶음 조회 실패: {exc}"
                ) from None
            for row in rows:
                campaign_id = str(row.get("id") or row.get("nccCampaignId") or "")
                category = category_by_id.get(campaign_id)
                if category:
                    add_row(daily[target_day][category], row)
            time.sleep(0.2)
        print(
            f"네이버 통계 수집: {target_day.isoformat()} "
            f"({len(campaign_ids)}개 캠페인, {len(batches)}개 묶음)"
        )
    return daily, matched


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

    write_json(DATA_PATH, dashboard)
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
        "대시보드 JSON 갱신 및 Slack 전송"
    )


if __name__ == "__main__":
    main()
