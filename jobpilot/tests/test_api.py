from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from jobpilot.api import JobPilotAPIError, build_filler_request, build_filter_request, build_match_request, build_profile_request, build_rank_request, build_resume_request, build_state_response, create_server, questionnaire_response


PROJECT_ROOT = Path(__file__).parents[2]
RESUME_EXAMPLE = "profile_builder/examples/resume.example.json"
PROFILE_EXAMPLE = "filler/inputs/profile.example.json"


class JobPilotAPITests(unittest.TestCase):
    def test_resume_upload_runs_local_extractor_and_profile_builder(self) -> None:
        resume = """张三\n北京\n求职意向：机器学习工程师\n\n教育背景\n2024.09-2027.06 示例大学 计算机科学 硕士\n\n项目经历\n模型评测平台，使用 Python 和 PyTorch\n\n核心技能\nPython、PyTorch、机器学习\n"""
        result = build_resume_request(
            {
                "filename": "张三-简历.md",
                "content_base64": base64.b64encode(resume.encode("utf-8")).decode("ascii"),
                "save": False,
            }
        )
        self.assertEqual(result["meta"]["processing_mode"], "local_components")
        self.assertEqual(result["meta"]["components"], ["resume_splitter", "profile_builder"])
        self.assertGreaterEqual(result["data"]["resume"]["section_count"], 3)
        self.assertEqual(result["data"]["profile"]["metadata"]["component"], "profile_builder")

    def test_rank_request_uses_matcher_scores(self) -> None:
        profile = json.loads((PROJECT_ROOT / PROFILE_EXAMPLE).read_text(encoding="utf-8"))
        result = build_rank_request(
            {
                "profile": profile,
                "jobs": [
                    {"id": 1, "title": "机器学习算法工程师", "company": "示例科技", "tags": ["Python", "机器学习"], "locations": ["北京"]},
                    {"id": 2, "title": "市场营销专员", "company": "示例品牌", "tags": ["销售"], "locations": ["广州"]},
                ],
            }
        )
        self.assertEqual(result["meta"]["component"], "matcher")
        self.assertFalse(result["meta"]["external_network_called"])
        self.assertEqual(result["data"]["jobs"][0]["id"], "1")

    def test_state_response_exposes_full_latest_profile_evidence(self) -> None:
        result = build_state_response()
        self.assertEqual(result["meta"]["processing_mode"], "local_persisted_state")
        self.assertGreaterEqual(result["data"]["resume"]["section_count"], 1)
        self.assertIn("skills", result["data"]["profile"]["capabilities"])
        self.assertIn("evidence", result["data"]["profile"])

    def test_profile_completion_tracks_application_form_fields(self) -> None:
        profile = build_state_response()["data"]["profile"]
        profile["identity"]["contact"] = {"phone": None, "email": None, "links": []}
        completion = build_profile_request({"profile": profile, "save": False})["data"]["completion"]
        missing_paths = {
            item["field_path"]
            for item in completion["missing_required"] + completion["missing_recommended"]
        }
        obsolete_paths = {
            "target.available_from",
            "career.job_search_status",
            "target.preferred_industries",
            "target.salary.monthly_min_cny",
            "preferences.company_sizes",
            "constraints.deal_breakers",
        }
        self.assertTrue(obsolete_paths.isdisjoint(missing_paths))
        self.assertTrue({"identity.contact.phone", "identity.contact.email"} <= missing_paths)

    def test_questionnaire_contract_and_default_model_flag(self) -> None:
        result = questionnaire_response()
        self.assertEqual(len(result["questions"]), 12)
        self.assertFalse(result["model_call_default"])
        self.assertEqual(result["endpoint"], "/jobpilot/profile")

    def test_profile_request_does_not_construct_model_by_default(self) -> None:
        def forbidden_model_factory(*args, **kwargs):
            raise AssertionError("默认规则模式不应构造或调用模型")

        result = build_profile_request(
            {
                "resume_json": RESUME_EXAMPLE,
                "survey_answers": {
                    "basic_status": "目前在深圳，正在积极求职",
                    "location_work_mode": "首选深圳，接受现场办公",
                },
                "save": False,
            },
            model_factory=forbidden_model_factory,
        )
        self.assertEqual(result["meta"]["processing_mode"], "rules_only")
        self.assertFalse(result["meta"]["model_called"])
        self.assertEqual(result["data"]["career"]["current_city"], "深圳")

    def test_profile_request_accepts_and_recalculates_browser_profile(self) -> None:
        profile = build_state_response()["data"]["profile"]
        profile["target"]["preferred_locations"] = ["深圳"]
        result = build_profile_request({"profile": profile, "save": False})
        self.assertEqual(result["meta"]["source_kind"], "browser_profile")
        self.assertEqual(result["data"]["target"]["preferred_locations"], ["深圳"])
        self.assertIn("completion", result["data"])

    def test_model_use_requires_explicit_boolean_and_model_name(self) -> None:
        with self.assertRaisesRegex(JobPilotAPIError, "布尔值"):
            build_profile_request({"use_model": "false", "save": False})
        with self.assertRaisesRegex(JobPilotAPIError, "必须提供 model"):
            build_profile_request(
                {
                    "resume_json": RESUME_EXAMPLE,
                    "use_model": True,
                    "survey_answers": {"additional_context": "偏好导师制度"},
                    "save": False,
                }
            )
        with self.assertRaisesRegex(JobPilotAPIError, "禁止通过请求体"):
            build_profile_request({"api_key": "must-not-be-accepted", "save": False})

    def test_explicit_model_mode_uses_injected_model(self) -> None:
        calls: list[str] = []

        class FakeModel:
            def __init__(self, model: str, **kwargs) -> None:
                self.model = model
                calls.append(model)

            def extract_patches(self, profile, survey_answers):
                return [
                    {
                        "path": "preferences.culture_keywords",
                        "value": ["导师制度"],
                        "confidence": 0.9,
                        "evidence_answer_ids": ["additional_context"],
                    }
                ]

        result = build_profile_request(
            {
                "resume_json": RESUME_EXAMPLE,
                "use_model": True,
                "model": "fake-model",
                "survey_answers": {"additional_context": "偏好导师制度"},
                "save": False,
            },
            model_factory=FakeModel,
        )
        self.assertEqual(calls, ["fake-model"])
        self.assertTrue(result["meta"]["model_called"])
        self.assertEqual(result["data"]["preferences"]["culture_keywords"], ["导师制度"])

    def test_match_api_is_offline_by_default(self) -> None:
        result = build_match_request({"profile_json": PROFILE_EXAMPLE, "save": False})
        self.assertEqual(result["meta"]["processing_mode"], "offline_only")
        self.assertFalse(result["meta"]["external_network_called"])
        self.assertEqual(result["data"]["providers"], [])

    def test_filter_api_generates_local_html_without_network(self) -> None:
        table = {
            "schema_version": "1.0",
            "component": "matcher",
            "profile_id": "profile-123456789abc",
            "jobs": [
                {
                    "source": "example",
                    "source_job_id": "1",
                    "title": "算法工程师",
                    "company": "示例公司",
                    "locations": ["北京"],
                    "employment_type": "full_time",
                    "application_url": "https://example.com/apply/1",
                    "match": {"total": 90, "hard_constraints_passed": True},
                }
            ],
        }
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmp:
            matcher_path = Path(tmp) / "jobs.json"
            matcher_path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
            result = build_filter_request({"matcher_json": str(matcher_path), "output_dir": tmp})
        self.assertEqual(result["meta"]["processing_mode"], "local_html_generation")
        self.assertFalse(result["meta"]["external_network_called"])
        self.assertTrue(result["data"]["html_path"].endswith("job-filter.html"))

    def test_filler_api_only_creates_local_draft(self) -> None:
        payload = {
            "schema_version": "1.0",
            "component": "filter",
            "profile_id": "profile-123456789abc",
            "jobs": [{
                "job_key": "example:1",
                "title": "算法工程师",
                "company": "示例公司",
                "application_url": "https://example.com/apply/1"
            }],
        }
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmp:
            path = Path(tmp) / "selected-jobs.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            resume = Path(tmp) / "resume.pdf"
            resume.write_bytes(b"%PDF-1.4\n")
            result = build_filler_request(
                {
                    "profile_json": PROFILE_EXAMPLE,
                    "selected_jobs_json": str(path),
                    "resume_file": str(resume),
                    "output_dir": tmp,
                }
            )
        self.assertEqual(result["meta"]["processing_mode"], "local_draft_only")
        self.assertFalse(result["meta"]["external_network_called"])
        self.assertFalse(result["meta"]["browser_opened"])
        self.assertFalse(result["meta"]["personal_data_transmitted"])
        self.assertTrue(result["meta"]["resume_file_configured"])
        self.assertFalse(result["meta"]["resume_uploaded"])
        self.assertFalse(result["meta"]["automatic_submit"])

    def test_http_health_and_profile_endpoints(self) -> None:
        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(f"{base}/jobpilot/health") as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertFalse(health["model_call_default"])
            self.assertFalse(health["online_sources_default"])

            with urllib.request.urlopen(f"{base}/jobpilot/openapi.json") as response:
                specification = json.loads(response.read().decode("utf-8"))
            self.assertFalse(
                specification["paths"]["/jobpilot/profile"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["use_model"]["default"]
            )
            self.assertFalse(
                specification["paths"]["/jobpilot/match"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["online"]["default"]
            )
            self.assertIn("/jobpilot/filter", specification["paths"])
            self.assertIn("/jobpilot/filler", specification["paths"])
            self.assertIn("/jobpilot/state", specification["paths"])

            with urllib.request.urlopen(f"{base}/jobpilot/state") as response:
                state = json.loads(response.read().decode("utf-8"))
            self.assertEqual(state["meta"]["processing_mode"], "local_persisted_state")

            body = json.dumps(
                {"resume_json": RESUME_EXAMPLE, "survey_answers": {}, "save": False}
            ).encode("utf-8")
            request = urllib.request.Request(
                f"{base}/jobpilot/profile",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["meta"]["processing_mode"], "rules_only")
            self.assertFalse(result["meta"]["model_called"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
