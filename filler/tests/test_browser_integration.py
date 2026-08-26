from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from filler.browser import execute_plan


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "需要安装 filler[browser]")
class BrowserIntegrationTests(unittest.TestCase):
    def test_real_field_fill_and_explicit_remote_draft_save(self):
        draft_id = "draft-local-test"
        mock_page = Path(__file__).parents[1] / "examples" / "mock-career.html"
        fields = [
            {"key": "full_name", "value": "测试用户", "aliases": ["姓名", "name"]},
            {"key": "email", "value": "user@example.com", "aliases": ["邮箱", "电子邮箱", "email"]},
            {"key": "phone", "value": "13800000000", "aliases": ["手机号码", "电话", "mobile"]},
            {"key": "current_city", "value": "深圳", "aliases": ["现居城市", "current city"]},
            {"key": "skills", "value": "Python、机器学习", "aliases": ["技能", "skills"]},
        ]
        plan = {
            "applications": [{
                "draft_id": draft_id,
                "company": "示例科技",
                "title": "算法工程师",
                "application_url": mock_page.resolve().as_uri(),
                "fields": fields,
            }]
        }
        answers = iter([
            f"READY {draft_id}",
            f"FILL {draft_id}",
            f"SAVE {draft_id}",
        ])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = execute_plan(
                plan,
                run_dir=root,
                browser_profile=root / "browser-profile",
                headless=True,
                save_remote_draft=True,
                input_func=lambda _: next(answers),
            )
            report = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertTrue(report["remote_draft_saved"])
        self.assertEqual(report["remote_save_status"], "confirmed_by_page")
        self.assertTrue(all(item["status"] == "filled_verified" for item in report["fields"] if item["key"] in {f["key"] for f in fields}))
        self.assertFalse(report["automatic_submit"])


if __name__ == "__main__":
    unittest.main()
