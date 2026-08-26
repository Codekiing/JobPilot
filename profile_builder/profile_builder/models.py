from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class UserProfile:
    schema_version: str
    profile_id: str
    metadata: dict[str, Any]
    identity: dict[str, Any]
    career: dict[str, Any]
    target: dict[str, Any]
    capabilities: dict[str, Any]
    evidence: dict[str, Any]
    preferences: dict[str, Any]
    constraints: dict[str, Any]
    matching_config: dict[str, Any]
    questionnaire: dict[str, Any]
    completion: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "UserProfile":
        required = {
            "schema_version",
            "profile_id",
            "metadata",
            "identity",
            "career",
            "target",
            "capabilities",
            "evidence",
            "preferences",
            "constraints",
            "matching_config",
            "questionnaire",
        }
        missing = required - value.keys()
        if missing:
            raise ValueError(f"用户画像缺少字段: {', '.join(sorted(missing))}")
        return cls(**{key: value[key] for key in required}, completion=value.get("completion", {}))
