from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "naver_place_collector.py"
SPEC = importlib.util.spec_from_file_location("naver_place_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(collector)


SAMPLE = """
방문 전 지표
플레이스 유입 703회 전주 956회
예약·주문 신청 3회 전주 12회
스마트콜 통화 11회 전주 20회
방문 후 지표
리뷰 등록 7회 전주 7회
유입채널
네이버지도 268회
네이버검색 197회
네이버 블로그 51회
인스타그램 77회
페이스북 42회
네이버 플레이스광고 76회
네이버 지역소상공인광고 31회
네이버톡톡 9회
웹사이트 36회
유입키워드
1 시흥 조개전골 35회
2 장현동 맛집 21회
한 주간 리뷰
"""

RESERVATION_SAMPLE = """
예약 통계
예약 페이지 유입 82회
예약 신청 14건
예약 취소 2건
이용 완료 9건
유입경로
네이버 검색 51회
네이버 지도 19회
플레이스 광고 12회
유입트렌드
"""

SMARTCALL_SAMPLE = """
스마트콜 통계
통화 연결 18회
부재중 전화 3회
"""

REVIEW_SAMPLE = """
리뷰 통계
신규 리뷰 7건
방문자 리뷰
"""

ACTUAL_LABEL_SAMPLE = """
플레이스 상세페이지 유입 수
703
리뷰 등록 수 7건
누적 통화 연결 11회
"""

PLACE_RATIO_SAMPLE = """
유입 채널
1 네이버지도 40.98%
2 네이버검색 30.12%
3 인스타그램 11.77%
유입 키워드
1 장현동 맛집 52.25%
2 시흥 조개전골 25.50%
한 주간 리뷰
"""


class CollectorTests(unittest.TestCase):
    def test_place_channel_and_keyword_ratios(self) -> None:
        channels = collector.parse_channels(PLACE_RATIO_SAMPLE)
        keywords = collector.parse_keywords(PLACE_RATIO_SAMPLE)
        self.assertEqual(channels["네이버지도"], 40.98)
        self.assertEqual(channels["네이버검색"], 30.12)
        self.assertEqual(keywords["장현동 맛집"], 52.25)

    def test_place_sales_card_label(self) -> None:
        metrics = collector.parse_summary_metrics("유입 수·매출액 703회")
        self.assertEqual(metrics["place_visits_weekly"], 703)

    def test_actual_smartplace_metric_labels(self) -> None:
        metrics = collector.parse_summary_metrics(ACTUAL_LABEL_SAMPLE)
        self.assertEqual(metrics["place_visits_weekly"], 703)
        self.assertEqual(metrics["smartcall_weekly"], 11)
        self.assertEqual(metrics["reviews_weekly"], 7)

    def test_report_can_supply_place_visits_when_place_tab_has_no_card(self) -> None:
        place_only = "유입채널\n네이버 검색\n197\n유입키워드\n"
        row = collector.parse_rendered_text(
            place_only, date(2026, 8, 2), require_place_visits=False
        )
        collector.merge_present(row, collector.parse_summary_metrics(ACTUAL_LABEL_SAMPLE))
        self.assertEqual(row["place_visits_weekly"], 703)
        self.assertEqual(collector.parse_channels(place_only)["네이버 검색"], 197)

    def test_statistics_url_moves_to_current_monday(self) -> None:
        url = (
            "https://new.smartplace.naver.com/bizes/place/1/statistics?"
            "menu=reports&startDate=2026-07-01&endDate=2026-07-07&term=weekly"
        )
        moved = collector.current_week_url(url, date(2026, 8, 2))
        self.assertIn("startDate=2026-07-27", moved)
        self.assertIn("endDate=2026-08-02", moved)
        self.assertIn("menu=reports", moved)

    def test_smartcall_subdomain_is_allowed(self) -> None:
        self.assertTrue(
            collector.is_smartplace_url(
                "https://smartcall.smartplace.naver.com/statistics/1"
            )
        )
        self.assertFalse(collector.is_smartplace_url("https://example.com/statistics"))

    def test_parse_screenshot_text(self) -> None:
        row = collector.parse_rendered_text(SAMPLE, date(2026, 8, 1))
        self.assertEqual(row["week_start"], "2026-07-27")
        self.assertEqual(row["place_visits_weekly"], 703)
        self.assertEqual(row["booking_orders_weekly"], 3)
        self.assertEqual(row["naver_map_weekly"], 268)
        self.assertEqual(row["facebook_weekly"], 42)
        self.assertEqual(row["naver_blog_weekly"], 51)
        self.assertEqual(row["local_smb_ads_weekly"], 31)
        self.assertEqual(row["naver_talktalk_weekly"], 9)
        self.assertEqual(
            collector.parse_channels(SAMPLE)["네이버 플레이스광고"], 76
        )
        self.assertIn('"페이스북":42', row["channels_json"])
        self.assertIn('"시흥 조개전골":35', row["keywords_json"])

    def test_parse_reservation_statistics(self) -> None:
        row = collector.parse_reservation_text(RESERVATION_SAMPLE)
        self.assertEqual(row["reservation_inflows_weekly"], 82)
        self.assertEqual(row["reservation_applications_weekly"], 14)
        self.assertEqual(row["reservation_cancellations_weekly"], 2)
        self.assertEqual(row["reservation_completions_weekly"], 9)
        self.assertIn('"네이버 검색":51', row["reservation_channels_json"])

    def test_parse_smartcall_and_review_tabs(self) -> None:
        self.assertEqual(
            collector.parse_smartcall_text(SMARTCALL_SAMPLE)["smartcall_weekly"], 18
        )
        self.assertEqual(collector.parse_review_text(REVIEW_SAMPLE)["reviews_weekly"], 7)

    def test_merge_present_does_not_erase_valid_values(self) -> None:
        row = {"smartcall_weekly": 11, "channels_json": '{"네이버지도":10}'}
        collector.merge_present(row, {"smartcall_weekly": "", "channels_json": "{}"})
        self.assertEqual(row["smartcall_weekly"], 11)
        self.assertEqual(row["channels_json"], '{"네이버지도":10}')

    def test_daily_delta_uses_previous_cumulative_total(self) -> None:
        row = collector.parse_rendered_text(SAMPLE, date(2026, 8, 1))
        previous = {
            "week_start": "2026-07-27",
            "place_visits_weekly": "600",
            "booking_orders_weekly": "2",
            "smartcall_weekly": "9",
            "reviews_weekly": "6",
            "reservation_inflows_weekly": "70",
            "reservation_applications_weekly": "10",
            "reservation_cancellations_weekly": "1",
            "reservation_completions_weekly": "8",
        }
        row.update(collector.parse_reservation_text(RESERVATION_SAMPLE))
        collector.add_daily_deltas(row, previous)
        self.assertEqual(row["place_visits_daily_delta"], 103)
        self.assertEqual(row["smartcall_daily_delta"], 2)
        self.assertEqual(row["reservation_inflows_daily_delta"], 12)
        self.assertEqual(row["reservation_applications_daily_delta"], 4)

    def test_upsert_replaces_same_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily.csv"
            first = collector.parse_rendered_text(SAMPLE, date(2026, 8, 1))
            collector.upsert_row(first, path)
            changed = dict(first, place_visits_weekly=710)
            collector.upsert_row(changed, path)
            rows = collector.load_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["place_visits_weekly"], "710")


if __name__ == "__main__":
    unittest.main()
