from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from jobpilot.api import JobPilotAPIError, build_filler_request, build_filter_request, build_match_request, build_profile_request, create_server, questionnaire_response


PROJECT_ROOT = Path(__file__).parents[2]
RESUME_EXAMPLE = "profile_builder/examples/resume.example.json"
PROFILE_EXAMPLE = "filler/inputs/profile.example.json"


class JobPilotAPITests(unittest.TestCase):
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
            result = build_filler_request(
                {
                    "profile_json": PROFILE_EXAMPLE,
                    "selected_jobs_json": str(path),
                    "output_dir": tmp,
                }
            )
        self.assertEqual(result["meta"]["processing_mode"], "local_draft_only")
        self.assertFalse(result["meta"]["external_network_called"])
        self.assertFalse(result["meta"]["browser_opened"])
        self.assertFalse(result["meta"]["personal_data_transmitted"])
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
