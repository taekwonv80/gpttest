import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "naver_place_rank_collector.py"
SPEC = importlib.util.spec_from_file_location("naver_place_rank_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class NaverPlaceRankCollectorTests(unittest.TestCase):
    def test_find_rank_keeps_first_visible_matching_result(self):
        cards = [
            "다른 식당\n한식",
            "택이네조개전골 장현지구점x바다를품다 시흥플랑드르근처\n조개요리",
            "택이네조개전골 장현지구점x바다를품다 시흥플랑드르근처\n광고",
        ]
        result = collector.find_rank(cards, ["택이네조개전골 장현지구점"])
        self.assertEqual(result["rank"], 2)
        self.assertFalse(result["is_ad"])

    def test_history_appends_measurement(self):
        history = {"schema_version": 1, "measurements": []}
        measurement = {
            "keyword": "장현동맛집",
            "measured_at": "2026-10-05T09:15:00+09:00",
            "rank": 8,
        }
        saved = collector.append_history(history, [measurement], "1827896507")
        self.assertEqual(saved["place_id"], "1827896507")
        self.assertEqual(saved["measurements"][0]["rank"], 8)


if __name__ == "__main__":
    unittest.main()
