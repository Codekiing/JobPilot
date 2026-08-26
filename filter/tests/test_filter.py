from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from job_filter.builder import FilterBuilder, load_match_table
from job_filter.limits import load_limit_config, resolve_quota
from job_filter.template import render_html


def matcher_table() -> dict:
    return {
        "schema_version": "1.0",
        "component": "matcher",
        "profile_id": "profile-123456789abc",
        "created_at": "2026-08-26T00:00:00+00:00",
        "jobs": [
            {
                "source": "nowcoder",
                "source_job_id": "1",
                "title": "大模型算法工程师",
                "company": "示例科技有限公司",
                "locations": ["深圳"],
                "employment_type": "campus",
                "application_url": "https://example.com/apply/1",
                "match": {"total": 91, "grade": "A", "hard_constraints_passed": True, "matched_skills": ["Python"], "reasons": ["岗位方向命中"]},
            },
            {
                "source": "offershow",
                "source_job_id": "2",
                "title": "强化学习算法工程师",
                "company": "示例科技有限公司",
                "locations": ["北京"],
                "employment_type": "campus",
                "application_url": "https://example.com/apply/2",
                "match": {"total": 82, "grade": "A", "hard_constraints_passed": True},
            },
            {
                "source": "nowcoder",
                "source_job_id": "3",
                "title": "推荐算法工程师",
                "company": "另一家公司",
                "locations": ["上海"],
                "employment_type": "full_time",
                "application_limit": 3,
                "application_limit_confirmed": True,
                "match": {"total": 70, "grade": "B", "hard_constraints_passed": True},
            },
        ],
    }


class FilterTests(unittest.TestCase):
    def test_default_quota_is_conservative_and_unconfirmed(self):
        quota = resolve_quota("未知公司", "campus", [], load_limit_config(None))
        self.assertEqual(quota.limit, 1)
        self.assertFalse(quota.confirmed)
        self.assertEqual(quota.source, "conservative_default")
        self.assertEqual(quota.verification_status, "unverified")

    def test_company_config_and_job_embedded_quota_priority(self):
        config = {
            "default_limit": 1,
            "aliases": {"示例科技有限公司": "示例科技"},
            "companies": {
                "示例科技": {
                    "employment_types": ["campus"],
                    "limit": 2,
                    "confirmed": True,
                    "verification_status": "confirmed",
                    "verified_at": "2026-08-26",
                }
            },
        }
        configured = resolve_quota("示例科技有限公司", "campus", [], config)
        self.assertEqual(configured.limit, 2)
        self.assertTrue(configured.confirmed)
        self.assertEqual(configured.verification_status, "confirmed")
        embedded = resolve_quota("示例科技有限公司", "campus", [{"application_limit": 4}], config)
        self.assertEqual(embedded.limit, 4)
        self.assertEqual(embedded.source, "job_data")

    def test_reviewed_but_undisclosed_rule_is_distinct_from_unverified(self):
        config = {
            "default_limit": 1,
            "aliases": {},
            "companies": {
                "未公开公司": {
                    "employment_types": ["full_time"],
                    "limit": 1,
                    "confirmed": False,
                    "verification_status": "public_not_found",
                    "verified_at": "2026-08-26",
                }
            },
        }
        quota = resolve_quota("未公开公司", "full_time", [], config)
        self.assertFalse(quota.confirmed)
        self.assertEqual(quota.verification_status, "public_not_found")
        self.assertEqual(quota.verified_at, "2026-08-26")

    def test_builder_groups_by_company_and_employment_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.json"
            path.write_text(json.dumps(matcher_table(), ensure_ascii=False), encoding="utf-8")
            data = FilterBuilder().build_data(matcher_table(), path)
        self.assertEqual(data["summary"]["job_count"], 3)
        self.assertEqual(data["summary"]["company_count"], 2)
        self.assertEqual(data["summary"]["quota_group_count"], 2)
        self.assertEqual(data["summary"]["resolved_quota_count"], 1)
        self.assertTrue(data["filter_id"].startswith("filter-"))
        first = next(group for group in data["groups"] if group["company"] == "示例科技有限公司")
        self.assertEqual([job["score"] for job in first["jobs"]], [91.0, 82.0])

    def test_html_is_self_contained_and_escapes_script_termination(self):
        data = {
            "profile_id": "profile-x",
            "source_matcher_sha256": "abc",
            "source_matcher_json": "/tmp/jobs.json",
            "summary": {"job_count": 1, "company_count": 1},
            "groups": [{"group_id": "g", "company": "</script><script>alert(1)</script>", "employment_type": "campus", "quota": {"limit": 1, "confirmed": False, "source": "conservative_default", "verification_status": "unverified", "source_url": "", "verified_at": "", "note": ""}, "jobs": []}],
        }
        html = render_html(data)
        self.assertEqual(html.lower().count("<!doctype html>"), 1)
        self.assertNotIn("</script><script>alert(1)</script>", html)
        self.assertIn("selected-jobs.csv", html)
        self.assertIn("verificationStatus === 'public_not_found'", html)
        self.assertNotIn("fetch(", html)

    def test_build_file_writes_interactive_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "jobs.json"
            target = root / "job-filter.html"
            source.write_text(json.dumps(matcher_table(), ensure_ascii=False), encoding="utf-8")
            data = FilterBuilder().build_file(source, target)
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 10_000)
            self.assertEqual(data["profile_id"], "profile-123456789abc")
            self.assertEqual(load_match_table(source)["component"], "matcher")


if __name__ == "__main__":
    unittest.main()
