import importlib.util
import datetime as dt
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("feishu_notify", ROOT / "feishu_notify.py")
feishu_notify = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(feishu_notify)


class FeishuNotifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = feishu_notify.jobscan.load_config(ROOT / "config.json")

    def test_validate_webhook_accepts_expected_feishu_url(self):
        value = "https://open.feishu.cn/open-apis/bot/v2/hook/example-id"
        self.assertEqual(feishu_notify.validate_webhook(value), value)

    def test_validate_webhook_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            feishu_notify.validate_webhook(
                "https://example.com/open-apis/bot/v2/hook/example-id"
            )

    def test_card_contains_keyword_and_original_job_link(self):
        jobs = [{
            "id": "job-1",
            "title": "机器人仿真工程师",
            "company": "示例机器人",
            "location": "深圳",
            "employment_type": "校招",
            "source_domain": "career.huawei.com",
            "url": "https://career.example/job/1",
            "skills": ["Python", "Isaac Sim"],
            "category": "机器人仿真/合成数据",
            "experience": "应届",
            "education": "硕士",
        }]
        card = feishu_notify.build_card(
            "2026-09-14", jobs, 10, True, self.config
        )
        rendered = str(card)
        self.assertIn(feishu_notify.REQUIRED_KEYWORD, rendered)
        self.assertIn("https://career.example/job/1", rendered)
        self.assertIn("新增岗位", rendered)
        self.assertEqual(card["msg_type"], "interactive")

    def test_empty_delta_is_explicit(self):
        card = feishu_notify.build_card(
            "2026-09-14", [], 10, True, self.config
        )
        self.assertIn("没有发现新增岗位", str(card))

    def test_job_card_explains_priority_and_entry_barrier(self):
        jobs = [{
            "id": "job-1",
            "title": "机器人仿真开发实习生",
            "company": "示例机器人",
            "location": "深圳",
            "employment_type": "实习",
            "source_domain": "career.huawei.com",
            "url": "https://career.example/job/1",
            "skills": ["Python", "Isaac Sim"],
            "category": "机器人仿真/合成数据",
            "experience": "经验不限",
            "education": "本科",
            "description_excerpt": "使用 Isaac Sim 生成机器人合成数据",
        }]
        rendered = str(feishu_notify.build_card(
            "2026-09-14", jobs, 10, True, self.config
        ))
        self.assertIn("具身实习/校招", rendered)
        self.assertIn("入门门槛", rendered)
        self.assertIn("岗位优先分", rendered)

    def test_rank_jobs_puts_friendly_direct_role_before_high_barrier_role(self):
        friendly = {
            "id": "friendly",
            "title": "机器人仿真实习生",
            "company": "示例机器人",
            "location": "深圳",
            "employment_type": "实习",
            "source_domain": "www.nowcoder.com",
            "url": "https://example.com/friendly",
            "skills": ["Python"],
            "category": "机器人仿真/合成数据",
            "experience": "经验不限",
            "education": "本科",
            "description_excerpt": "机器人仿真与合成数据",
        }
        high_barrier = {
            "id": "high",
            "title": "具身智能资深研究员",
            "company": "示例机器人",
            "location": "深圳",
            "employment_type": "校招",
            "source_domain": "career.huawei.com",
            "url": "https://example.com/high",
            "skills": ["Python", "C++", "VLA", "强化学习", "模仿学习"],
            "category": "机器人控制/VLA",
            "experience": "应届",
            "education": "博士",
            "description_excerpt": "要求博士，负责 VLA 与强化学习",
        }
        ranked = feishu_notify.rank_jobs([high_barrier, friendly], self.config)
        self.assertEqual(ranked[0]["id"], "friendly")
        self.assertEqual(ranked[1]["entryBarrier"], "高")

    def test_card_only_adds_supplied_high_value_social(self):
        card = feishu_notify.build_card(
            "2026-09-14", [], 10, True, self.config, social_items=[{
                "platform": "X",
                "signalType": "招人/内推",
                "title": "机器人团队招人",
                "company": "示例机器人",
                "url": "https://x.com/example/status/1",
            }]
        )
        rendered = str(card)
        self.assertIn("高价值就业线索", rendered)
        self.assertIn("https://x.com/example/status/1", rendered)
        self.assertIn("不是已核验岗位", rendered)



    def test_digest_changes_when_card_content_changes(self):
        first = {"msg_type": "interactive", "card": {"title": "A"}}
        second = {"msg_type": "interactive", "card": {"title": "B"}}
        self.assertEqual(
            feishu_notify.card_digest(first),
            feishu_notify.card_digest(dict(first)),
        )
        self.assertNotEqual(
            feishu_notify.card_digest(first),
            feishu_notify.card_digest(second),
        )

    def test_social_content_digest_ignores_refresh_timestamp(self):
        first = [{
            "id": "signal-1",
            "url": "https://x.com/example/status/1",
            "title": "机器人发布",
            "topic": "开源、论文与产品",
            "score": 70,
            "priority": "中",
            "supportCount": 1,
            "discoveredAt": "2026-09-15T00:00:00+00:00",
        }]
        second = [dict(first[0], discoveredAt="2026-09-15T06:00:00+00:00")]
        self.assertEqual(
            feishu_notify.social_content_digest(first, []),
            feishu_notify.social_content_digest(second, []),
        )

    def test_urgent_alert_requires_two_source_support(self):
        settings = {
            "timezone": "Asia/Shanghai",
            "digest_hour": 20,
            "min_digest_score": 60,
            "urgent_score": 85,
            "urgent_min_support": 2,
            "max_items": 5,
            "max_predictions": 3,
        }
        item = {
            "id": "signal-1",
            "url": "https://x.com/example/status/1",
            "score": 90,
            "supportCount": 1,
            "topic": "VLA与策略学习",
        }
        mode, selected, _, _ = feishu_notify.select_social_notification(
            [item], [], {}, settings,
            dt.datetime(2026, 9, 15, 10, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(mode, "")
        self.assertEqual(selected, [])
        item["supportCount"] = 2
        mode, selected, _, _ = feishu_notify.select_social_notification(
            [item], [], {}, settings,
            dt.datetime(2026, 9, 15, 10, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(mode, "urgent")
        self.assertEqual(selected[0]["id"], "signal-1")

    def test_digest_is_once_per_shanghai_day_after_eight_pm(self):
        settings = {
            "timezone": "Asia/Shanghai",
            "digest_hour": 20,
            "min_digest_score": 60,
            "urgent_score": 85,
            "urgent_min_support": 2,
            "max_items": 5,
            "max_predictions": 3,
        }
        item = {
            "id": "signal-1",
            "url": "https://x.com/example/status/1",
            "score": 70,
            "supportCount": 1,
        }
        now = dt.datetime(2026, 9, 15, 12, tzinfo=dt.timezone.utc)
        mode, _, _, local_day = feishu_notify.select_social_notification(
            [item], [], {}, settings, now
        )
        self.assertEqual(mode, "digest")
        mode, _, _, _ = feishu_notify.select_social_notification(
            [item], [], {"last_social_digest_date": local_day}, settings, now
        )
        self.assertEqual(mode, "")
if __name__ == "__main__":
    unittest.main()
