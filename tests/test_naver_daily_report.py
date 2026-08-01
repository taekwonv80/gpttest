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
        self.assertEqual(payload["weeks"][0]["label"], "2026.07.25 — 07.31")
        self.assertEqual(payload["daily_report"]["date"], "2026-07-31")
        self.assertEqual(len(payload["weeks"][0]["daily"]), 7)


if __name__ == "__main__":
    unittest.main()
