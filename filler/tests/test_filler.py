from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from filler.browser import match_fields
from filler.loader import load_selected_jobs
from filler.official_sites import load_official_sites, resolve_official_site
from filler.planner import FillPlanner, adapter_for
from filler.storage import save_plan


def sample_profile() -> dict:
    return {
        "schema_version": "1.0",
        "profile_id": "profile-123456789abc",
        "identity": {"name": "测试用户", "contact": {"email": "user@example.com", "phone": "13800000000"}},
        "career": {"current_city": "深圳", "highest_degree": "硕士", "graduation_date": "2027-06"},
        "target": {"primary_roles": ["算法工程师"], "preferred_locations": ["深圳", "北京"]},
        "capabilities": {"skills": [{"name": "Python"}, {"name": "机器学习"}], "languages": ["英语"]},
        "evidence": {
            "education": [{"title": "示例大学 · 计算机", "date": "2024-2027", "content": "硕士"}],
            "experience": [{"title": "示例公司 · 算法实习生", "date": "2026", "content": "完成模型训练"}],
            "projects": [], "publications": []
        },
        "preferences": {"culture_keywords": ["导师制度"]},
    }


def sample_jobs() -> dict:
    return {
        "schema_version": "1.0",
        "component": "filter",
        "profile_id": "profile-123456789abc",
        "jobs": [
            {
                "job_key": "moka:1", "title": "算法工程师", "company": "示例科技",
                "application_url": "https://app.mokahr.com/apply/example/1#/job/1", "source_url": "https://example.com/job/1"
            }
        ],
    }


class FillerTests(unittest.TestCase):
    def test_verified_official_site_replaces_aggregator_job_url(self):
        config = {
            "aliases": {"示例科技有限公司": "示例科技"},
            "companies": {"示例科技": {"campus": "https://careers.example.com/campus"}},
        }
        jobs = sample_jobs()
        jobs["jobs"][0]["employment_type"] = "campus"
        jobs["jobs"][0]["application_url"] = "https://www.nowcoder.com/jobs/detail/1"
        plan = FillPlanner(config).build(
            sample_profile(), jobs, profile_path=Path("profile.json"), selected_jobs_path=Path("selected-jobs.json")
        )
        application = plan.to_dict()["applications"][0]
        self.assertEqual(application["application_url"], "https://careers.example.com/campus")
        self.assertEqual(application["original_application_url"], "https://www.nowcoder.com/jobs/detail/1")
        self.assertEqual(application["official_url_source"], "verified_company_config")

    def test_aggregator_without_official_mapping_is_not_opened(self):
        result = resolve_official_site(
            "未知公司", "campus", "https://www.nowcoder.com/jobs/detail/1", {"companies": {}}
        )
        self.assertEqual(result.url, "")
        self.assertEqual(result.source, "official_site_not_found")

    def test_repository_official_site_config_is_valid(self):
        config = load_official_sites(Path(__file__).parents[1] / "config" / "official_sites.json")
        result = resolve_official_site(
            "拼多多集团-PDD", "campus", "https://www.nowcoder.com/jobs/detail/1", config
        )
        self.assertEqual(result.url, "https://careers.pddglobalhr.com/campus/grad")

    def test_plan_maps_profile_and_job_without_browser_execution(self):
        config = {"companies": {"示例科技": {"default": "https://app.mokahr.com/apply/example/1#/job/1"}}}
        plan = FillPlanner(config).build(
            sample_profile(), sample_jobs(), profile_path=Path("profile.json"), selected_jobs_path=Path("selected-jobs.json")
        )
        data = plan.to_dict()
        self.assertEqual(data["summary"]["application_count"], 1)
        self.assertFalse(data["safety"]["browser_execution_default"])
        self.assertFalse(data["safety"]["automatic_submit"])
        self.assertEqual(data["applications"][0]["adapter"], "moka")
        fields = {item["key"]: item["value"] for item in data["applications"][0]["fields"]}
        self.assertEqual(fields["full_name"], "测试用户")
        self.assertIn("Python", fields["skills"])
        self.assertIn("示例大学", fields["education_summary"])

    def test_profile_id_mismatch_is_rejected(self):
        jobs = sample_jobs()
        jobs["profile_id"] = "profile-ffffffffffff"
        with self.assertRaisesRegex(ValueError, "不属于同一画像"):
            FillPlanner().build(sample_profile(), jobs, profile_path=Path("a"), selected_jobs_path=Path("b"))

    def test_invalid_or_empty_selected_jobs_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.json"
            path.write_text(json.dumps({"jobs": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "没有已选择岗位"):
                load_selected_jobs(path)

    def test_adapter_detection(self):
        self.assertEqual(adapter_for("https://app.mokahr.com/apply/x"), "moka")
        self.assertEqual(adapter_for("https://company.jobs.feishu.cn/x"), "feishu")
        self.assertEqual(adapter_for("https://company.zhiye.com/x"), "beisen")
        self.assertEqual(adapter_for("javascript:alert(1)"), "generic")

    def test_generic_field_matching_avoids_ambiguous_and_password_fields(self):
        fields = [
            {"key": "full_name", "aliases": ["姓名", "name"], "value": "测试用户"},
            {"key": "email", "aliases": ["邮箱", "email"], "value": "user@example.com"},
        ]
        descriptors = [
            {"label": "姓名", "name": "candidateName"},
            {"label": "电子邮箱", "name": "email"},
        ]
        matches = match_fields(fields, descriptors)
        self.assertEqual([item["status"] for item in matches], ["matched", "matched"])
        self.assertEqual(matches[0]["descriptor_index"], 0)

    def test_local_drafts_use_private_permissions(self):
        config = {"companies": {"示例科技": {"default": "https://app.mokahr.com/apply/example/1#/job/1"}}}
        plan = FillPlanner(config).build(
            sample_profile(), sample_jobs(), profile_path=Path("profile.json"), selected_jobs_path=Path("selected-jobs.json")
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = save_plan(plan, Path(tmp))
            mode = stat.S_IMODE((run_dir / "fill-plan.json").stat().st_mode)
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
