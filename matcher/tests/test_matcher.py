from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from matcher.dedupe import deduplicate
from matcher.engine import MatchEngine
from matcher.matching import score_job
from matcher.models import Job
from matcher.providers.boss import BossProvider
from matcher.providers.company import CompanyCareersProvider
from matcher.providers.importer import ImportProvider
from matcher.providers.nowcoder import NowcoderProvider
from matcher.providers.offershow import OfferShowProvider
from matcher.providers.shixiseng import ShixisengProvider
from matcher.query import build_queries
from matcher.storage import save_run


def profile(employment_types=None):
    return {
        "profile_id": "profile-123456789abc",
        "career": {"career_stage": "student", "highest_degree": "硕士", "experience_months": 11},
        "target": {
            "employment_types": employment_types or ["full_time"],
            "primary_roles": ["大模型算法工程师（后训练 / RLHF 方向）"],
            "secondary_roles": [],
            "preferred_locations": ["深圳"],
            "acceptable_locations": ["北京"],
            "preferred_industries": [],
            "excluded_industries": [],
            "salary": {"monthly_min_cny": None},
        },
        "capabilities": {
            "skills": [
                {"name": "Python", "proficiency": "advanced"},
                {"name": "RLHF", "proficiency": "advanced"},
                {"name": "DeepSpeed", "proficiency": "intermediate"},
            ]
        },
        "constraints": {"deal_breakers": []},
        "matching_config": {
            "must_have_keywords": [],
            "nice_to_have_keywords": [],
            "excluded_keywords": [],
            "weights": {},
        },
    }


class MatcherTests(unittest.TestCase):
    def test_queries_are_derived_from_profile(self):
        queries = build_queries(profile())
        self.assertEqual(queries[0], "大模型算法工程师")
        self.assertTrue(any("大模型" in query for query in queries))

    def test_score_explains_role_skill_and_location(self):
        job = Job(
            source="test",
            source_job_id="1",
            title="大模型算法工程师",
            company="示例公司",
            locations=["深圳"],
            requirements="熟悉 Python、RLHF 和 DeepSpeed，本科及以上",
            education="本科",
            employment_type="campus",
        )
        result = score_job(profile(), job)
        self.assertGreaterEqual(result.total, 80)
        self.assertIn("Python", result.matched_skills)
        self.assertTrue(result.hard_constraints_passed)
        self.assertTrue(result.reasons)

    def test_deduplicate_keeps_richer_cross_source_record(self):
        one = Job(source="a", source_job_id="1", title="算法工程师", company="甲", locations=["深圳"])
        two = Job(
            source="b", source_job_id="2", title="算法工程师", company="甲", locations=["深圳"], description="完整描述"
        )
        result = deduplicate([one, two])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].description, "完整描述")

    def test_shixiseng_parser_and_profile_skip(self):
        page = '''<div data-intern-id="inn_1" class="intern-wrap intern-item">
        <div class="intern-detail__job"><a href="https://www.shixiseng.com/intern/inn_1" title="大模型算法">大模型算法</a>
        <span class="city ellipsis">深圳</span></div>
        <div class="intern-detail__company"><a title="示例科技">示例科技</a></div>
        <span class="intern-label">可转正实习</span></div>'''
        jobs = ShixisengProvider()._parse(page)
        self.assertEqual(jobs[0].company, "示例科技")
        self.assertEqual(jobs[0].locations, ["深圳"])
        skipped = ShixisengProvider().collect(profile(["full_time"]), ["算法"])
        self.assertEqual(skipped.status, "skipped")

    @patch("matcher.providers.nowcoder.request_json")
    def test_nowcoder_provider_normalizes_public_response(self, request_json):
        request_json.return_value = {
            "code": 0,
            "data": {
                "datas": [
                    {
                        "data": {
                            "id": 7,
                            "jobName": "大模型算法工程师",
                            "jobCityList": ["深圳"],
                            "jobKeys": "Python,RLHF",
                            "eduLevel": 5000,
                            "salaryMin": 25,
                            "salaryMax": 50,
                            "ext": json.dumps({"requirements": "熟悉 Python 和 RLHF", "infos": "训练大模型"}),
                            "recommendInternCompany": {"companyName": "示例公司", "industryTagNameList": ["人工智能"]},
                        }
                    }
                ]
            },
        }
        result = NowcoderProvider(max_jobs=10).collect(profile(), ["大模型算法工程师"])
        self.assertEqual(result.status, "success")
        self.assertEqual(result.jobs[0].company, "示例公司")
        self.assertEqual(result.jobs[0].employment_type, "campus")
        self.assertEqual(result.jobs[0].salary_min, 25000)
        self.assertEqual(result.jobs[0].experience, "应届生")

    @patch("matcher.providers.offershow.request_json")
    def test_offershow_splits_recruitment_plan_positions(self, request_json):
        request_json.return_value = {
            "code": 200001,
            "data": {
                "data": [
                    {
                        "uuid": "plan-1",
                        "title": "示例公司2027校园招聘",
                        "company_name": "示例公司",
                        "city": "深圳 | 北京",
                        "positions": "大模型算法工程师\n财务专员",
                        "notice_url": "https://example.com/jobs",
                        "end_time": "20261231",
                    }
                ]
            },
        }
        result = OfferShowProvider(max_jobs=10).collect(profile(), ["大模型算法工程师"])
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].title, "大模型算法工程师")
        self.assertEqual(result.jobs[0].application_url, "https://example.com/jobs")

    @patch("matcher.providers.boss.request_json")
    def test_boss_environment_check_is_reported_not_bypassed(self, request_json):
        request_json.return_value = {"code": 37, "message": "您的环境存在异常"}
        result = BossProvider().collect(profile(), ["大模型算法工程师"])
        self.assertEqual(result.status, "needs_browser")
        self.assertEqual(result.jobs, [])
        self.assertTrue(result.discovery_urls)

    @patch("matcher.providers.company.request_text")
    def test_company_jsonld_provider(self, request_text):
        request_text.return_value = '''<script type="application/ld+json">{
          "@type":"JobPosting","identifier":{"value":"abc"},"title":"大模型算法工程师",
          "hiringOrganization":{"name":"某科技"},"jobLocation":{"address":{"addressLocality":"深圳"}},
          "description":"需要 Python","url":"/jobs/abc"
        }</script>'''
        result = CompanyCareersProvider(["https://example.com/careers"]).collect(profile(), ["大模型"])
        self.assertEqual(result.jobs[0].url, "https://example.com/jobs/abc")

    def test_offline_import_engine_and_three_output_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            imported = root / "jobs.csv"
            with imported.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["职位", "公司", "地点", "岗位要求", "投递链接"])
                writer.writeheader()
                writer.writerow(
                    {"职位": "大模型算法工程师", "公司": "示例公司", "地点": "深圳", "岗位要求": "Python RLHF", "投递链接": "https://example.com/apply"}
                )
            run = MatchEngine([ImportProvider([imported])]).run(profile())
            output = save_run(run, root / "outputs")
            self.assertTrue((output / "jobs.json").exists())
            self.assertTrue((output / "jobs.csv").exists())
            self.assertTrue((output / "jobs.md").exists())
            self.assertEqual(run.jobs[0].job.title, "大模型算法工程师")


if __name__ == "__main__":
    unittest.main()
