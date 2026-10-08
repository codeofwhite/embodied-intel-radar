from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import social_rank


class SocialRankTests(unittest.TestCase):
    def setUp(self):
        self.section = {
            "watched_accounts": ["Figure_robot", "1x_tech"],
            "relevance": {
                "embodied_keywords": ["robotics", "humanoid", "VLA", "robot learning"],
                "employment_keywords": ["hiring"],
                "trend_keywords": ["release", "open source", "benchmark"],
            },
        }

    def test_watched_new_signal_gets_auditable_score(self):
        item = {
            "id": "one",
            "url": "https://x.com/Figure_robot/status/1",
            "title": "Humanoid robotics VLA robot learning open source release benchmark",
            "excerpt": "",
            "verification": "search_index_only",
            "domain": "x.com",
        }
        ranked = social_rank.score_items([item], [], self.section)
        self.assertEqual(ranked[0]["account"], "figure_robot")
        self.assertEqual(ranked[0]["priority"], "高")
        self.assertIn("精选观察账号", " ".join(ranked[0]["scoreReasons"]))
        self.assertIn("待核实", " ".join(ranked[0]["scoreReasons"]))

    def test_two_accounts_raise_forecast_confidence_but_not_to_high(self):
        items = [
            {
                "id": "one",
                "url": "https://x.com/Figure_robot/status/1",
                "title": "VLA robot learning policy robotics release",
                "excerpt": "",
                "verification": "search_index_only",
                "domain": "x.com",
            },
            {
                "id": "two",
                "url": "https://x.com/1x_tech/status/2",
                "title": "VLA robot learning policy robotics benchmark",
                "excerpt": "",
                "verification": "search_index_only",
                "domain": "x.com",
            },
        ]
        ranked = social_rank.score_items(items, [], self.section)
        self.assertEqual({item["supportCount"] for item in ranked}, {2})
        prediction = social_rank.build_predictions(ranked)[0]
        self.assertEqual(prediction["confidence"], "中")
        self.assertEqual(prediction["sourceCount"], 2)
        self.assertIn("撤销", prediction["invalidation"])

    def test_history_deduplicates_and_counts_observations(self):
        first = {"id": "one", "url": "https://x.com/a/status/1", "title": "A"}
        payload = social_rank.merge_history([], [first], "2026-09-15T00:00:00+00:00")
        payload = social_rank.merge_history(
            payload["items"], [first], "2026-09-15T06:00:00+00:00"
        )
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["seenCount"], 2)
        self.assertEqual(payload["items"][0]["firstSeenAt"], "2026-09-15T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
