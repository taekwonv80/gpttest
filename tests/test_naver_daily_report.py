from __future__ import annotations

import importlib.util
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


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

    def test_keywords_are_requested_for_an_adgroup(self) -> None:
        captured = {}

        class RecordingClient(report.NaverSearchAdClient):
            def get(self, uri, params=None):
                captured["uri"] = uri
                captured["params"] = params
                return [{"nccKeywordId": "kw-test", "keyword": "장현동 맛집"}]

        keywords = RecordingClient("1", "api", "secret").keywords("group-test")

        self.assertEqual(captured["uri"], "/ncc/keywords")
        self.assertEqual(captured["params"]["nccAdgroupId"], "group-test")
        self.assertEqual(keywords[0]["keyword"], "장현동 맛집")

    def test_registered_keyword_collection_keeps_zero_activity_rows(self) -> None:
        class KeywordClient:
            def keywords(self, adgroup_id):
                return [{"nccKeywordId": "kw-stale", "keyword": "오래된 키워드"}]

            def summary_stats(self, entity_ids, since, until):
                return []

        rows = report.collect_registered_keyword_rows(
            KeywordClient(),
            [{"adgroup_id": "group-test", "category": "파워링크", "adgroup_name": "테스트"}],
            date(2026, 7, 1),
            date(2026, 7, 30),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "오래된 키워드")
        self.assertEqual(rows[0]["impressions"], 0)

    def test_registered_keyword_windows_fetch_catalog_once(self) -> None:
        class WindowClient:
            def __init__(self):
                self.keyword_calls = 0
                self.stat_ranges = []

            def keywords(self, adgroup_id):
                self.keyword_calls += 1
                return [{"nccKeywordId": "kw-one", "keyword": "장현동 맛집"}]

            def summary_stats(self, entity_ids, since, until):
                self.stat_ranges.append((since, until))
                days = (until - since).days + 1
                return [{"id": "kw-one", "impCnt": days * 10, "clkCnt": days, "salesAmt": days * 100}]

        client = WindowClient()
        with patch.object(report.time, "sleep"):
            windows = report.collect_registered_keyword_windows(
                client,
                [{"adgroup_id": "group-test", "category": "파워링크", "adgroup_name": "테스트"}],
                date(2026, 8, 2),
            )

        self.assertEqual(client.keyword_calls, 1)
        self.assertEqual(len(client.stat_ranges), 6)
        self.assertTrue(all((until - since).days < 30 for since, until in client.stat_ranges))
        self.assertEqual(windows["7"][0]["impressions"], 70)
        self.assertEqual(windows["90"][0]["clicks"], 90)

    def test_place_search_terms_use_npla_stat_type(self) -> None:
        captured = {}

        class RecordingClient(report.NaverSearchAdClient):
            def get(self, uri, params=None):
                captured["uri"] = uri
                captured["params"] = params
                return [{"schKeyword": "조개전골", "impCnt": 10}]

        rows = RecordingClient("1", "api", "secret").place_search_terms("group-test")

        self.assertEqual(captured["uri"], "/stats")
        self.assertEqual(captured["params"]["id"], "group-test")
        self.assertEqual(captured["params"]["statType"], "NPLA_SCH_KEYWORD")
        self.assertEqual(rows[0]["schKeyword"], "조개전골")

    def test_expkeyword_report_is_parsed_and_duplicate_terms_are_aggregated(self) -> None:
        text = "\n".join(
            [
                "20260801\t1\tcmp-power\tgrp-power\t장현동 맛집\t123\tM\t1\t100\t5\t1000\t0",
                "20260801\t1\tcmp-power\tgrp-power\t장현동 맛집\t123\tP\t0\t50\t2\t300\t0",
                "20260801\t1\tcmp-power\tgrp-power\t-\t123\tP\t0\t20\t1\t100\t0",
                "20260801\t1\tcmp-other\tgrp-other\t제외\t123\tP\t0\t20\t1\t100\t0",
            ]
        )

        rows = report.parse_expkeyword_report(
            text, {"grp-power"}, {"cmp-power"}
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "장현동 맛집")
        self.assertEqual(rows[0]["impressions"], 150)
        self.assertEqual(rows[0]["clicks"], 7)
        self.assertEqual(rows[0]["spend"], 1300)
        self.assertEqual(rows[0]["match_types"], ["확장", "일치"])

    def test_report_download_url_encodes_token_and_requires_v2(self) -> None:
        normalized = report.normalize_report_download_url(
            "http://api.searchad.naver.com/report-download?authtoken=a+b/c&amp;other=1"
        )

        self.assertEqual(
            normalized,
            "https://api.searchad.naver.com/report-download?"
            "authtoken=a%2Bb%2Fc&other=1&fileVersion=v2",
        )

    def test_powerlink_search_term_days_keep_latest_ninety_days(self) -> None:
        existing = [
            {"date": "2026-07-02", "rows": []},
            {"date": "2026-07-04", "rows": [{"value": "기존"}]},
            {"date": "2026-08-02", "rows": [{"value": "교체"}]},
        ]
        rows = [{"value": "신규", "category": "파워링크", "spend": 100}]

        merged = report.merge_powerlink_days(existing, date(2026, 8, 2), rows)

        self.assertEqual(
            [item["date"] for item in merged],
            ["2026-07-02", "2026-07-04", "2026-08-02"],
        )
        self.assertEqual(merged[-1]["rows"][0]["value"], "신규")

    def test_keyword_windows_include_trend_primary_and_long_term_ranges(self) -> None:
        ranges = report.keyword_window_ranges(date(2026, 8, 2))

        self.assertEqual(ranges["7"], (date(2026, 7, 27), date(2026, 8, 2)))
        self.assertEqual(ranges["previous_7"], (date(2026, 7, 20), date(2026, 7, 26)))
        self.assertEqual(ranges["30"][0], date(2026, 7, 4))
        self.assertEqual(ranges["90"][0], date(2026, 5, 5))

    def test_metric_windows_do_not_invent_unavailable_periods(self) -> None:
        primary = [
            {"category": "플레이스 검색광고", "value": "맛집", "impressions": 30, "clicks": 2, "spend": 200}
        ]
        attached = report.attach_metric_windows(primary, {"30": primary, "7": []})

        self.assertIn("30", attached[0]["windows"])
        self.assertNotIn("7", attached[0]["windows"])

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
