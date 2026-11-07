import unittest

from app.learning import build_recommendations, score_post


class LearningTests(unittest.TestCase):
    def test_score_is_zero_without_engagement(self):
        self.assertEqual(score_post({"reach": 100, "views": 100}), 0.0)

    def test_score_uses_reach_denominator(self):
        score = score_post({"reach": 100, "likes": 10, "comments": 2, "saves": 4, "shares": 3, "follows": 1})
        self.assertGreater(score, 0)

    def test_requires_three_measured_posts(self):
        result = build_recommendations([{"measured_at": "today", "category": "A", "format": "webtoon", "metrics": {"reach": 100}}] * 2)
        self.assertEqual(result["status"], "collecting_data")

    def test_builds_recommendation_after_three_posts(self):
        rows = []
        for idx in range(3):
            rows.append({
                "title": f"post {idx}", "category": "디지털 생활", "format": "webtoon_carousel",
                "measured_at": "today",
                "metrics": {"reach": 100, "views": 120, "likes": 10, "comments": 2, "shares": 5, "saves": 8, "follows": 2},
            })
        result = build_recommendations(rows)
        self.assertEqual(result["status"], "learning")
        self.assertTrue(result["rankings"])


if __name__ == "__main__":
    unittest.main()
