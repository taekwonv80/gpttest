from __future__ import annotations

import unittest

from dashboard_math import infer_ratio_counts


class DashboardMathTests(unittest.TestCase):
    def test_infers_place_channel_counts(self) -> None:
        ratios = {
            "네이버지도": 40.98,
            "네이버검색": 30.12,
            "인스타그램": 11.77,
            "네이버 플레이스광고": 11.62,
            "웹사이트": 5.50,
        }
        self.assertEqual(
            infer_ratio_counts(ratios),
            {
                "네이버지도": 268,
                "네이버검색": 197,
                "인스타그램": 77,
                "네이버 플레이스광고": 76,
                "웹사이트": 36,
            },
        )

    def test_infers_place_keyword_counts(self) -> None:
        ratios = {
            "택이네조개전골": 74.51,
            "맛집": 6.86,
            "택이네조개전골장현": 6.86,
            "시흥장현맛집": 5.88,
            "장현동맛집": 5.88,
        }
        self.assertEqual(
            infer_ratio_counts(ratios),
            {
                "택이네조개전골": 76,
                "맛집": 7,
                "택이네조개전골장현": 7,
                "시흥장현맛집": 6,
                "장현동맛집": 6,
            },
        )

    def test_rejects_incomplete_distribution(self) -> None:
        self.assertEqual(infer_ratio_counts({"네이버지도": 40.98}), {})


if __name__ == "__main__":
    unittest.main()
