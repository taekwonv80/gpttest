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
        self.assertIsNone(
            report.classify_campaign({"campaignTp": "PLACE", "name": "매장"})
        )
        self.assertEqual(
            report.classify_campaign({"campaignTp": "WEB_SITE", "name": "브랜드"}),
            "파워링크",
        )

    def test_place_adgroups_are_classified_by_official_type(self) -> None:
        self.assertEqual(
            report.classify_place_adgroup(
                {"adgroupType": "PLACE", "name": "플레이스검색 이름"}
            ),
            "지역소상공인 광고",
        )
        self.assertEqual(
            report.classify_place_adgroup(
                {"adgroupType": "LOCAL_AD", "name": "지역소상공인 이름"}
            ),
            "플레이스 검색광고",
        )
        self.assertIsNone(
            report.classify_place_adgroup({"adgroupType": "DOOH", "name": "플레이스검색"})
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

    def test_adgroups_are_requested_for_the_place_campaign(self) -> None:
        captured = {}

        class RecordingClient(report.NaverSearchAdClient):
            def get(self, uri, params=None):
                captured["uri"] = uri
                captured["params"] = params
                return [{"nccAdgroupId": "group-test", "adgroupType": "LOCAL_AD"}]

        groups = RecordingClient("1", "api", "secret").adgroups("campaign-test")

        self.assertEqual(captured["uri"], "/ncc/adgroups")
        self.assertEqual(captured["params"]["nccCampaignId"], "campaign-test")
        self.assertEqual(captured["params"]["recordSize"], 1000)
        self.assertEqual(groups[0]["adgroupType"], "LOCAL_AD")

    def test_query_string_repeats_bulk_ids(self) -> None:
        self.assertEqual(
            report.query_string({"ids": ["cmp-one", "cmp-two"], "timeIncrement": "allDays"}),
            "ids=cmp-one&ids=cmp-two&timeIncrement=allDays",
        )

    def test_collect_daily_metrics_uses_place_adgroups_and_excludes_dooh(self) -> None:
        class BatchClient:
            def __init__(self):
                self.calls = []

            def campaigns(self):
                return [
                    {"nccCampaignId": "place", "campaignTp": "PLACE", "name": "매장"},
                    {"nccCampaignId": "power", "campaignTp": "WEB_SITE", "name": "검색"},
                ]

            def adgroups(self, campaign_id):
                self.assert_campaign_id = campaign_id
                return [
                    {"nccAdgroupId": "local-smb", "adgroupType": "PLACE"},
                    {"nccAdgroupId": "place-search", "adgroupType": "LOCAL_AD"},
                    {"nccAdgroupId": "outdoor", "adgroupType": "DOOH"},
                ]

            def summary_stats(self, entity_ids, since, until):
                self.calls.append((entity_ids, since, until))
                stats = {
                    "local-smb": {"impCnt": 100, "clkCnt": 10, "salesAmt": 1000},
                    "place-search": {"impCnt": 300, "clkCnt": 3, "salesAmt": 5000},
                    "power": {"impCnt": 200, "clkCnt": 20, "salesAmt": 3000},
                }
                return [{"id": entity_id, **stats[entity_id]} for entity_id in entity_ids]

        client = BatchClient()
        daily, matched = report.collect_daily_metrics(client, date(2026, 7, 31), weeks=1)

        self.assertEqual(len(client.calls), 10)
        self.assertEqual(client.calls[0][0], ["local-smb", "place-search"])
        self.assertEqual(client.calls[1][0], ["power"])
        self.assertTrue(all("outdoor" not in call[0] for call in client.calls))
        self.assertEqual(len(matched), 2)
        self.assertEqual(daily[date(2026, 7, 31)]["플레이스 검색광고"]["spend"], 5000)
        self.assertEqual(daily[date(2026, 7, 31)]["지역소상공인 광고"]["clicks"], 10)
        self.assertEqual(daily[date(2026, 7, 31)]["파워링크"]["spend"], 3000)


if __name__ == "__main__":
    unittest.main()
