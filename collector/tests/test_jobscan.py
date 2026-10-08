import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jobscan", ROOT / "jobscan.py")
jobscan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(jobscan)


class JobScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = jobscan.load_config(ROOT / "config.json")

    def test_salary_monthly_with_months(self):
        result = jobscan.normalize_salary("30-40K × 15薪")
        self.assertEqual(result["salary_min_monthly"], 30000)
        self.assertEqual(result["salary_max_monthly"], 40000)
        self.assertEqual(result["salary_months"], 15)

    def test_salary_annual(self):
        result = jobscan.normalize_salary("年薪42-60万元/年")
        self.assertEqual(result["salary_min_monthly"], 35000)
        self.assertEqual(result["salary_max_monthly"], 50000)

    def test_salary_daily_is_not_monthly(self):
        result = jobscan.normalize_salary("实习补贴200-300元/天")
        self.assertEqual(result["salary_daily"], 250)
        self.assertIsNone(result["salary_min_monthly"])

    def test_schema_full_time_is_normalized(self):
        self.assertEqual(jobscan.infer_employment("FULL_TIME"), "全职/社招")

    def test_robots_timeout_fails_open_and_is_cached(self):
        fetcher = jobscan.Fetcher(self.config)
        session = Mock()
        session.headers = {"User-Agent": "test-agent"}
        session.get.side_effect = jobscan.requests.Timeout("timed out")
        fetcher.session = session

        first = fetcher.allowed("https://example.com/jobs/1")
        second = fetcher.allowed("https://example.com/jobs/2")

        self.assertEqual(first, (True, "robots_unavailable"))
        self.assertEqual(second, (True, "robots_unavailable"))
        session.get.assert_called_once_with(
            "https://example.com/robots.txt",
            timeout=self.config["request"]["timeout_seconds"],
            allow_redirects=True,
        )

    def test_classification(self):
        category, scores = jobscan.classify(
            "使用 Isaac Sim 和 MuJoCo 构建机器人仿真任务并生成合成数据",
            self.config["categories"],
        )
        self.assertEqual(category, "机器人仿真/合成数据")
        self.assertGreater(scores[category], 1)

    def test_specific_category_beats_generic_algorithm_label(self):
        category, _ = jobscan.classify(
            "机器人导航算法工程师，负责路径规划、轨迹规划、MPC控制算法与机器人运动学",
            self.config["categories"],
        )
        self.assertEqual(category, "机器人控制/VLA")

    def test_biased_small_sample_does_not_claim_competition(self):
        jobs = [{"employment_type": "校招", "experience": "应届", "education": "硕士", "company": "A"}]
        label, _ = jobscan.pressure_proxy(jobs)
        self.assertEqual(label, "不可估计")

    def test_jsonld_job_parsing(self):
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "仿真与数据合成工程师",
            "hiringOrganization": {"name": "示例机器人"},
            "jobLocation": {"address": {"addressLocality": "深圳"}},
            "datePosted": "2026-09-01",
            "employmentType": "校招",
            "description": "负责Isaac Sim机器人仿真，要求硕士，30-40K·15薪，Python C++。",
        }
        body = f'<html><script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script></html>'
        result = jobscan.parse_job_page("https://example.com/job/1", body, self.config)
        self.assertEqual(result["company"], "示例机器人")
        self.assertEqual(result["location"], "深圳")
        self.assertEqual(result["category"], "机器人仿真/合成数据")
        self.assertIn("Python", result["skills"])

    def test_canonical_url_drops_tracking(self):
        left = jobscan.canonical_url("https://example.com/job/1?utm_source=x&id=2")
        right = jobscan.canonical_url("https://example.com/job/1?id=2&utm_source=y")
        self.assertEqual(left, right)

    def test_nowcoder_company_from_title(self):
        body = """<html><head><title>仿真与数据合成工程师_戴盟（深圳）机器人科技有限公司校招_牛客网</title>
        <meta name="description" content="深圳 机器人仿真 Isaac Sim，硕士，30-40K"></head><body>招聘</body></html>"""
        result = jobscan.parse_job_page("https://www.nowcoder.com/jobs/detail/1", body, self.config)
        self.assertEqual(result["company"], "戴盟（深圳）机器人科技有限公司")

    def test_explicit_location_beats_company_name(self):
        body = """<html><head><title>算法工程师_深圳示例公司校招</title>
        <meta name="description" content="工作地点：北京，负责机器人算法。"></head><body>招聘</body></html>"""
        result = jobscan.parse_job_page("https://www.nowcoder.com/jobs/detail/2", body, self.config)
        self.assertEqual(result["location"], "北京")

    def test_source_tiers(self):
        self.assertEqual(jobscan.source_tier("career.huawei.com", self.config), "公司官方")
        self.assertEqual(jobscan.source_tier("www.unitree.com", self.config), "公司官方")
        self.assertEqual(jobscan.source_tier("www.nowcoder.com", self.config), "招聘平台")
        self.assertEqual(jobscan.source_tier("career.example.edu.cn", self.config), "高校转发")

    def test_display_title_removes_platform_suffix(self):
        title = "仿真与数据合成工程师_戴盟机器人校招_牛客网"
        self.assertEqual(jobscan.display_job_title(title), "仿真与数据合成工程师")

    def test_fallback_rejects_result_outside_site_query(self):
        item = {
            "query": "site:fourierintelligence.com careers robotics",
            "url": "https://jobs.bytedance.com/campus/position/1/detail",
            "title": "机器人算法工程师招聘",
            "description": "负责 VLA 和强化学习",
        }
        self.assertFalse(jobscan.discovery_fallback_relevant(item, self.config))

    def test_fallback_requires_job_and_direction_in_result(self):
        relevant = {
            "query": "机器人算法招聘",
            "url": "https://www.nowcoder.com/jobs/detail/1",
            "title": "机器人仿真工程师招聘",
            "description": "使用 Isaac Sim 生成合成数据",
        }
        noise = {
            "query": "机器人算法招聘",
            "url": "https://www.zhaopin.com/",
            "title": "招聘官网",
            "description": "找工作上招聘网",
        }
        self.assertTrue(jobscan.discovery_fallback_relevant(relevant, self.config))
        self.assertFalse(jobscan.discovery_fallback_relevant(noise, self.config))



    def test_dji_hot_jobs_listing_splits_official_cards(self):
        body = """
        <div class="pc_card__abc" role="link">
          <div><h4><a href="https://apply.careers.dji.com/jobs#a">世界模型算法工程师</a></h4>
          <div><span class="pc_tag__x">深圳</span><span class="pc_tag__x">上海</span></div>
          <p class="pc_intro__x">负责3DGS、数字孪生与强化学习仿真。</p></div>
        </div>
        <div class="pc_card__abc" role="link">
          <div><h4><a href="https://apply.careers.dji.com/jobs#b">数据闭环与自动标注算法工程师</a></h4>
          <div><span class="pc_tag__x">深圳</span></div>
          <p class="pc_intro__x">负责数据闭环、数据质量和自动标注。</p></div>
        </div>
        """
        jobs = jobscan.parse_dji_hot_jobs(body, self.config)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["company"], "大疆创新")
        self.assertEqual(jobs[0]["source_domain"], "careers.dji.com")
        self.assertIn("深圳", jobs[0]["location"])
        self.assertNotEqual(jobs[0]["id"], jobs[1]["id"])

    def test_config_registers_dji_listing_adapter(self):
        listings = self.config.get("listing_sources", [])
        self.assertIn("dji_hot_jobs", {item["type"] for item in listings})
        self.assertTrue(any("careers.dji.com" in item["url"] for item in listings))

    def test_unitree_listing_extracts_role_and_full_duties(self):
        body = """
        <a href="/position/robot-data-engineer" class="link">
          <div><p class="title">具身智能数据工程师 <span>HOT</span></p>
          <p class="base-info">杭州市 | 技术类 | 研发部</p>
          <div class="duty"><p>负责机器人数据采集、清洗和数据闭环。</p>
          <p>熟悉 Python、Linux，有强化学习或模仿学习经验者优先。</p></div></div>
        </a>
        """
        jobs = jobscan.parse_unitree_positions(body, self.config)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "宇树科技")
        self.assertEqual(jobs[0]["location"], "杭州")
        self.assertIn("数据采集", jobs[0]["description_excerpt"])
        self.assertEqual(jobs[0]["source_domain"], "www.unitree.com")

    def test_job_insights_explain_capabilities_and_generated_questions(self):
        job = {
            "title": "机器人仿真与数据闭环工程师",
            "category": "机器人仿真/合成数据",
            "skills": ["Python", "Isaac Sim", "强化学习"],
            "description_excerpt": (
                "负责使用 Isaac Sim 构建机器人仿真与数据闭环。"
                "要求熟悉 Python、Linux 与强化学习，硕士优先。"
            ),
        }
        result = jobscan.job_insights(job, self.config)
        self.assertTrue(result["responsibilities"])
        self.assertTrue(result["requirements"])
        self.assertTrue(result["capabilityGroups"])
        self.assertTrue(all(item["basis"].startswith("岗位信号：") for item in result["interviewPrep"]))

    def test_company_registry_has_direct_career_links(self):
        companies = jobscan.load_company_registry(ROOT / "config.json", self.config)
        self.assertGreaterEqual(len(companies), 25)
        self.assertTrue(all(item.get("careerUrl", "").startswith("https://") for item in companies))
        self.assertIn("宇树科技", {item["name"] for item in companies})

    def test_missing_requirements_are_not_called_low_barrier(self):
        job = {
            "title": "具身智能算法实习生",
            "description_excerpt": "负责机器人策略学习",
            "employment_type": "实习",
            "education": "未注明",
            "experience": "未注明",
        }
        barrier, friendliness, basis = jobscan.entry_barrier(job, self.config)
        self.assertEqual(barrier, "不可判断")
        self.assertEqual(friendliness, 40)
        self.assertIn("学历与经验要求未完整披露", basis)

    def test_explicit_bachelor_internship_is_direct_priority(self):
        job = {
            "title": "机器人仿真开发实习生",
            "description_excerpt": "使用 Isaac Sim 生成机器人合成数据，本科可投",
            "employment_type": "实习",
            "education": "本科",
            "experience": "经验不限",
            "company": "示例机器人",
            "category": "机器人仿真/合成数据",
        }
        result = jobscan.job_priority(job, self.config, 70, "招聘平台")
        self.assertEqual(result["entryBarrier"], "低")
        self.assertEqual(result["priorityTier"], "P0")
        self.assertEqual(result["priorityLabel"], "具身实习/校招")

    def test_phd_requirement_stays_high_barrier_despite_high_match(self):
        job = {
            "title": "具身智能研究员",
            "description_excerpt": "负责 VLA 研究，要求博士学历",
            "employment_type": "校招",
            "education": "博士",
            "experience": "应届",
            "company": "示例机器人",
            "category": "机器人控制/VLA",
        }
        result = jobscan.job_priority(job, self.config, 92, "公司官方")
        self.assertEqual(result["entryBarrier"], "高")
        self.assertEqual(result["priorityTier"], "P3")

    def test_big_tech_adjacent_junior_role_is_priority_two(self):
        config = {
            **self.config,
            "job_priority": {
                **self.config["job_priority"],
                "big_tech_companies": ["腾讯"],
            },
        }
        job = {
            "title": "AI 模型评测工程师",
            "description_excerpt": "负责模型评测与自动化测试，1-2年经验",
            "employment_type": "全职/社招",
            "education": "本科",
            "experience": "1-2年",
            "company": "腾讯",
            "category": "测试开发/模型评测",
        }
        result = jobscan.job_priority(job, config, 66, "公司官方")
        self.assertEqual(result["entryBarrier"], "中")
        self.assertEqual(result["priorityTier"], "P2")
        self.assertTrue(result["isBigTech"])

    def test_generic_data_role_is_not_mislabeled_as_embodied(self):
        job = {
            "title": "后端研发工程师 - 自变量机器人科技招聘",
            "description_excerpt": "负责 Go、SQL 报表和数据仓库",
            "employment_type": "实习",
            "education": "本科",
            "experience": "经验不限",
            "company": "示例公司",
            "category": "数据工程/数据闭环",
        }
        result = jobscan.job_priority(job, self.config, 60, "招聘平台")
        self.assertEqual(result["priorityTier"], "P3")
if __name__ == "__main__":
    unittest.main()
