from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import intel_scan


class IntelScanTests(unittest.TestCase):
    def test_social_results_are_filtered_and_deduplicated(self):
        config = {
            "request": {
                "timeout_seconds": 1,
                "delay_seconds": 0,
                "max_results_per_query": 10,
                "respect_robots_txt": True,
                "user_agent": "test",
            },
            "social": {
                "queries": ["q1", "q2"],
                "allowed_domains": ["xiaohongshu.com"],
                "max_items": 10,
            },
        }

        def fake_discover(fetcher, query, limit):
            return [
                {
                    "url": "https://www.xiaohongshu.com/explore/abc?utm_source=test",
                    "title": "机器人求职",
                    "description": "公开搜索摘要",
                    "query": query,
                },
                {
                    "url": "https://example.com/not-allowed",
                    "title": "不允许",
                    "description": "",
                    "query": query,
                },
            ]

        items, health = intel_scan.indexed_candidates(
            "social", config, discover=fake_discover
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(len(health), 2)
        self.assertEqual(sum(row["accepted"] for row in health), 2)

    def test_social_results_require_career_and_embodied_signals(self):
        section = {
            "relevance": {
                "employment_keywords": ["招聘", "面试"],
                "embodied_keywords": ["机器人", "VLA"],
            }
        }
        self.assertTrue(intel_scan.social_relevant({
            "title": "机器人算法招聘",
            "description": "深圳校招",
            "url": "https://x.com/example/status/1",
        }, section))
        self.assertFalse(intel_scan.social_relevant({
            "title": "汉语词典：机器人",
            "description": "解释与造句",
            "url": "https://www.xiaohongshu.com/explore/noise",
        }, section))
        self.assertFalse(intel_scan.social_relevant({
            "title": "通用软件工程师招聘",
            "description": "普通互联网岗位",
            "url": "https://x.com/example/status/2",
        }, section))

    def test_social_results_allow_embodied_release_signals(self):
        section = {
            "watched_accounts": ["Figure_robot"],
            "relevance": {
                "employment_keywords": ["招聘"],
                "embodied_keywords": ["机器人", "VLA"],
                "trend_keywords": ["发布", "开源"],
            },
        }
        self.assertTrue(intel_scan.social_relevant({
            "title": "Figure 发布新的 VLA 机器人演示",
            "description": "公开摘要",
            "url": "https://x.com/Figure_robot/status/3",
        }, section))
        self.assertFalse(intel_scan.social_relevant({
            "title": "普通手机新品发布",
            "description": "公开摘要",
            "url": "https://x.com/example/status/4",
        }, section))

    def test_signal_classification_and_platform(self):
        self.assertEqual(intel_scan.signal_type("机器人算法内推，团队正在招人"), "招人/内推")
        self.assertEqual(intel_scan.signal_type("人形机器人面经复盘"), "面试经验")
        self.assertEqual(intel_scan.platform_for_url("https://x.com/a/status/1"), "X")
        self.assertEqual(intel_scan.platform_for_url("https://www.xiaohongshu.com/explore/a"), "小红书")

    def test_search_shortcuts_are_direct_links_not_signals(self):
        shortcuts = intel_scan.build_search_shortcuts({"search_shortcuts": [
            {"platform": "X", "label": "X 招聘", "query": "机器人 招聘"},
            {"platform": "小红书", "label": "小红书面试", "query": "机器人面试"},
        ]})
        self.assertEqual(len(shortcuts), 2)
        self.assertIn("x.com/search", shortcuts[0]["url"])
        self.assertIn("xiaohongshu.com/search_result", shortcuts[1]["url"])

    def test_release_changes_are_cleaned_and_limited(self):
        changes = intel_scan.release_key_changes("""
## What's Changed
- Added dataset recording support for two cameras.
- [Fixed dependency resolution](https://example.com/change) for training.
- Breaking migration for the policy configuration.
- A fourth change that should not be returned.
""")
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes[0], "Added dataset recording support for two cameras.")
        self.assertNotIn("https://", changes[1])
        self.assertEqual(intel_scan.clean_release_line("- **example:** add g1_audio_client"), "example: add g1_audio_client")

    def test_github_event_separates_source_facts_from_rule_based_guidance(self):
        item = intel_scan.event_details({
            "title": "LeRobot v0.7.0",
            "excerpt": "Breaking migration for policy training and dataset recording.",
            "keyChanges": ["Breaking migration for policy training."],
            "domain": "github.com",
            "company": "Hugging Face",
            "project": "LeRobot",
            "version": "v0.7.0",
        })
        self.assertEqual(item["eventType"], "开源版本")
        self.assertEqual(item["whatHappened"], "Hugging Face 发布 LeRobot v0.7.0。")
        self.assertIn("数据与采集", item["affectedAreas"])
        self.assertIn("训练与策略", item["affectedAreas"])
        self.assertIn("兼容性", item["affectedAreas"])
        self.assertIn("破坏性变更", item["suggestedAction"])
        self.assertIn("规则提炼", item["interpretation"])

    def test_github_page_without_version_is_an_open_source_project(self):
        item = intel_scan.event_details({
            "title": "Open X-Humanoid",
            "excerpt": "A public humanoid robot project page.",
            "domain": "github.com",
        })
        self.assertEqual(item["eventType"], "开源项目")
        self.assertEqual(item["project"], "Open X-Humanoid")
        self.assertNotIn("新版本", item["whatHappened"])


    def test_source_tiers_are_explicit(self):
        self.assertEqual(
            intel_scan.source_tier("social", "xiaohongshu.com"),
            "社媒搜索线索",
        )
        self.assertEqual(
            intel_scan.source_tier("events", "arxiv.org"),
            "研究发布",
        )
        self.assertEqual(
            intel_scan.source_tier("events", "unitree.com"),
            "公司官方",
        )


if __name__ == "__main__":
    unittest.main()
