from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ProviderResult


class Provider(ABC):
    name: str

    def __init__(self, *, timeout: float = 15, max_jobs: int = 30) -> None:
        self.timeout = timeout
        self.max_jobs = max_jobs

    @abstractmethod
    def collect(self, profile: dict[str, Any], queries: list[str]) -> ProviderResult:
        raise NotImplementedError
