from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .storage import save_fill_report


class BrowserDependencyError(RuntimeError):
    pass


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-:：*（）()]+", "", value or "").casefold()


def _descriptor_score(field: dict[str, Any], descriptor: dict[str, Any]) -> int:
    values = [
        descriptor.get("label", ""), descriptor.get("ariaLabel", ""), descriptor.get("placeholder", ""),
        descriptor.get("name", ""), descriptor.get("id", ""),
    ]
    normalized_values = [_normalize(str(value)) for value in values if value]
    aliases = [_normalize(str(value)) for value in field.get("aliases", []) if value]
    key = _normalize(str(field.get("key", "")))
    best = 0
    for value in normalized_values:
        if value == key:
            best = max(best, 110)
        for alias in aliases:
            if value == alias:
                best = max(best, 100)
            elif len(alias) >= 4 and alias in value:
                best = max(best, 70)
    return best


def match_fields(fields: list[dict[str, Any]], descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure matching function kept separate so it can be tested without a browser."""
    matches: list[dict[str, Any]] = []
    used: set[int] = set()
    for field in fields:
        ranked = sorted(
            ((index, _descriptor_score(field, item)) for index, item in enumerate(descriptors) if index not in used),
            key=lambda pair: pair[1],
            reverse=True,
        )
        if not ranked or ranked[0][1] < 70:
            matches.append({"key": field["key"], "status": "not_found"})
            continue
        top_score = ranked[0][1]
        tied = [index for index, score in ranked if score == top_score]
        if len(tied) > 1:
            matches.append({"key": field["key"], "status": "ambiguous", "candidate_indexes": tied})
            continue
        index = ranked[0][0]
        used.add(index)
        matches.append({"key": field["key"], "status": "matched", "descriptor_index": index})
    return matches


def execute_plan(
    plan: dict[str, Any],
    *,
    run_dir: Path,
    browser_profile: Path,
    headless: bool = False,
    save_remote_draft: bool = True,
    input_func: Callable[[str], str] = input,
) -> list[Path]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserDependencyError(
            "浏览器执行需要 Playwright：pip install -e 'filler[browser]' && playwright install chromium"
        ) from exc

    report_paths: list[Path] = []
    browser_profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(browser_profile.resolve()), headless=headless
        )
        try:
            for application in plan.get("applications", []):
                if not application.get("application_url"):
                    continue
                page = context.new_page()
                try:
                    page.goto(application["application_url"], wait_until="domcontentloaded")
                except Exception as exc:
                    report_paths.append(
                        save_fill_report(run_dir, _skipped_report(application, f"官方招聘入口打开失败: {type(exc).__name__}"))
                    )
                    page.close()
                    continue
                official_host = urlparse(application["application_url"]).hostname or application["application_url"]
                ready = input_func(
                    f"已打开 {application.get('company')} 官方招聘入口 {official_host}。请在浏览器中手动登录，"
                    f"搜索“{application.get('title')}”，点击申请并进入实际填表页。完成后输入 "
                    f"READY {application['draft_id']}；其他输入将跳过："
                ).strip()
                if ready != f"READY {application['draft_id']}":
                    report_paths.append(save_fill_report(run_dir, _skipped_report(application, "用户未确认已进入填表页")))
                    page.close()
                    continue

                _install_submission_guard(page)
                fields = application.get("fields", [])
                descriptors, locator = _collect_descriptors(page)
                matches = match_fields(fields, descriptors)
                matched_count = sum(item["status"] == "matched" for item in matches)
                retry = 0
                while matched_count == 0 and retry < 5:
                    answer = input_func(
                        f"当前页面没有识别到可填写字段。请继续在浏览器进入申请表，然后输入 "
                        f"RETRY {application['draft_id']}；其他输入将跳过："
                    ).strip()
                    if answer != f"RETRY {application['draft_id']}":
                        break
                    retry += 1
                    descriptors, locator = _collect_descriptors(page)
                    matches = match_fields(fields, descriptors)
                    matched_count = sum(item["status"] == "matched" for item in matches)
                if matched_count == 0:
                    report_paths.append(save_fill_report(run_dir, _skipped_report(application, "填表页没有可明确匹配的字段")))
                    page.close()
                    continue

                current_url = page.url
                current_host = urlparse(current_url).hostname or current_url
                matched_keys = [item["key"] for item in matches if item["status"] == "matched"]
                answer = input_func(
                    f"将在 {current_host} 真实填入 {matched_count} 个字段（{', '.join(matched_keys)}）。"
                    f"这会把个人信息发送给该网站；输入 FILL {application['draft_id']} 才会执行："
                ).strip()
                if answer != f"FILL {application['draft_id']}":
                    report_paths.append(save_fill_report(run_dir, _skipped_report(application, "用户未确认敏感信息发送")))
                    page.close()
                    continue

                field_by_key = {item["key"]: item for item in fields}
                audit: list[dict[str, Any]] = []
                for match in matches:
                    if match["status"] != "matched":
                        audit.append(match)
                        continue
                    descriptor = descriptors[match["descriptor_index"]]
                    if descriptor.get("disabled") or descriptor.get("readOnly"):
                        audit.append({"key": match["key"], "status": "not_editable"})
                        continue
                    field = field_by_key[match["key"]]
                    element = locator.nth(match["descriptor_index"])
                    try:
                        if descriptor.get("tag") == "select":
                            options = element.locator("option").all_text_contents()
                            wanted = _normalize(field["value"])
                            selected = next((text for text in options if wanted in _normalize(text) or _normalize(text) in wanted), None)
                            if not selected:
                                audit.append({"key": match["key"], "status": "option_not_found"})
                                continue
                            element.select_option(label=selected)
                            actual = element.input_value()
                        else:
                            element.fill(str(field["value"]))
                            actual = element.input_value()
                        status = "filled_verified" if actual else "filled_unverified"
                        audit.append({"key": match["key"], "status": status})
                    except Exception as exc:
                        audit.append({"key": match["key"], "status": "fill_error", "error": type(exc).__name__})

                remote_saved = False
                remote_save_status = "not_requested"
                if save_remote_draft:
                    save_answer = input_func(
                        f"将尝试点击 {current_host} 的“保存草稿/暂存”，这会在网站账户中保存个人信息。"
                        f"输入 SAVE {application['draft_id']} 才会继续："
                    ).strip()
                    if save_answer == f"SAVE {application['draft_id']}":
                        buttons = page.get_by_role("button", name=re.compile(r"^\s*(保存草稿|暂存)\s*$"))
                        if buttons.count() == 1:
                            buttons.click()
                            page.wait_for_timeout(800)
                            confirmations = page.get_by_text(
                                re.compile(r"^(草稿已保存|保存成功|已保存|draft saved|saved)$", re.IGNORECASE),
                                exact=True,
                            )
                            if confirmations.count() and confirmations.first.is_visible():
                                remote_saved = True
                                remote_save_status = "confirmed_by_page"
                            else:
                                confirm_answer = input_func(
                                    f"已点击保存控件。请查看页面保存结果；确认成功后输入 "
                                    f"SAVED {application['draft_id']}，其他输入会记录为未确认："
                                ).strip()
                                remote_saved = confirm_answer == f"SAVED {application['draft_id']}"
                                remote_save_status = "confirmed_by_user" if remote_saved else "clicked_unverified"
                        else:
                            remote_save_status = "exact_save_control_not_found"
                    else:
                        remote_save_status = "user_declined"
                report = {
                    "schema_version": "1.0",
                    "component": "filler",
                    "draft_id": application["draft_id"],
                    "filled_at": datetime.now(timezone.utc).isoformat(),
                    "application_url": application["application_url"],
                    "final_form_url": current_url,
                    "remote_draft_saved": remote_saved,
                    "remote_save_status": remote_save_status,
                    "automatic_submit": False,
                    "fields": audit,
                }
                report_paths.append(save_fill_report(run_dir, report))
                if not headless:
                    input_func("请在浏览器中检查已填内容；按回车关闭该页面并继续。")
                page.close()
        finally:
            context.close()
    return report_paths


_FIELD_SELECTOR = (
    "input:not([type=hidden]):not([type=password]):not([type=file]):not([type=submit]):"
    "not([type=button]):not([type=checkbox]):not([type=radio]), textarea, select"
)


def _collect_descriptors(page: Any) -> tuple[list[dict[str, Any]], Any]:
    locator = page.locator(_FIELD_SELECTOR)
    descriptors = locator.evaluate_all(
        """elements => elements.map((el, index) => ({
          index, tag: el.tagName.toLowerCase(), type: el.type || '', name: el.name || '', id: el.id || '',
          placeholder: el.placeholder || '', ariaLabel: el.getAttribute('aria-label') || '',
          label: (el.labels && el.labels.length ? Array.from(el.labels).map(x => x.innerText).join(' ') : ''),
          disabled: Boolean(el.disabled), readOnly: Boolean(el.readOnly)
        }))"""
    )
    return descriptors, locator


def _install_submission_guard(page: Any) -> None:
    page.evaluate(
        """() => {
          const safe = /^(保存草稿|暂存)$/;
          const dangerous = /^(提交|提交申请|立即申请|确认投递|投递)$/;
          document.addEventListener('submit', event => {
            const el = event.submitter;
            const text = ((el && (el.innerText || el.value || el.getAttribute('aria-label'))) || '').trim();
            if (!safe.test(text)) {
              event.preventDefault(); event.stopImmediatePropagation();
              window.__jobpilotSubmitBlocked = true;
            }
          }, true);
          document.addEventListener('click', event => {
            const el = event.target && event.target.closest && event.target.closest('button,input[type=submit]');
            const text = ((el && (el.innerText || el.value || el.getAttribute('aria-label'))) || '').trim();
            if (dangerous.test(text)) {
              event.preventDefault(); event.stopImmediatePropagation();
              window.__jobpilotSubmitBlocked = true;
            }
          }, true);
        }"""
    )


def _skipped_report(application: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "component": "filler",
        "draft_id": application["draft_id"],
        "filled_at": datetime.now(timezone.utc).isoformat(),
        "application_url": application.get("application_url", ""),
        "status": "skipped",
        "reason": reason,
        "remote_draft_saved": False,
        "automatic_submit": False,
        "fields": [],
    }
