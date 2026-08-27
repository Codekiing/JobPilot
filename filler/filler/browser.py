from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .storage import save_fill_report


class BrowserDependencyError(RuntimeError):
    pass


_SELECT_FIELD_KEYS = {"highest_degree", "preferred_locations"}
_MULTI_VALUE_FIELD_KEYS = {"preferred_locations", "languages"}


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-:：*（）()]+", "", value or "").casefold()


def _descriptor_score(field: dict[str, Any], descriptor: dict[str, Any]) -> int:
    if descriptor.get("visible") is False or descriptor.get("disabled") or descriptor.get("readOnly"):
        return 0
    values = [
        descriptor.get("label", ""), descriptor.get("ariaLabel", ""), descriptor.get("placeholder", ""),
        descriptor.get("name", ""), descriptor.get("id", ""), descriptor.get("contextText", ""),
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
    if field.get("key") in _SELECT_FIELD_KEYS and (
        descriptor.get("tag") == "select" or descriptor.get("role") == "combobox"
    ):
        best += 15
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


def _value_parts(field: dict[str, Any]) -> list[str]:
    value = str(field.get("value") or "").strip()
    if not value:
        return []
    if field.get("key") not in _MULTI_VALUE_FIELD_KEYS:
        return [value]
    return list(dict.fromkeys(part.strip() for part in re.split(r"[、,，|；;\n]+", value) if part.strip()))


def _option_index(options: list[str], wanted: str) -> int | None:
    normalized = _normalize(wanted)
    exact = [index for index, text in enumerate(options) if _normalize(text) == normalized]
    if len(exact) == 1:
        return exact[0]
    partial = [
        index for index, text in enumerate(options)
        if normalized in _normalize(text) or _normalize(text) in normalized
    ]
    return partial[0] if len(partial) == 1 else None


def _fill_native_select(element: Any, field: dict[str, Any]) -> str:
    options = element.locator("option").all_text_contents()
    selected: list[str] = []
    for wanted in _value_parts(field):
        index = _option_index(options, wanted)
        if index is None:
            return "option_not_found"
        selected.append(options[index])
    if not selected:
        return "empty_value"
    if element.get_attribute("multiple") is not None:
        element.select_option(label=selected)
    else:
        element.select_option(label=selected[0])
    return "filled_verified" if element.input_value() else "filled_unverified"


def _fill_custom_select(page: Any, element: Any, field: dict[str, Any]) -> str:
    wanted_values = _value_parts(field)
    if not wanted_values:
        return "empty_value"
    selected_count = 0
    for wanted in wanted_values:
        element.click()
        page.wait_for_timeout(100)
        options = page.get_by_role("option")
        texts = options.all_text_contents()
        index = _option_index(texts, wanted)
        if index is None:
            return "option_not_found"
        options.nth(index).click()
        selected_count += 1
        if field.get("key") not in _MULTI_VALUE_FIELD_KEYS:
            break
    return "filled_verified" if selected_count else "filled_unverified"


def _set_controlled_value(element: Any, value: str) -> str:
    element.fill(value)
    actual = element.input_value()
    if actual or not value:
        return actual
    element.press_sequentially(value)
    actual = element.input_value()
    if actual:
        return actual
    # Some React-controlled fields discard Playwright's regular fill events.
    # Use the native value setter as a final standards-based event fallback.
    element.evaluate(
        """(el, value) => {
          const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
          if (setter) setter.call(el, value); else el.value = value;
          el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )
    return element.input_value()


def _fill_control(page: Any, element: Any, descriptor: dict[str, Any], field: dict[str, Any]) -> str:
    if descriptor.get("tag") == "select":
        return _fill_native_select(element, field)
    if descriptor.get("role") == "combobox":
        if field.get("key") == "preferred_locations" and page.locator(
            'input[id="application_preferred_city_list"]'
        ).count():
            values = _value_parts(field)
            return _atsx_select_location(page, values[0]) if values else "empty_value"
        return _fill_custom_select(page, element, field)
    actual = _set_controlled_value(element, str(field.get("value") or ""))
    return "filled_verified" if actual else "filled_unverified"


def _atsx_id(page: Any, control_id: str) -> Any:
    return page.locator(f'input[id="{control_id}"], textarea[id="{control_id}"]')


def _atsx_fill_text(page: Any, control_id: str, value: str) -> str:
    control = _atsx_id(page, control_id)
    if control.count() != 1 or not control.is_visible():
        return "not_found"
    actual = _set_controlled_value(control, value)
    control.press("Tab")
    return "filled_verified" if control.input_value().strip() == value.strip() else "filled_unverified"


def _atsx_select(page: Any, control_id: str, value: str, *, searchable: bool = False) -> str:
    hidden_or_search = page.locator(f'input[id="{control_id}"]')
    if hidden_or_search.count() != 1:
        return "not_found"
    owner = hidden_or_search.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' atsx-select ')][1]")
    combo = owner.locator('[role="combobox"]')
    if combo.count() != 1:
        return "not_found"
    combo.click()
    if searchable and hidden_or_search.is_visible():
        hidden_or_search.fill("")
        hidden_or_search.press_sequentially(value)
        page.wait_for_timeout(400)
    options = page.get_by_role("option")
    texts = options.all_text_contents()
    index = _option_index(texts, value)
    if index is None and searchable:
        visible_text = page.get_by_text(value, exact=True)
        if visible_text.count() == 1 and visible_text.is_visible():
            visible_text.click()
            return "filled_verified"
        return "option_not_found"
    if index is None:
        return "option_not_found"
    options.nth(index).click()
    displayed = combo.inner_text().strip()
    return "filled_verified" if value in displayed or displayed in value else "filled_unverified"


def _atsx_select_location(page: Any, value: str) -> str:
    city_input = page.locator('input[id="application_preferred_city_list"]')
    if city_input.count() == 0:
        return "not_found"
    owner = city_input.first.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' atsx-select ')][1]")
    combo = owner.locator('[role="combobox"]')
    if combo.count() != 1:
        return "not_found"
    combo.click()
    item = page.get_by_role("treeitem", name=value, exact=True)
    if item.count() != 1:
        return "option_not_found"
    item.locator(".atsx-tree-node-content-wrapper").click()
    page.locator("#name").click()
    return "filled_verified" if value in combo.inner_text() else "filled_unverified"


def _atsx_fill_period(page: Any, prefix: str, start: str, end: str) -> str:
    if not start or not end:
        return "empty_value"
    for suffix, value in (("Begin", start), ("End", end)):
        try:
            year, month = value.split("-", 1)
        except ValueError:
            return "invalid_period"
        label = page.locator(f'[data-cy="{prefix}.periodInput{suffix}"]')
        if label.count() != 1:
            return "not_found"
        label.click()
        panel = page.locator(f'[data-cy="{prefix}.periodInput{suffix}Dropdown"]')
        if panel.count() != 1:
            return "not_found"
        year_option = panel.locator(f'[data-cy="{year}"]')
        month_option = panel.locator(f'[data-cy="{month}"]')
        if year_option.count() != 1 or month_option.count() != 1:
            return "option_not_found"
        year_option.click()
        month_option.click()
    begin_text = page.locator(f'[data-cy="{prefix}.periodInputBegin"]').inner_text()
    end_text = page.locator(f'[data-cy="{prefix}.periodInputEnd"]').inner_text()
    return "filled_verified" if start in begin_text and end in end_text else "filled_unverified"


def _atsx_add_record(page: Any, section_index: int) -> None:
    adds = page.locator(".addMore-add")
    if adds.count() > section_index:
        adds.nth(section_index).click()
        page.wait_for_timeout(100)


def _fill_atsx_structured(page: Any, records: dict[str, Any]) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    education = records.get("education", []) if isinstance(records, dict) else []
    for index, record in enumerate(education):
        if index and _atsx_id(page, f"education[{index}].fieldOfStudy").count() == 0:
            _atsx_add_record(page, 0)
        for key, status in (
            ("school", _atsx_select(page, f"education[{index}].school", record.get("school", ""), searchable=True)),
            ("degree", _atsx_select(page, f"education[{index}].degree", record.get("degree", ""))),
            ("major", _atsx_fill_text(page, f"education[{index}].fieldOfStudy", record.get("major", ""))),
            ("period", _atsx_fill_period(page, f"education[{index}]", record.get("start", ""), record.get("end", ""))),
        ):
            audit.append({"key": f"education[{index}].{key}", "status": status, "control": "atsx"})

    internships = records.get("internship", []) if isinstance(records, dict) else []
    if internships:
        no_work = page.get_by_role("checkbox", name=re.compile("没有工作经历"))
        if no_work.count() == 1 and not no_work.is_checked():
            no_work.check()
            audit.append({"key": "career.none", "status": "filled_verified", "control": "atsx"})
    for index, record in enumerate(internships):
        if _atsx_id(page, f"internship[{index}].company").count() == 0:
            _atsx_add_record(page, 1)
        for key, status in (
            ("company", _atsx_fill_text(page, f"internship[{index}].company", record.get("company", ""))),
            ("title", _atsx_fill_text(page, f"internship[{index}].title", record.get("title", ""))),
            ("period", _atsx_fill_period(page, f"internship[{index}]", record.get("start", ""), record.get("end", ""))),
            ("description", _atsx_fill_text(page, f"internship[{index}].desc", record.get("description", ""))),
        ):
            audit.append({"key": f"internship[{index}].{key}", "status": status, "control": "atsx"})

    projects = records.get("projects", []) if isinstance(records, dict) else []
    for index, record in enumerate(projects):
        if _atsx_id(page, f"project[{index}].name").count() == 0:
            _atsx_add_record(page, 2)
        for key, status in (
            ("name", _atsx_fill_text(page, f"project[{index}].name", record.get("name", ""))),
            ("description", _atsx_fill_text(page, f"project[{index}].desc", record.get("description", ""))),
        ):
            audit.append({"key": f"project[{index}].{key}", "status": status, "control": "atsx"})
    return audit


def _upload_resume(
    page: Any,
    resume_file: str | None,
    application: dict[str, Any],
    current_host: str,
    input_func: Callable[[str], str],
) -> tuple[bool, str]:
    if not resume_file:
        return False, "not_configured"
    path = Path(resume_file).expanduser().resolve()
    if not path.is_file():
        return False, "file_missing"
    inputs = page.locator('input[type="file"]')
    if inputs.count() == 0:
        return False, "file_control_not_found"
    if inputs.count() > 1:
        return False, "ambiguous_file_controls"
    answer = input_func(
        f"将在 {current_host} 上传简历附件 {path.name}；这会把文件发送给招聘网站。"
        f"输入 UPLOAD {application['draft_id']} 才会执行："
    ).strip()
    if answer != f"UPLOAD {application['draft_id']}":
        return False, "user_declined"
    control = inputs.first
    try:
        control.set_input_files(str(path))
        return bool(control.input_value()), "uploaded_verified" if control.input_value() else "uploaded_unverified"
    except Exception as exc:
        return False, f"upload_error:{type(exc).__name__}"


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
    shared_fields = plan.get("fields", [])
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
                # Current plans store common profile fields once. The fallback
                # keeps previously generated application-level plans executable.
                fields = application.get("fields") or shared_fields
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
                structured = plan.get("structured_records", {}) if application.get("adapter") == "atsx" else {}
                structured_summary = ", ".join(
                    f"{key}={len(value)}"
                    for key, value in structured.items()
                    if isinstance(value, list) and value
                )
                answer = input_func(
                    f"将在 {current_host} 真实填入 {matched_count} 个字段（{', '.join(matched_keys)}）"
                    f"{f'，并填入结构化记录（{structured_summary}）' if structured_summary else ''}。"
                    f"这会把个人信息发送给该网站；输入 FILL {application['draft_id']} 才会执行："
                ).strip()
                if answer != f"FILL {application['draft_id']}":
                    report_paths.append(save_fill_report(run_dir, _skipped_report(application, "用户未确认敏感信息发送")))
                    page.close()
                    continue

                # Upload first because many ATS products parse the resume and
                # overwrite form fields asynchronously. Explicit profile data
                # is applied afterwards and therefore remains authoritative.
                resume_uploaded, resume_upload_status = _upload_resume(
                    page,
                    plan.get("resume_file"),
                    application,
                    current_host,
                    input_func,
                )
                if resume_uploaded:
                    page.wait_for_timeout(1200)
                    if application.get("adapter") == "atsx":
                        parse_action = page.get_by_text("解析并覆盖", exact=True)
                        if parse_action.count() == 1 and parse_action.is_visible():
                            parse_action.click()
                            page.wait_for_timeout(1200)
                            resume_upload_status = "uploaded_parsed"

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
                        audit.append({
                            "key": match["key"],
                            "status": _fill_control(page, element, descriptor, field),
                            "control": descriptor.get("control", descriptor.get("tag", "unknown")),
                        })
                    except Exception as exc:
                        audit.append({"key": match["key"], "status": "fill_error", "error": type(exc).__name__})

                if application.get("adapter") == "atsx":
                    try:
                        audit.extend(_fill_atsx_structured(page, plan.get("structured_records", {})))
                    except Exception as exc:
                        audit.append({"key": "structured_records", "status": "fill_error", "error": type(exc).__name__})

                remote_saved = False
                remote_save_status = "not_requested"
                if save_remote_draft and application.get("adapter") == "atsx":
                    # The ATSX application page used by SenseTime exposes no
                    # draft-save action and a second authenticated tab does not
                    # restore unsent fields. Do not misreport an open tab as a
                    # remotely persisted draft.
                    remote_save_status = "site_draft_unsupported"
                elif save_remote_draft:
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
                    "resume_uploaded": resume_uploaded,
                    "resume_upload_status": resume_upload_status,
                    "resume_file_name": Path(plan["resume_file"]).name if plan.get("resume_file") else None,
                    "automatic_submit": False,
                    "fields": audit,
                }
                report_paths.append(save_fill_report(run_dir, report))
                if not headless:
                    message = "请在浏览器中检查已填内容；按回车关闭该页面并继续。"
                    if remote_save_status == "site_draft_unsupported":
                        message = (
                            "该网站不支持远程草稿，当前已填页面仅在本次浏览器会话中保留。"
                            "请完成检查后再按回车关闭。"
                        )
                    input_func(message)
                page.close()
        finally:
            context.close()
    return report_paths


_FIELD_SELECTOR = (
    "input:not([type=hidden]):not([type=password]):not([type=file]):not([type=submit]):"
    "not([type=button]):not([type=checkbox]):not([type=radio]), textarea, select, [role=combobox]"
)


def _collect_descriptors(page: Any) -> tuple[list[dict[str, Any]], Any]:
    locator = page.locator(_FIELD_SELECTOR)
    descriptors = locator.evaluate_all(
        r"""elements => elements.map((el, index) => {
          const labelledBy = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)
            .map(id => document.getElementById(id)?.innerText || '').join(' ');
          const owner = el.closest('[class*=form-item], [class*=formItem], [class*=field], [class*=control]');
          const contextText = owner?.querySelector('label, [class*=label]')?.innerText || '';
          const role = el.getAttribute('role') || '';
          const controlId = el.id || el.closest('[id]')?.id || '';
          return {
            index, tag: el.tagName.toLowerCase(), type: el.type || '', role,
            control: el.tagName.toLowerCase() === 'select' ? 'native_select' : (role === 'combobox' ? 'custom_select' : 'text'),
            name: el.name || '', id: controlId, placeholder: el.placeholder || '',
            ariaLabel: el.getAttribute('aria-label') || labelledBy,
            label: (el.labels && el.labels.length ? Array.from(el.labels).map(x => x.innerText).join(' ') : ''),
            contextText: contextText.slice(0, 160),
            visible: Boolean(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
            disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
            readOnly: Boolean(el.readOnly),
            multiple: Boolean(el.multiple || el.getAttribute('aria-multiselectable') === 'true')
          };
        })"""
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
        "resume_uploaded": False,
        "resume_upload_status": "not_attempted",
        "automatic_submit": False,
        "fields": [],
    }
