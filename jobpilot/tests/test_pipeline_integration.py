from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from extractor.resume_splitter import ResumeParser
from filler.filler.loader import load_profile as load_fill_profile, load_selected_jobs
from filler.filler.planner import FillPlanner
from filler.filler.storage import save_plan
from filter.job_filter.builder import FilterBuilder
from matcher.matcher.engine import MatchEngine
from matcher.matcher.profile import load_profile as load_match_profile
from matcher.matcher.providers import ImportProvider
from matcher.matcher.storage import save_run
from profile_builder.profile_builder import ProfileBuilder, SimpleSurvey
from profile_builder.profile_builder.storage import save_profile


class PipelineIntegrationTests(unittest.TestCase):
    def test_component_outputs_feed_the_next_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume_path = root / "resume.md"
            resume_path.write_text(
                """# 张三

邮箱：zhangsan@example.com | 电话：13800138000
求职意向：后端工程师

## 教育背景
2020.09-2024.06 示例大学 本科 计算机科学

## 项目经历
2023.01-2023.06 搜索系统
- 使用 Python 和 Go 将检索延迟降低 30%

## 核心技能
Python、Go、PostgreSQL
""",
                encoding="utf-8",
            )

            _, resume_dir = ResumeParser().parse_and_save(resume_path, root / "extractor-outputs")
            profile = ProfileBuilder().build_from_file(resume_dir / "resume.json")
            profile_dir = save_profile(profile, SimpleSurvey().questions(), root / "profile-outputs")
            loaded_profile = load_match_profile(profile_dir / "profile.json")

            imported_jobs = root / "jobs.json"
            imported_jobs.write_text(
                json.dumps(
                    [{
                        "source": "company_careers",
                        "source_job_id": "backend-1",
                        "title": "后端工程师",
                        "company": "示例公司",
                        "locations": ["深圳"],
                        "employment_type": "full_time",
                        "description": "使用 Python 和 Go 开发服务",
                        "tags": ["Python", "Go"],
                        "url": "https://careers.example.com/jobs/1",
                        "application_url": "https://careers.example.com/jobs/1/apply",
                    }],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            run = MatchEngine([ImportProvider([imported_jobs])]).run(loaded_profile)
            matcher_dir = save_run(run, root / "matcher-outputs")

            filter_path = root / "filter-outputs" / "job-filter.html"
            filter_data = FilterBuilder().build_file(matcher_dir / "jobs.json", filter_path)
            selected_job = filter_data["groups"][0]["jobs"][0]
            selected_path = root / "selected-jobs.json"
            selected_path.write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "component": "filter",
                    "profile_id": filter_data["profile_id"],
                    "jobs": [selected_job],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            plan = FillPlanner().build(
                load_fill_profile(profile_dir / "profile.json"),
                load_selected_jobs(selected_path),
                profile_path=profile_dir / "profile.json",
                selected_jobs_path=selected_path,
            )
            filler_dir = save_plan(plan, root / "filler-outputs")
            saved_plan = json.loads((filler_dir / "fill-plan.json").read_text(encoding="utf-8"))

            self.assertEqual(saved_plan["profile_id"], profile.profile_id)
            self.assertEqual(saved_plan["summary"]["application_count"], 1)
            self.assertEqual(saved_plan["applications"][0]["job_key"], "company_careers:backend-1")
            self.assertEqual(
                {field["key"] for field in saved_plan["fields"]} & {"full_name", "email", "phone"},
                {"full_name", "email", "phone"},
            )
            self.assertNotIn("fields", saved_plan["applications"][0])
            self.assertTrue(filter_path.is_file())


if __name__ == "__main__":
    unittest.main()
