from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from matcher.dedupe import deduplicate
from matcher.company_catalog import CompanyCatalog, CompanyTarget
from matcher.engine import MatchEngine
from matcher.matching import score_job
from matcher.models import Job, ProviderResult
from matcher.providers.base import Provider
from matcher.providers.boss import BossProvider
from matcher.providers.browser_official import BrowserOfficialProvider
from matcher.providers.company import CompanyCareersProvider, CompanyCatalogProvider
from matcher.providers.importer import ImportProvider
from matcher.providers.nowcoder import NowcoderMajorCompanyProvider, NowcoderProvider
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
    def test_browser_official_provider_builds_traceable_bytedance_and_meituan_jobs(self):
        provider = BrowserOfficialProvider()
        bytedance = provider._bytedance_job(
            "机器学习平台研发工程师\n北京、深圳\n正式\n研发 - 后端\n2027届校园招聘\n职位 ID：A100\n负责机器学习平台",
            "/campus/position/7670812949539883317/detail",
        )
        meituan = provider._meituan_job(
            "4721378720",
            "商业分析实习生（大模型应用BP）",
            ["日常实习", "北京市", "更新于2026/08/27", "核心本地商业-美团平台"],
            ["参与大模型服务质量标准制定"],
        )
        self.assertEqual(bytedance.company, "字节跳动")
        self.assertEqual(bytedance.application_source, "official")
        self.assertIn("7670812949539883317", bytedance.application_url)
        self.assertEqual(meituan.company, "美团")
        self.assertEqual(meituan.employment_type, "internship")
        self.assertIn("4721378720", meituan.application_url)

    @patch("matcher.providers.nowcoder.request_json")
    def test_major_company_fallback_queries_each_company_and_keeps_source_honest(self, request_json):
        request_json.side_effect = [
            {"code": 0, "data": {"datas": []}},
            {
                "code": 0,
                "data": {"datas": [{"data": {"id": 9, "jobName": "大模型算法工程师", "recommendInternCompany": {"companyName": "字节跳动"}}}]},
            },
        ]
        catalog = CompanyCatalog([
            CompanyTarget("腾讯", "major", ("https://join.qq.com",), ()),
            CompanyTarget("字节跳动", "major", ("https://jobs.bytedance.com",), ()),
        ])
        result = NowcoderMajorCompanyProvider(catalog, max_jobs=20).collect(profile(), ["大模型算法工程师"])
        self.assertEqual(request_json.call_count, 2)
        self.assertEqual(result.jobs[0].company, "字节跳动")
        self.assertEqual(result.jobs[0].source, "nowcoder_company_search")
        self.assertEqual(result.jobs[0].application_source, "public_platform")

    def test_ranked_results_are_diversified_across_companies_before_repeating(self):
        class Concentrated(Provider):
            name = "concentrated"

            def collect(self, profile, queries):
                jobs = [
                    Job(
                        source=self.name,
                        source_job_id=str(index),
                        title=f"大模型算法工程师 {index}",
                        company="甲公司" if index < 4 else "乙公司" if index == 4 else "丙公司",
                        requirements="Python RLHF DeepSpeed",
                    )
                    for index in range(6)
                ]
                return ProviderResult(source=self.name, status="success", jobs=jobs)

        run = MatchEngine([Concentrated()]).run(profile(), limit=3)
        self.assertEqual({item.job.company for item in run.jobs}, {"甲公司", "乙公司", "丙公司"})

    def test_official_candidates_are_collected_first_and_win_cross_source_deduplication(self):
        calls: list[str] = []

        class Official(Provider):
            name = "official"
            priority = 10
            source_kind = "official"

            def collect(self, profile, queries):
                calls.append(self.name)
                return ProviderResult(
                    source=self.name,
                    status="success",
                    jobs=[Job(source=self.name, source_job_id="official-1", title="大模型算法工程师", company="腾讯", locations=["深圳"], application_url="https://join.qq.com/job/1")],
                )

        class Platform(Provider):
            name = "platform"
            priority = 40

            def collect(self, profile, queries):
                calls.append(self.name)
                return ProviderResult(
                    source=self.name,
                    status="success",
                    jobs=[Job(source=self.name, source_job_id="platform-1", title="大模型算法工程师", company="腾讯科技", locations=["深圳"], description="更长的平台描述", application_url="https://example.com/job/1")],
                )

        catalog = CompanyCatalog([CompanyTarget("腾讯", "major", ("https://join.qq.com",), ("腾讯科技",))])
        run = MatchEngine([Platform(), Official()], company_catalog=catalog).run(profile())
        self.assertEqual(calls, ["official", "platform"])
        self.assertEqual(len(run.jobs), 1)
        self.assertEqual(run.jobs[0].job.source_kind, "official")
        self.assertEqual(run.jobs[0].job.application_url, "https://join.qq.com/job/1")
        self.assertEqual(run.jobs[0].job.application_source, "official")
        self.assertEqual(run.coverage["planned_companies"], 1)
        self.assertEqual(run.coverage["companies_with_jobs"], 1)

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

    def test_company_provider_parses_conservative_ssr_initial_data(self):
        page = '''<script>window.__INITIAL_DATA__ = {"listData":{"listDetailData":[{
          "name":"北京-大模型算法工程师(J100728)","postId":"post-1","jobId":"job-1",
          "postType":"技术","projectType":"校招","workPlace":"北京市",
          "workContent":"从事大模型后训练","serviceCondition":"熟悉 Python 和 PyTorch",
          "updateDate":"2026-07-21"
        }]}}; window.prefix="/jobs";</script>'''
        jobs = CompanyCareersProvider([])._parse_page(page, "https://talent.baidu.com/jobs/list")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_kind, "official")
        self.assertEqual(jobs[0].application_url, "https://talent.baidu.com/jobs/detail/GRADUATE/post-1")

    def test_company_provider_parses_tencent_public_position_api(self):
        catalog = CompanyCatalog([CompanyTarget("腾讯", "major", ("https://join.qq.com/post.html",), ())])
        provider = CompanyCatalogProvider(catalog)
        jobs = provider._parse_tencent_payload(
            {
                "status": 0,
                "data": {
                    "positionList": [
                        {
                            "postId": "1282707395466077186",
                            "positionTitle": "AI算法工程",
                            "workCities": "深圳总部 北京 上海 广州 ",
                            "projectName": "应届毕业生",
                            "positionFamily": 2,
                        }
                    ]
                },
            },
            "https://join.qq.com/post.html",
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "腾讯")
        self.assertEqual(jobs[0].locations, ["深圳总部", "北京", "上海", "广州"])
        self.assertEqual(jobs[0].application_url, "https://join.qq.com/post_detail.html?postid=1282707395466077186")

    def test_company_provider_parses_kuaishou_public_position_api(self):
        catalog = CompanyCatalog([CompanyTarget("快手", "major", ("https://campus.kuaishou.cn/",), ())])
        provider = CompanyCatalogProvider(catalog)
        jobs = provider._parse_kuaishou_payload(
            {
                "code": 0,
                "result": {
                    "list": [
                        {
                            "id": 13024,
                            "name": "大模型应用算法工程师-电商方向",
                            "description": "负责大模型应用",
                            "positionDemand": "熟悉 Python 和 RLHF",
                            "positionNatureCode": "fulltime",
                            "releaseTime": "2026-08-09 17:59:47",
                            "workLocationDicts": [{"name": "杭州", "code": "Hangzhou"}],
                        }
                    ]
                },
            },
            "https://campus.kuaishou.cn/",
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "快手")
        self.assertEqual(jobs[0].locations, ["杭州"])
        self.assertEqual(jobs[0].application_url, "https://campus.kuaishou.cn/recruit/campus/e#/campus/job-info/13024")

    def test_company_catalog_reports_reachability_separately_from_matching_jobs(self):
        catalog = CompanyCatalog([
            CompanyTarget("可访问公司", "major", ("https://reachable.example/jobs",), ()),
            CompanyTarget("不可访问公司", "unicorn", ("https://offline.example/jobs",), ()),
        ])
        provider = CompanyCatalogProvider(catalog, workers=2)

        def collect_target(target, url, terms):
            if target.name == "不可访问公司":
                return [], "不可访问公司: TimeoutError"
            return [], None

        with patch.object(provider, "_collect_target", side_effect=collect_target):
            result = provider.collect(profile(), ["大模型算法工程师"])

        self.assertEqual(result.metadata["reachable_companies"], 1)
        self.assertEqual(result.metadata["reachable_companies_by_tier"], {"major": 1, "unicorn": 0})
        self.assertEqual(result.metadata["companies_with_jobs"], 0)
        self.assertEqual(result.metadata["unreachable_companies"], 1)
        entries = {entry["name"]: entry for entry in result.metadata["coverage_entries"]}
        self.assertEqual(entries["可访问公司"]["status"], "reachable_no_match")
        self.assertEqual(entries["不可访问公司"]["status"], "unreachable")

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
