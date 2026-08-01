from __future__ import annotations

import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "naver_daily_report.py"
SPEC = importlib.util.spec_from_file_location("naver_daily_report", MODULE_PATH)
report = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(report)


class ReportTests(unittest.TestCase):
    def test_signature_is_stable(self) -> None:
        self.assertEqual(
            report.signature("1700000000000", "GET", "/stats", "secret"),
            "dSmwhFWokbdwBl/uE6S6gXwJnOJpri7T5DFhYjePHJU=",
        )

    def test_campaign_classification(self) -> None:
        self.assertEqual(
            report.classify_campaign({"campaignTp": "PLACE", "name": "매장"}),
            "플레이스 검색광고",
        )
        self.assertEqual(
            report.classify_campaign({"campaignTp": 6, "name": "지역 홍보"}),
            "지역소상공인 광고",
        )
        self.assertEqual(
            report.classify_campaign({"campaignTp": "WEB_SITE", "name": "브랜드"}),
            "파워링크",
        )

    def test_dashboard_payload_has_five_selectable_weeks(self) -> None:
        report_date = date(2026, 7, 31)
        since = report_date - timedelta(days=34)
        daily = {}
        for offset in range(35):
            day = since + timedelta(days=offset)
            daily[day] = {
                name: {
                    "name": name,
                    "spend": 100 + offset,
                    "impressions": 1000,
                    "clicks": 25,
                }
                for name in report.CATEGORIES
            }

        payload = report.build_dashboard_payload(
            daily,
            [{"nccCampaignId": "cmp-test", "campaignTp": "PLACE"}],
            report_date,
        )
        self.assertEqual(len(payload["weeks"]), 5)
        self.assertEqual(payload["weeks"][0]["label"], "2026.07.27 — 08.02 · 진행 중")
        self.assertEqual(payload["weeks"][0]["since"], "2026-07-27")
        self.assertEqual(payload["weeks"][0]["until"], "2026-08-02")
        self.assertEqual(payload["daily_report"]["date"], "2026-07-31")
        self.assertEqual(len(payload["weeks"][0]["daily"]), 7)
        self.assertEqual(payload["days"][0]["label"], "2026.07.31 (금)")

    def test_summary_stats_uses_supported_bulk_summary_request(self) -> None:
        captured = {}

        class RecordingClient(report.NaverSearchAdClient):
            def get(self, uri, params=None):
                captured["uri"] = uri
                captured["params"] = params
                return {
                    "summaryStatResponse": {
                        "data": [
                            {"id": "cmp-test", "impCnt": 100, "clkCnt": 5, "salesAmt": 1000}
                        ]
                    }
                }

        client = RecordingClient("1", "api", "secret")
        rows = client.summary_stats(
            ["cmp-test", "cmp-other"], date(2026, 7, 31), date(2026, 7, 31)
        )

        self.assertEqual(captured["uri"], "/stats")
        self.assertEqual(captured["params"]["ids"], ["cmp-test", "cmp-other"])
        self.assertNotIn("id", captured["params"])
        self.assertEqual(captured["params"]["timeIncrement"], "allDays")
        self.assertEqual(rows[0]["clkCnt"], 5)

    def test_query_string_repeats_bulk_ids(self) -> None:
        self.assertEqual(
            report.query_string({"ids": ["cmp-one", "cmp-two"], "timeIncrement": "allDays"}),
            "ids=cmp-one&ids=cmp-two&timeIncrement=allDays",
        )

    def test_collect_daily_metrics_batches_campaigns_by_day(self) -> None:
        class BatchClient:
            calls = []

            def campaigns(self):
                return [
                    {"nccCampaignId": "place", "campaignTp": "PLACE", "name": "매장"},
                    {"nccCampaignId": "power", "campaignTp": "WEB_SITE", "name": "검색"},
                ]

            def summary_stats(self, campaign_ids, since, until):
                self.calls.append((campaign_ids, since, until))
                return [
                    {"id": "place", "impCnt": 100, "clkCnt": 10, "salesAmt": 1000},
                    {"id": "power", "impCnt": 200, "clkCnt": 20, "salesAmt": 3000},
                ]

        client = BatchClient()
        daily, matched = report.collect_daily_metrics(client, date(2026, 7, 31), weeks=1)

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(client.calls[0][0], ["place", "power"])
        self.assertEqual(len(matched), 2)
        self.assertEqual(daily[date(2026, 7, 31)]["플레이스 검색광고"]["clicks"], 10)
        self.assertEqual(daily[date(2026, 7, 31)]["파워링크"]["spend"], 3000)


if __name__ == "__main__":
    unittest.main()
