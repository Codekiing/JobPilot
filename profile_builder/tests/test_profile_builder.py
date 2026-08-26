from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from profile_builder import ProfileBuilder, ProfileEnricher, SimpleSurvey
from profile_builder.model_enricher import _redact_answers, _response_output_text
from profile_builder.cli import main as cli_main
from profile_builder.storage import save_profile


PROJECT_ROOT = Path(__file__).parents[2]


class ProfileBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resume_json = PROJECT_ROOT / "profile_builder" / "examples" / "resume.example.json"

    def setUp(self) -> None:
        self.builder = ProfileBuilder()
        self.survey = SimpleSurvey()
        self.enricher = ProfileEnricher()

    def test_resume_output_builds_normalized_profile(self) -> None:
        profile = self.builder.build_from_file(self.resume_json)
        self.assertEqual(profile.identity["name"], "示例候选人")
        self.assertEqual(profile.career["career_stage"], "student")
        self.assertEqual(profile.career["highest_degree"], "硕士")
        self.assertEqual(profile.career["graduation_date"], "2027-06")
        self.assertEqual(profile.target["primary_roles"], ["机器学习工程师"])
        skill_names = {skill["name"] for skill in profile.capabilities["skills"]}
        self.assertTrue({"Python", "PyTorch", "机器学习", "深度学习"} <= skill_names)
        self.assertGreater(len(profile.evidence["quantified_achievements"]), 2)

    def test_schema_is_valid_json_and_matches_top_level_contract(self) -> None:
        schema_path = PROJECT_ROOT / "profile_builder" / "schemas" / "user_profile.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        profile = self.builder.build_from_file(self.resume_json).to_dict()
        self.assertEqual(schema["properties"]["schema_version"]["const"], profile["schema_version"])
        self.assertFalse(set(schema["required"]) - profile.keys())

    def test_profile_and_questions_are_saved_together(self) -> None:
        profile = self.builder.build_from_file(self.resume_json)
        with tempfile.TemporaryDirectory() as tmp:
            output = save_profile(profile, self.survey.questions(), tmp)
            self.assertTrue((output / "profile.json").exists())
            self.assertTrue((output / "questions.json").exists())
            self.assertTrue((output / "profile_summary.md").exists())
            saved = json.loads((output / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["profile_id"], profile.profile_id)
            questions = json.loads((output / "questions.json").read_text(encoding="utf-8"))
            self.assertEqual(len(questions["questions"]), 12)

    def test_simple_survey_has_twelve_questions_and_covers_all_angles(self) -> None:
        questions = self.survey.questions()
        self.assertEqual(len(questions), 12)
        angles = {question.angle for question in questions}
        self.assertTrue({"基本情况与职业阶段", "目标岗位", "地点与办公方式", "技能与核心优势", "求职硬约束"} <= angles)
        covered = {path for question in questions for path in question.covers}
        self.assertTrue({"target.primary_roles", "capabilities.skills", "evidence.user_highlights", "constraints.deal_breakers"} <= covered)

    def test_survey_rules_complete_missing_profile_fields(self) -> None:
        profile = self.builder.build_from_file(self.resume_json)
        enriched = self.enricher.enrich(
            profile,
            {
                "basic_status": "目前在深圳，2027届硕士，正在积极求职",
                "job_targets": "全职；首选大模型后训练算法工程师，其次Agent算法工程师",
                "location_work_mode": "首选深圳、北京，可接受上海；接受现场或混合办公，可以搬迁",
                "availability": "2027-07-01入职",
                "compensation": "最低30K，期望35K-45K，14薪以上，可商议",
                "strengths_skills": "GRPO、RLHF、分布式训练；能独立定位训练稳定性问题",
                "achievements": "准确率提升11%；调参成本降低60%",
                "constraints": "不接受长期出差和单休；可接受适度加班",
            },
        )
        self.assertEqual(enriched.career["current_city"], "深圳")
        self.assertEqual(enriched.career["job_search_status"], "actively_looking")
        self.assertEqual(enriched.target["preferred_locations"], ["深圳", "北京"])
        self.assertEqual(enriched.target["acceptable_locations"], ["上海"])
        self.assertEqual(enriched.target["salary"]["monthly_min_cny"], 30000)
        self.assertEqual(enriched.target["salary"]["monthly_max_cny"], 45000)
        self.assertEqual(enriched.target["salary"]["expected_salary_months"], 14)
        self.assertEqual(enriched.evidence["user_highlights"], ["准确率提升11%", "调参成本降低60%"])
        self.assertTrue(enriched.completion["match_ready"])

    def test_survey_rules_extract_internship_availability(self) -> None:
        profile = self.builder.build_from_file(self.resume_json)
        enriched = self.enricher.enrich(
            profile,
            {
                "job_targets": "实习；大模型算法实习生",
                "availability": "2026-09-01开始，每周5天，连续6个月，希望转正",
            },
        )
        self.assertEqual(enriched.target["employment_types"], ["internship"])
        self.assertEqual(enriched.target["available_from"], "2026-09-01")
        self.assertEqual(enriched.target["internship"]["days_per_week"], 5)
        self.assertEqual(enriched.target["internship"]["duration_months"], 6)
        self.assertEqual(enriched.target["internship"]["conversion_intent"], "yes")

    def test_model_only_fills_missing_fields_and_records_provenance(self) -> None:
        class FakeModel:
            model = "fake-structured-model"

            def extract_patches(self, profile, survey_answers):
                return [
                    {"path": "target.primary_roles", "value": ["不应覆盖"], "confidence": 1.0, "evidence_answer_ids": ["job_targets"]},
                    {"path": "preferences.culture_keywords", "value": ["技术成长", "导师制度"], "confidence": 0.9, "evidence_answer_ids": ["additional_context"]},
                ]

        profile = self.builder.build_from_file(self.resume_json)
        original_roles = list(profile.target["primary_roles"])
        enriched = self.enricher.enrich(
            profile,
            {"additional_context": "希望重视技术成长并有导师制度"},
            model_enricher=FakeModel(),
        )
        self.assertEqual(enriched.target["primary_roles"], original_roles)
        self.assertEqual(enriched.preferences["culture_keywords"], ["技术成长", "导师制度"])
        self.assertEqual(enriched.questionnaire["model_enrichment"]["model"], "fake-structured-model")
        self.assertEqual(len(enriched.questionnaire["model_enrichment"]["applied_patches"]), 1)

    def test_model_payload_redacts_identity_and_response_text_is_parsed(self) -> None:
        profile = self.builder.build_from_file(self.resume_json)
        redacted = _redact_answers(
            profile,
            {"basic_status": "我是示例候选人，邮箱candidate@example.com，电话13800000000，目前在北京"},
        )
        self.assertNotIn("示例候选人", redacted["basic_status"])
        self.assertNotIn("candidate@example.com", redacted["basic_status"])
        self.assertNotIn("13800000000", redacted["basic_status"])
        response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "{\"patches\":[],\"unresolved\":[]}"}]}]}
        self.assertIn("patches", _response_output_text(response))

    def test_cli_accepts_simple_survey_answer_file(self) -> None:
        answers = PROJECT_ROOT / "profile_builder" / "examples" / "survey_answers.example.json"
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            exit_code = cli_main(
                [
                    "--resume-json",
                    str(self.resume_json),
                    "--draft",
                    "--answers",
                    str(answers),
                    "--output-dir",
                    tmp,
                ]
            )
            self.assertEqual(exit_code, 0)
            profile_path = next(Path(tmp).glob("*/profile.json"))
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(len(profile["questionnaire"]["survey_answers"]), 12)
            self.assertTrue(profile["completion"]["match_ready"])


if __name__ == "__main__":
    unittest.main()
