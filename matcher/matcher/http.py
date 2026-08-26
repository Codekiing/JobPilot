from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "JobPilot/0.1 (local job matcher; public pages only)"


def request_bytes(
    url: str,
    *,
    timeout: float = 15,
    method: str = "GET",
    form: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    }
    request_headers.update(headers or {})
    data = None
    if form is not None:
        data = urlencode(form, doseq=True).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def request_text(url: str, **kwargs: Any) -> str:
    return request_bytes(url, **kwargs).decode("utf-8", errors="replace")


def request_json(url: str, **kwargs: Any) -> dict[str, Any]:
    data = json.loads(request_bytes(url, **kwargs).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("远端响应不是 JSON 对象")
    return data
