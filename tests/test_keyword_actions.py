from __future__ import annotations

import unittest

from scripts.keyword_actions import build_action_plan, intent, recommend


class KeywordActionTests(unittest.TestCase):
    def test_irrelevant_search_term_is_excluded(self) -> None:
        row = {"value": "조개전골 레시피", "category": "파워링크", "impressions": 300, "clicks": 4, "spend": 500}
        result = recommend(row, source="실제 검색어", cohort_ctr=1.0, cohort_cpc=120)
        self.assertEqual(result["action"], "제외")
        self.assertEqual(result["intent"], "무관 의도")

    def test_zero_impression_registered_keyword_is_paused(self) -> None:
        row = {"value": "오래된 키워드", "category": "파워링크", "impressions": 0, "clicks": 0, "spend": 0}
        result = recommend(row, source="등록 키워드", cohort_ctr=1.0, cohort_cpc=120)
        self.assertEqual(result["action"], "중지")

    def test_high_intent_low_ctr_is_improved_not_removed(self) -> None:
        row = {"value": "장현동 조개전골", "category": "파워링크", "impressions": 1000, "clicks": 2, "spend": 300}
        result = recommend(row, source="등록 키워드", cohort_ctr=1.0, cohort_cpc=120)
        self.assertEqual(result["action"], "개선")

    def test_strong_keyword_is_expansion_candidate(self) -> None:
        row = {"value": "시흥 조개전골", "category": "파워링크", "impressions": 1000, "clicks": 25, "spend": 2500}
        result = recommend(row, source="등록 키워드", cohort_ctr=1.0, cohort_cpc=120)
        self.assertEqual(result["action"], "확대")

    def test_small_sample_stays_in_observation(self) -> None:
        row = {"value": "장현동 회식", "category": "파워링크", "impressions": 90, "clicks": 3, "spend": 300}
        result = recommend(row, source="등록 키워드", cohort_ctr=1.0, cohort_cpc=120)
        self.assertEqual(result["action"], "유지")
        self.assertEqual(result["confidence"], "낮음")

    def test_plan_is_sorted_by_priority(self) -> None:
        rows = [
            {"value": "일반 키워드", "category": "파워링크", "impressions": 80, "clicks": 1, "spend": 100},
            {"value": "조개전골 밀키트", "category": "파워링크", "impressions": 500, "clicks": 10, "spend": 1500},
        ]
        plan = build_action_plan(rows, "실제 검색어")
        self.assertEqual(plan[0]["action"], "제외")
        self.assertEqual(intent("택이네 조개전골"), "브랜드")


if __name__ == "__main__":
    unittest.main()
