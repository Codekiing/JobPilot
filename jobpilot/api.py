from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from filter.job_filter.builder import FilterBuilder, find_latest_jobs
from filter.job_filter.storage import output_path as filter_output_path, update_manifest as update_filter_manifest
from filler.filler.loader import find_latest_profile as find_latest_fill_profile, load_profile as load_fill_profile, load_selected_jobs
from filler.filler.official_sites import load_official_sites
from filler.filler.planner import FillPlanner
from filler.filler.storage import save_plan as save_fill_plan
from matcher.matcher.engine import MatchEngine
from matcher.matcher.profile import find_latest_profile, load_profile as load_match_profile
from matcher.matcher.providers import BossProvider, ImportProvider, NowcoderProvider, OfferShowProvider, ShixisengProvider
from matcher.matcher.storage import save_run
from profile_builder.profile_builder.builder import ProfileBuilder
from profile_builder.profile_builder.completion import calculate_completion
from profile_builder.profile_builder.enrichment import ProfileEnricher
from profile_builder.profile_builder.model_enricher import OpenAIProfileEnricher
from profile_builder.profile_builder.models import UserProfile
from profile_builder.profile_builder.storage import save_profile
from profile_builder.profile_builder.survey import SimpleSurvey


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "profile_builder" / "outputs"
DEFAULT_MATCHER_OUTPUT_ROOT = PROJECT_ROOT / "matcher" / "outputs"
DEFAULT_FILTER_OUTPUT_ROOT = PROJECT_ROOT / "filter" / "outputs"
DEFAULT_FILTER_LIMITS = PROJECT_ROOT / "filter" / "config" / "company_limits.json"
DEFAULT_FILLER_OUTPUT_ROOT = PROJECT_ROOT / "filler" / "outputs"
DEFAULT_OFFICIAL_SITES = PROJECT_ROOT / "filler" / "config" / "official_sites.json"
DEFAULT_RESUME_ROOTS = (PROJECT_ROOT / "extractor" / "outputs",)
MAX_REQUEST_BYTES = 1024 * 1024


class JobPilotAPIError(ValueError):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = int(status)


def questionnaire_response() -> dict[str, Any]:
    """Return the stable questionnaire contract for a frontend or client."""
    return {
        "schema_version": "1.0",
        "endpoint": "/jobpilot/profile",
        "model_call_default": False,
        "questions": [question.to_dict() for question in SimpleSurvey().questions()],
    }


def build_profile_request(
    payload: dict[str, Any],
    *,
    model_factory: Callable[..., Any] = OpenAIProfileEnricher,
) -> dict[str, Any]:
    """Build/enrich a profile. External model use is strictly opt-in."""
    if not isinstance(payload, dict):
        raise JobPilotAPIError("请求体必须是 JSON 对象")
    if "api_key" in payload:
        raise JobPilotAPIError("禁止通过请求体传入 api_key；请使用服务端环境变量")

    use_model = payload.get("use_model", False)
    if not isinstance(use_model, bool):
        raise JobPilotAPIError("use_model 必须是布尔值；省略时默认为 false")
    save_result = payload.get("save", True)
    if not isinstance(save_result, bool):
        raise JobPilotAPIError("save 必须是布尔值")

    if payload.get("profile_json") and payload.get("resume_json"):
        raise JobPilotAPIError("profile_json 和 resume_json 不能同时提供")
    if payload.get("profile_json"):
        profile = _load_profile(_resolve_project_file(str(payload["profile_json"])))
        source_kind = "existing_profile"
    else:
        resume_path = (
            _resolve_project_file(str(payload["resume_json"]))
            if payload.get("resume_json")
            else _find_latest_resume()
        )
        profile = ProfileBuilder().build_from_file(resume_path)
        source_kind = "resume_output"

    answers = payload.get("survey_answers", {})
    if not isinstance(answers, dict):
        raise JobPilotAPIError("survey_answers 必须是 JSON 对象")
    valid_ids = {question.id for question in SimpleSurvey().questions()}
    unknown = set(answers) - valid_ids
    if unknown:
        raise JobPilotAPIError(f"未知问卷题号: {', '.join(sorted(unknown))}")
    normalized_answers = {
        str(question_id): str(answer).strip()
        for question_id, answer in answers.items()
        if str(answer).strip()
    }

    model_enricher = None
    if use_model:
        if not normalized_answers:
            raise JobPilotAPIError("调用模型前至少需要一条问卷答案")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            raise JobPilotAPIError("use_model=true 时必须提供 model")
        api_base = payload.get("api_base")
        if api_base is not None and not isinstance(api_base, str):
            raise JobPilotAPIError("api_base 必须是字符串")
        # API keys are intentionally read only from the server environment;
        # request bodies must never carry credentials.
        model_enricher = model_factory(model.strip(), base_url=api_base)

    if normalized_answers:
        profile = ProfileEnricher().enrich(profile, normalized_answers, model_enricher=model_enricher)
    else:
        profile.completion = calculate_completion(profile)

    saved_to = None
    if save_result:
        output_root = (
            _resolve_project_directory(str(payload["output_dir"]), create=True)
            if payload.get("output_dir")
            else DEFAULT_OUTPUT_ROOT
        )
        saved_to = save_profile(profile, SimpleSurvey().questions(), output_root)

    return {
        "schema_version": "1.0",
        "data": profile.to_dict(),
        "meta": {
            "source_kind": source_kind,
            "processing_mode": "rules_and_model" if use_model else "rules_only",
            "model_called": use_model,
            "model": payload.get("model") if use_model else None,
            "saved_to": str(saved_to) if saved_to else None,
        },
    }


def build_match_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Collect and match jobs. Outbound network access is strictly opt-in for the API."""
    if not isinstance(payload, dict):
        raise JobPilotAPIError("请求体必须是 JSON 对象")
    online = payload.get("online", False)
    save_result = payload.get("save", True)
    if not isinstance(online, bool):
        raise JobPilotAPIError("online 必须是布尔值；省略时默认为 false")
    if not isinstance(save_result, bool):
        raise JobPilotAPIError("save 必须是布尔值")

    profile_path = (
        _resolve_project_file(str(payload["profile_json"]))
        if payload.get("profile_json")
        else find_latest_profile(PROJECT_ROOT)
    )
    profile = load_match_profile(profile_path)

    queries = payload.get("queries")
    if queries is not None and (not isinstance(queries, list) or not all(isinstance(x, str) for x in queries)):
        raise JobPilotAPIError("queries 必须是字符串数组")
    imports = payload.get("import_jobs", [])
    if not isinstance(imports, list) or not all(isinstance(x, str) for x in imports):
        raise JobPilotAPIError("import_jobs 必须是项目内文件路径数组")
    import_paths = [_resolve_project_file(value) for value in imports]

    max_per_source = payload.get("max_per_source", 30)
    limit = payload.get("limit", 100)
    min_score = payload.get("min_score", 0)
    if not isinstance(max_per_source, int) or not 1 <= max_per_source <= 100:
        raise JobPilotAPIError("max_per_source 必须是 1 到 100 的整数")
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise JobPilotAPIError("limit 必须是 1 到 500 的整数")
    if not isinstance(min_score, (int, float)) or not 0 <= min_score <= 100:
        raise JobPilotAPIError("min_score 必须在 0 到 100 之间")

    providers = []
    provider_kwargs = {"timeout": 15, "max_jobs": max_per_source}
    if import_paths:
        providers.append(ImportProvider(import_paths, **provider_kwargs))
    selected_sources: list[str] = []
    if online:
        sources = payload.get("sources", ["boss", "shixiseng", "nowcoder", "offershow"])
        if not isinstance(sources, list) or not all(isinstance(x, str) for x in sources):
            raise JobPilotAPIError("sources 必须是字符串数组")
        mapping = {
            "boss": BossProvider,
            "shixiseng": ShixisengProvider,
            "nowcoder": NowcoderProvider,
            "offershow": OfferShowProvider,
        }
        unknown = sorted(set(sources) - mapping.keys())
        if unknown:
            raise JobPilotAPIError("未知渠道：" + ", ".join(unknown))
        selected_sources = list(dict.fromkeys(sources))
        providers.extend(mapping[source](**provider_kwargs) for source in selected_sources)

    run = MatchEngine(providers).run(
        profile,
        queries=[query.strip() for query in queries if query.strip()] if queries else None,
        min_score=float(min_score),
        limit=limit,
    )
    saved_to = None
    if save_result:
        output_root = (
            _resolve_project_directory(str(payload["output_dir"]), create=True)
            if payload.get("output_dir")
            else DEFAULT_MATCHER_OUTPUT_ROOT
        )
        saved_to = save_run(run, output_root)
    return {
        "schema_version": "1.0",
        "data": run.to_dict(),
        "meta": {
            "processing_mode": "online_public_sources" if online else "offline_only",
            "external_network_called": online,
            "sources": selected_sources,
            "profile_json": str(profile_path),
            "saved_to": str(saved_to) if saved_to else None,
        },
    }


def build_filter_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a self-contained interactive job filter page without network access."""
    if not isinstance(payload, dict):
        raise JobPilotAPIError("请求体必须是 JSON 对象")
    matcher_path = (
        _resolve_project_file(str(payload["matcher_json"]))
        if payload.get("matcher_json")
        else find_latest_jobs(PROJECT_ROOT)
    )
    limits_path = (
        _resolve_project_file(str(payload["limits_json"]))
        if payload.get("limits_json")
        else DEFAULT_FILTER_LIMITS
    )
    output_root = (
        _resolve_project_directory(str(payload["output_dir"]), create=True)
        if payload.get("output_dir")
        else DEFAULT_FILTER_OUTPUT_ROOT
    )
    builder = FilterBuilder.from_limit_file(limits_path if limits_path.exists() else None)
    table = json.loads(matcher_path.read_text(encoding="utf-8"))
    profile_id = str(table.get("profile_id") or "unknown") if isinstance(table, dict) else "unknown"
    html_path = filter_output_path(output_root, profile_id)
    data = builder.build_file(matcher_path, html_path)
    update_filter_manifest(output_root, html_path, data)
    return {
        "schema_version": "1.0",
        "data": {
            "filter_id": data["filter_id"],
            "profile_id": data["profile_id"],
            "summary": data["summary"],
            "html_path": str(html_path),
        },
        "meta": {
            "processing_mode": "local_html_generation",
            "external_network_called": False,
            "matcher_json": str(matcher_path),
            "limits_json": str(limits_path) if limits_path.exists() else None,
        },
    }


def build_filler_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Create local application drafts. The API never opens a browser or transmits profile data."""
    if not isinstance(payload, dict):
        raise JobPilotAPIError("请求体必须是 JSON 对象")
    if not payload.get("selected_jobs_json"):
        raise JobPilotAPIError("必须提供 filter 导出的 selected_jobs_json")
    profile_path = (
        _resolve_project_file(str(payload["profile_json"]))
        if payload.get("profile_json")
        else find_latest_fill_profile(PROJECT_ROOT)
    )
    selected_jobs_path = _resolve_project_file(str(payload["selected_jobs_json"]))
    official_sites_path = (
        _resolve_project_file(str(payload["official_sites_json"]))
        if payload.get("official_sites_json")
        else DEFAULT_OFFICIAL_SITES
    )
    output_root = (
        _resolve_project_directory(str(payload["output_dir"]), create=True)
        if payload.get("output_dir")
        else DEFAULT_FILLER_OUTPUT_ROOT
    )
    profile = load_fill_profile(profile_path)
    selected_jobs = load_selected_jobs(selected_jobs_path)
    plan = FillPlanner(load_official_sites(official_sites_path)).build(
        profile,
        selected_jobs,
        profile_path=profile_path,
        selected_jobs_path=selected_jobs_path,
    )
    run_dir = save_fill_plan(plan, output_root)
    return {
        "schema_version": "1.0",
        "data": {
            "plan_id": plan.plan_id,
            "profile_id": plan.profile_id,
            "summary": plan.to_dict()["summary"],
            "run_dir": str(run_dir),
            "fill_plan_json": str(run_dir / "fill-plan.json"),
        },
        "meta": {
            "processing_mode": "local_draft_only",
            "external_network_called": False,
            "browser_opened": False,
            "personal_data_transmitted": False,
            "automatic_submit": False,
            "official_sites_json": str(official_sites_path),
        },
    }


class JobPilotRequestHandler(BaseHTTPRequestHandler):
    server_version = "JobPilotLocalAPI/0.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/jobpilot/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "model_call_default": False,
                    "online_sources_default": False,
                    "browser_fill_default": False,
                    "service": "jobpilot-local-api",
                },
            )
            return
        if path == "/jobpilot/questionnaire":
            self._send_json(HTTPStatus.OK, questionnaire_response())
            return
        if path == "/jobpilot/openapi.json":
            with (Path(__file__).parent / "openapi.json").open(encoding="utf-8") as stream:
                self._send_json(HTTPStatus.OK, json.load(stream))
            return
        self._send_error(HTTPStatus.NOT_FOUND, "接口不存在")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlparse(self.path).path.rstrip("/")
        if path not in {"/jobpilot/profile", "/jobpilot/match", "/jobpilot/filter", "/jobpilot/filler"}:
            self._send_error(HTTPStatus.NOT_FOUND, "接口不存在")
            return
        try:
            payload = self._read_json_body()
            if path == "/jobpilot/profile":
                result = build_profile_request(payload)
            elif path == "/jobpilot/match":
                result = build_match_request(payload)
            elif path == "/jobpilot/filter":
                result = build_filter_request(payload)
            else:
                result = build_filler_request(payload)
        except JobPilotAPIError as exc:
            self._send_error(exc.status, str(exc))
            return
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_json(HTTPStatus.OK, result)

    def _read_json_body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise JobPilotAPIError("Content-Type 必须是 application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise JobPilotAPIError("Content-Length 无效") from exc
        if content_length <= 0:
            raise JobPilotAPIError("请求体不能为空")
        if content_length > MAX_REQUEST_BYTES:
            raise JobPilotAPIError("请求体超过 1MB 限制", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JobPilotAPIError("请求体不是有效的 UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise JobPilotAPIError("请求体必须是 JSON 对象")
        return payload

    def _send_error(self, status: int | HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": {"status": int(status), "message": message}})

    def _send_json(self, status: int | HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Keep standard server logs concise and avoid logging request bodies.
        super().log_message(format, *args)


def create_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), JobPilotRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JobPilot 本地 API（默认不调用外部模型）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args(argv)
    server = create_server(args.host, args.port)
    print(f"JobPilot API: http://{args.host}:{server.server_port}/jobpilot")
    print("默认处理模式: rules_only（不会调用外部模型）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _find_latest_resume() -> Path:
    candidates = [path for root in DEFAULT_RESUME_ROOTS for path in root.glob("*/resume.json")]
    if not candidates:
        raise JobPilotAPIError("未找到第一组件生成的 resume.json", HTTPStatus.NOT_FOUND)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _resolve_project_file(value: str) -> Path:
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise JobPilotAPIError("只允许读取 JobPilot 项目目录内的文件")
    if not path.is_file():
        raise JobPilotAPIError(f"文件不存在: {path}", HTTPStatus.NOT_FOUND)
    return path


def _resolve_project_directory(value: str, *, create: bool = False) -> Path:
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise JobPilotAPIError("只允许使用 JobPilot 项目目录内的输出目录")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise JobPilotAPIError(f"目录不存在: {path}")
    return path


def _load_profile(path: Path) -> UserProfile:
    with path.open(encoding="utf-8") as stream:
        return UserProfile.from_dict(json.load(stream))


if __name__ == "__main__":
    raise SystemExit(main())
