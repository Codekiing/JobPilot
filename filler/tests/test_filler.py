from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from filler.browser import match_fields
from filler.loader import load_selected_jobs
from filler.mapper import build_structured_records
from filler.official_sites import load_official_sites, resolve_official_site
from filler.planner import FillPlanner, adapter_for
from filler.storage import save_plan


def sample_profile() -> dict:
    return {
        "schema_version": "1.0",
        "profile_id": "profile-123456789abc",
        "identity": {
            "name": "测试用户",
            "gender": "女",
            "birth_date": "2002-08-16",
            "contact": {
                "email": "user@example.com",
                "phone": "13800000000",
                "links": ["https://github.com/example"],
            },
        },
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
    def test_structured_resume_records_are_preserved_for_ats_forms(self):
        records = build_structured_records({
            "evidence": {
                "education": [{
                    "title": "香港中文大学（QS 18） 人工智能与机器人（理学硕士）",
                    "date": "2025.09-2027.06",
                    "content": "GPA 3.72/4.00",
                }],
                "experience": [{
                    "title": "深圳市大数据研究院 大模型算法实习生",
                    "date": "2025.09-2026.02",
                    "content": "负责模型对齐与评测",
                }],
            }
        })
        self.assertEqual(records["education"][0]["school"], "香港中文大学")
        self.assertEqual(records["education"][0]["major"], "人工智能与机器人")
        self.assertEqual(records["education"][0]["start"], "2025-09")
        self.assertEqual(records["internship"][0]["company"], "深圳市大数据研究院")
        self.assertEqual(records["internship"][0]["title"], "大模型算法实习生")

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
        fields = {item["key"]: item["value"] for item in data["fields"]}
        self.assertEqual(fields["full_name"], "测试用户")
        self.assertEqual(fields["gender"], "女")
        self.assertEqual(fields["birth_date"], "2002-08-16")
        self.assertEqual(fields["personal_links"], "https://github.com/example")
        self.assertIn("Python", fields["skills"])
        self.assertIn("示例大学", fields["education_summary"])
        self.assertNotIn("fields", data["applications"][0])

    def test_shared_fields_are_serialized_once_for_multiple_jobs(self):
        jobs = sample_jobs()
        jobs["jobs"].append({
            **jobs["jobs"][0],
            "job_key": "moka:2",
            "title": "机器学习工程师",
            "application_url": "https://app.mokahr.com/apply/example/1#/job/2",
        })
        plan = FillPlanner().build(
            sample_profile(), jobs, profile_path=Path("profile.json"), selected_jobs_path=Path("selected-jobs.json")
        )
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
        self.assertEqual(len(plan.applications), 2)
        self.assertEqual(serialized.count("user@example.com"), 1)
        self.assertTrue(all("fields" not in item for item in plan.to_dict()["applications"]))

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
        self.assertEqual(adapter_for("https://hr-jobs.sensetime.com/exp/resume/1/apply"), "atsx")
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

    def test_matching_uses_visible_combobox_instead_of_hidden_input(self):
        fields = [
            {"key": "highest_degree", "aliases": ["最高学历", "学历", "degree"], "value": "硕士"},
            {"key": "preferred_locations", "aliases": ["意向城市", "preferred city"], "value": "深圳"},
        ]
        descriptors = [
            {"id": "education[0].degree", "tag": "input", "visible": False},
            {"id": "education[0].degree", "tag": "div", "role": "combobox", "visible": True},
            {"id": "application_preferred_city_list", "tag": "div", "role": "combobox", "visible": True},
        ]
        matches = match_fields(fields, descriptors)
        self.assertEqual([item["status"] for item in matches], ["matched", "matched"])
        self.assertEqual([item["descriptor_index"] for item in matches], [1, 2])

    def test_resume_file_is_explicitly_added_to_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "resume.pdf"
            resume.write_bytes(b"%PDF-1.4\n")
            plan = FillPlanner().build(
                sample_profile(),
                sample_jobs(),
                profile_path=Path("profile.json"),
                selected_jobs_path=Path("selected-jobs.json"),
                resume_file=resume,
            )
            data = plan.to_dict()
        self.assertEqual(data["resume_file"], str(resume.resolve()))
        self.assertTrue(data["summary"]["resume_file_configured"])
        self.assertTrue(data["safety"]["resume_upload_confirmation_required"])

    def test_unsupported_resume_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            resume = Path(tmp) / "resume.txt"
            resume.write_text("not an upload format", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不支持的简历文件格式"):
                FillPlanner().build(
                    sample_profile(),
                    sample_jobs(),
                    profile_path=Path("profile.json"),
                    selected_jobs_path=Path("selected-jobs.json"),
                    resume_file=resume,
                )

    def test_local_drafts_use_private_permissions(self):
        config = {"companies": {"示例科技": {"default": "https://app.mokahr.com/apply/example/1#/job/1"}}}
        plan = FillPlanner(config).build(
            sample_profile(), sample_jobs(), profile_path=Path("profile.json"), selected_jobs_path=Path("selected-jobs.json")
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = save_plan(plan, Path(tmp))
            mode = stat.S_IMODE((run_dir / "fill-plan.json").stat().st_mode)
            self.assertEqual(mode, 0o600)
            self.assertFalse((run_dir / "application-drafts").exists())


if __name__ == "__main__":
    unittest.main()
