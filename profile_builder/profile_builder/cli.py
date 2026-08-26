from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .builder import ProfileBuilder
from .completion import calculate_completion
from .enrichment import ProfileEnricher
from .model_enricher import OpenAIProfileEnricher
from .models import UserProfile
from .storage import save_profile
from .survey import SimpleSurvey


COMPONENT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = COMPONENT_ROOT.parent
DEFAULT_RESUME_ROOTS = (PROJECT_ROOT / "extractor" / "outputs",)
DEFAULT_OUTPUT_ROOT = COMPONENT_ROOT / "outputs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="基于简历拆解结果建立岗位匹配用户画像")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--resume-json", help="第一组件生成的 resume.json；省略时自动查找最新结果")
    source.add_argument("--profile", help="继续完善已有 profile.json")
    parser.add_argument("-o", "--output-dir", default=str(DEFAULT_OUTPUT_ROOT), help="输出目录")
    parser.add_argument("--draft", action="store_true", help="仅生成画像草稿和简版问卷，不进入交互")
    parser.add_argument("--answers", help="从 JSON 文件导入简版问卷答案")
    parser.add_argument("--list-questions", action="store_true", help="打印12道简版问卷题目")
    parser.add_argument("--use-model", action="store_true", help="规则处理后，调用模型补充仍缺失的字段")
    parser.add_argument("--model", default=os.environ.get("JOBPILOT_PROFILE_MODEL"), help="Responses API 模型名称；也可设置 JOBPILOT_PROFILE_MODEL")
    parser.add_argument("--api-base", default=os.environ.get("OPENAI_BASE_URL"), help="OpenAI 兼容 API 基地址")
    parser.add_argument("--json", action="store_true", help="向标准输出打印完整用户画像 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    survey = SimpleSurvey()
    enricher = ProfileEnricher()
    try:
        if args.profile:
            profile = _load_profile(Path(args.profile))
        else:
            resume_json = Path(args.resume_json).expanduser().resolve() if args.resume_json else _find_latest_resume()
            profile = ProfileBuilder().build_from_file(resume_json)

        existing_answers = {
            question_id: str(record.get("value", ""))
            for question_id, record in profile.questionnaire.get("survey_answers", {}).items()
            if isinstance(record, dict) and record.get("value")
        }
        survey_answers = dict(existing_answers)
        if args.answers:
            with Path(args.answers).expanduser().open(encoding="utf-8") as stream:
                payload = json.load(stream)
            answers = payload.get("survey_answers", payload.get("answers", payload))
            if not isinstance(answers, dict):
                raise ValueError("答案文件必须是 JSON 对象，或包含 survey_answers 对象")
            valid_ids = {question.id for question in survey.questions()}
            unknown = set(answers) - valid_ids
            if unknown:
                raise ValueError(f"未知的简版问卷题号: {', '.join(sorted(unknown))}")
            survey_answers.update({key: str(value) for key, value in answers.items() if str(value).strip()})

        interactive = not args.draft and sys.stdin.isatty()
        if interactive:
            survey_answers = survey.collect_interactively(profile, previous_answers=survey_answers)

        model_enricher = None
        if args.use_model:
            if not survey_answers:
                raise ValueError("调用模型前至少需要一条问卷答案")
            model_enricher = OpenAIProfileEnricher(
                args.model or "",
                base_url=args.api_base,
            )
        if survey_answers:
            profile = enricher.enrich(profile, survey_answers, model_enricher=model_enricher)
        else:
            profile.completion = calculate_completion(profile)

        questions = survey.questions()
        saved_to = save_profile(profile, questions, args.output_dir)
        if args.list_questions:
            for question in questions:
                marker = "必填" if question.required else "建议"
                print(f"[{marker}] {question.id} / {question.angle}: {question.prompt}")
        if args.json:
            print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(f"[ok] 用户画像 -> {saved_to}")
            answered_count = len(profile.questionnaire.get("survey_answers", {}))
            print(
                f"完成度 {profile.completion['score']}%，"
                f"岗位匹配就绪={'是' if profile.completion['match_ready'] else '否'}，"
                f"问卷已答 {answered_count}/12"
            )
            if not interactive and not args.draft:
                print("[warning] 当前不是交互终端，已自动生成草稿；请在终端运行以进入问询")
        return 0
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


def _find_latest_resume() -> Path:
    candidates = [path for root in DEFAULT_RESUME_ROOTS for path in root.glob("*/resume.json")]
    if not candidates:
        searched = "、".join(str(root) for root in DEFAULT_RESUME_ROOTS)
        raise FileNotFoundError(f"以下目录没有第一组件的 resume.json: {searched}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_profile(path: Path) -> UserProfile:
    with path.expanduser().open(encoding="utf-8") as stream:
        return UserProfile.from_dict(json.load(stream))


if __name__ == "__main__":
    raise SystemExit(main())
