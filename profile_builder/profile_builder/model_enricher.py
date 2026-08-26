from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .enrichment import FIELD_TYPES
from .models import UserProfile


PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["patches", "unresolved"],
    "properties": {
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "value", "confidence", "evidence_answer_ids"],
                "properties": {
                    "path": {"type": "string", "enum": sorted(FIELD_TYPES)},
                    "value": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "boolean"},
                            {"type": "integer"},
                            {"type": "array", "items": {"type": "string"}},
                        ]
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_answer_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
}


class OpenAIProfileEnricher:
    """Optional Responses API client for extracting ambiguous survey details."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        if not model.strip():
            raise ValueError("启用模型补全时必须指定模型名称")
        self.model = model.strip()
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("启用模型补全需要设置 OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout

    def extract_patches(self, profile: UserProfile, survey_answers: dict[str, str]) -> list[dict[str, Any]]:
        safe_profile = {
            "career": profile.career,
            "target": profile.target,
            "skills": [item.get("name") for item in profile.capabilities.get("skills", [])],
            "preferences": profile.preferences,
            "constraints": profile.constraints,
            "completion": profile.completion,
        }
        safe_answers = _redact_answers(profile, survey_answers)
        payload = {
            "model": self.model,
            "store": False,
            "max_output_tokens": 2500,
            "safety_identifier": profile.profile_id,
            "instructions": (
                "你是求职用户画像字段抽取器。仅根据问卷原文提取明确支持的信息；"
                "不得猜测或生成性别、年龄、婚育、民族、宗教、健康等敏感属性；"
                "只为当前缺失字段返回补丁，每个补丁必须引用支持它的问卷答案ID。"
            ),
            "input": json.dumps(
                {"current_profile": safe_profile, "survey_answers": safe_answers},
                ensure_ascii=False,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "jobpilot_profile_patch",
                    "strict": True,
                    "schema": PATCH_SCHEMA,
                }
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"模型补全请求失败 ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"模型补全网络请求失败: {exc.reason}") from exc
        output_text = _response_output_text(result)
        parsed = json.loads(output_text)
        patches = parsed.get("patches", [])
        if not isinstance(patches, list):
            raise RuntimeError("模型返回的 patches 不是数组")
        return patches


def _response_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise RuntimeError("模型响应中没有 output_text")


def _redact_answers(profile: UserProfile, answers: dict[str, str]) -> dict[str, str]:
    contact = profile.identity.get("contact", {})
    secrets = [profile.identity.get("name"), contact.get("email"), contact.get("phone")]
    result: dict[str, str] = {}
    for question_id, raw_answer in answers.items():
        answer = str(raw_answer)
        for secret in secrets:
            if secret:
                answer = answer.replace(str(secret), "[REDACTED]")
        answer = re.sub(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", "[REDACTED_EMAIL]", answer, flags=re.IGNORECASE)
        answer = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[REDACTED_PHONE]", answer)
        result[question_id] = answer
    return result
