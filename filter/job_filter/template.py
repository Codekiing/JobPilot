from __future__ import annotations

import json
from typing import Any


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JobPilot 待投递岗位筛选</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --surface-soft: #f8fafc;
      --text: #162033;
      --muted: #64748b;
      --border: #dce3eb;
      --primary: #1769e0;
      --primary-soft: #eaf2ff;
      --success: #087f5b;
      --success-soft: #e7f7f1;
      --warning: #a15c00;
      --warning-soft: #fff4db;
      --danger: #b42318;
      --danger-soft: #fff0ee;
      --shadow: 0 8px 28px rgba(21, 35, 56, .08);
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
    button, input, select { font: inherit; }
    a { color: var(--primary); }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid rgba(23, 105, 224, .28); outline-offset: 2px; }
    .shell { width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 64px; }
    .hero { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 20px; }
    h1 { margin: 0 0 8px; font-size: clamp(24px, 3vw, 36px); letter-spacing: -.03em; }
    .subtitle { margin: 0; color: var(--muted); }
    .summary { display: grid; grid-template-columns: repeat(3, minmax(110px, 1fr)); gap: 10px; min-width: 390px; }
    .metric { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; box-shadow: var(--shadow); }
    .metric-label { color: var(--muted); font-size: 13px; }
    .metric-value { font-size: 24px; font-weight: 650; margin-top: 4px; }
    .notice { border-radius: 12px; padding: 13px 16px; margin-bottom: 16px; background: var(--warning-soft); color: #714100; border: 1px solid #f2d494; }
    .notice strong { display: block; margin-bottom: 4px; }
    .toolbar { position: sticky; top: 0; z-index: 20; display: flex; gap: 12px; flex-wrap: wrap; align-items: end; background: rgba(244, 246, 248, .96); padding: 12px 0; backdrop-filter: blur(10px); }
    .field { display: grid; gap: 6px; }
    .field label { font-size: 13px; color: var(--muted); }
    .field input, .field select { height: 40px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface); color: var(--text); padding: 0 12px; }
    .field-search { flex: 1 1 280px; }
    .field-small { flex: 0 0 150px; }
    .actions { margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }
    .button { min-height: 40px; border-radius: 9px; padding: 8px 14px; border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer; }
    .button:hover:not(:disabled) { border-color: #aab7c7; background: var(--surface-soft); }
    .button-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
    .button-primary:hover:not(:disabled) { background: #0d5bc8; border-color: #0d5bc8; }
    .button-danger { color: var(--danger); }
    .button:disabled { cursor: not-allowed; opacity: .48; }
    .status-line { min-height: 24px; margin: 4px 0 12px; color: var(--muted); }
    .status-line.error { color: var(--danger); }
    .company-list { display: grid; gap: 16px; min-width: 0; }
    .company-card { min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); overflow: clip; }
    .company-head { display: grid; grid-template-columns: 1fr auto; gap: 20px; align-items: center; padding: 18px 20px; border-bottom: 1px solid var(--border); }
    .company-title { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .company-title h2 { margin: 0; font-size: 19px; }
    .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 9px; font-size: 12px; background: var(--surface-soft); color: var(--muted); border: 1px solid var(--border); }
    .badge-ok { color: var(--success); background: var(--success-soft); border-color: #b5e5d5; }
    .badge-warn { color: var(--warning); background: var(--warning-soft); border-color: #f2d494; }
    .badge-reviewed { color: #475569; background: #eef2f6; border-color: #cbd5e1; }
    .company-meta { color: var(--muted); font-size: 13px; margin-top: 6px; }
    .quota-box { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; justify-content: flex-end; }
    .quota-box .field { width: 105px; }
    .quota-help { width: 100%; text-align: right; color: var(--muted); font-size: 12px; }
    .table-wrap { min-width: 0; max-width: 100%; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th { text-align: left; font-size: 12px; font-weight: 600; color: var(--muted); background: var(--surface-soft); padding: 10px 12px; border-bottom: 1px solid var(--border); }
    td { padding: 13px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
    tbody tr:last-child td { border-bottom: 0; }
    tbody tr.selected { background: var(--primary-soft); }
    tbody tr.blocked { opacity: .58; }
    .select-cell { width: 62px; text-align: center; }
    .score { font-variant-numeric: tabular-nums; font-weight: 650; white-space: nowrap; }
    .job-title { font-weight: 600; margin-bottom: 5px; }
    .job-sub { color: var(--muted); font-size: 12px; }
    .job-reason { color: var(--muted); font-size: 12px; margin-top: 6px; max-width: 560px; }
    .links { display: flex; gap: 8px; white-space: nowrap; }
    .selected-section { min-width: 0; margin-top: 26px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow); overflow: clip; }
    .selected-head { padding: 18px 20px; border-bottom: 1px solid var(--border); }
    .selected-head h2 { margin: 0 0 5px; font-size: 20px; }
    .empty { padding: 30px; text-align: center; color: var(--muted); }
    .checkbox { width: 18px; height: 18px; accent-color: var(--primary); cursor: pointer; }
    .checkbox:disabled { cursor: not-allowed; }
    .footer-note { margin-top: 20px; color: var(--muted); font-size: 12px; }
    @media (max-width: 900px) {
      .hero { display: block; }
      .summary { min-width: 0; margin-top: 18px; }
      .company-head { grid-template-columns: 1fr; }
      .quota-box { justify-content: flex-start; }
      .quota-help { text-align: left; }
      .actions { margin-left: 0; width: 100%; }
    }
    @media (max-width: 560px) {
      .shell { width: min(100% - 20px, 1440px); padding-top: 18px; }
      .summary { grid-template-columns: 1fr; }
      .toolbar { position: static; }
      .field-small { flex: 1 1 130px; }
      .actions .button { flex: 1 1 auto; }
      .company-head { padding: 15px; }
    }
    @media (prefers-color-scheme: dark) {
      :root { color-scheme: dark; --bg: #0f141c; --surface: #171e28; --surface-soft: #1d2632; --text: #e9eef5; --muted: #9cabbc; --border: #303b49; --primary: #6ca6ff; --primary-soft: #17335b; --success: #60d6ad; --success-soft: #153a31; --warning: #f2bd63; --warning-soft: #3d2d16; --danger: #ff938a; --danger-soft: #47221f; --shadow: 0 8px 28px rgba(0, 0, 0, .22); }
      .button-primary { color: #07111f; }
      .notice { color: #f5cd84; border-color: #664b22; }
      .badge-ok { border-color: #2f6557; }
      .badge-warn { border-color: #664b22; }
      .toolbar { background: rgba(15, 20, 28, .96); }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero" aria-labelledby="page-title">
      <div>
        <h1 id="page-title">待投递岗位筛选</h1>
        <p class="subtitle" id="source-summary"></p>
      </div>
      <div class="summary" aria-label="筛选统计">
        <div class="metric"><div class="metric-label">候选岗位</div><div class="metric-value" id="metric-jobs">0</div></div>
        <div class="metric"><div class="metric-label">已选岗位</div><div class="metric-value" id="metric-selected">0</div></div>
        <div class="metric"><div class="metric-label">待处理限额</div><div class="metric-value" id="metric-unconfirmed">0</div></div>
      </div>
    </section>

    <aside class="notice">
      <strong>投递限额已按当前招聘批次核验。</strong>
      有公开规则的公司直接按规则限制勾选数量；官方公开页面未披露限额的公司会明确标记，并保守按 1 个岗位处理。若在登录后的投递系统看到不同规则，可修改后人工确认。
    </aside>

    <section class="toolbar" aria-label="岗位筛选工具">
      <div class="field field-search"><label for="search">搜索岗位或公司</label><input id="search" type="search" placeholder="输入岗位、公司、城市或技能"></div>
      <div class="field field-small"><label for="source-filter">渠道</label><select id="source-filter"><option value="">全部渠道</option></select></div>
      <div class="field field-small"><label for="score-filter">最低匹配分</label><select id="score-filter"><option value="0">不限</option><option value="50">50+</option><option value="65">65+</option><option value="80">80+</option><option value="90">90+</option></select></div>
      <div class="actions">
        <button class="button" id="reset-selection" type="button">清空选择</button>
        <button class="button" id="export-json" type="button" disabled>导出 JSON</button>
        <button class="button button-primary" id="export-csv" type="button" disabled>导出 CSV</button>
      </div>
    </section>
    <div class="status-line" id="status" role="status" aria-live="polite"></div>
    <section class="company-list" id="company-list" aria-label="按公司分组的候选岗位"></section>

    <section class="selected-section" aria-labelledby="selected-title">
      <div class="selected-head"><h2 id="selected-title">最终待投递岗位表</h2><div class="job-sub">只显示已勾选且未超过已核验规则或保守上限的岗位；导出内容与此处一致。</div></div>
      <div id="selected-table"></div>
    </section>
    <p class="footer-note">选择和限额确认状态仅保存在当前浏览器的本地存储中。打开投递链接后，请再次确认岗位仍在招聘以及公司最新投递规则。</p>
  </main>

  <script id="jobpilot-data" type="application/json">__JOBPILOT_DATA__</script>
  <script>
  (() => {
    'use strict';
    const data = JSON.parse(document.getElementById('jobpilot-data').textContent);
    const storageKey = `jobpilot-filter:${data.filter_id}`;
    const state = { selected: new Set(), quotas: {}, query: '', source: '', minScore: 0 };
    const elements = {
      list: document.getElementById('company-list'),
      selectedTable: document.getElementById('selected-table'),
      status: document.getElementById('status'),
      metricJobs: document.getElementById('metric-jobs'),
      metricSelected: document.getElementById('metric-selected'),
      metricUnconfirmed: document.getElementById('metric-unconfirmed'),
      search: document.getElementById('search'),
      source: document.getElementById('source-filter'),
      score: document.getElementById('score-filter'),
      exportJson: document.getElementById('export-json'),
      exportCsv: document.getElementById('export-csv'),
      reset: document.getElementById('reset-selection')
    };

    const el = (tag, attrs = {}, text = '') => {
      const node = document.createElement(tag);
      Object.entries(attrs).forEach(([key, value]) => {
        if (key === 'class') node.className = value;
        else if (key === 'checked') node.checked = Boolean(value);
        else if (key === 'disabled') node.disabled = Boolean(value);
        else node.setAttribute(key, String(value));
      });
      if (text !== '') node.textContent = text;
      return node;
    };

    const employmentLabel = value => ({ campus: '校园招聘', internship: '实习', full_time: '社会招聘', unknown: '类型未知' }[value] || value);
    const allJobs = data.groups.flatMap(group => group.jobs.map(job => ({ ...job, groupId: group.group_id })));
    const jobByKey = new Map(allJobs.map(job => [job.job_key, job]));
    const groupById = new Map(data.groups.map(group => [group.group_id, group]));

    function initialQuota(group) {
      return { limit: group.quota.limit, confirmed: group.quota.confirmed, verificationStatus: group.quota.verification_status || (group.quota.confirmed ? 'confirmed' : 'unverified') };
    }
    data.groups.forEach(group => { state.quotas[group.group_id] = initialQuota(group); });

    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved && Array.isArray(saved.selected) && saved.quotas) {
        saved.selected.filter(key => jobByKey.has(key)).forEach(key => state.selected.add(key));
        data.groups.forEach(group => {
          const quota = saved.quotas[group.group_id];
          if (quota && Number.isInteger(quota.limit) && quota.limit > 0) {
            state.quotas[group.group_id] = {
              limit: quota.limit,
              confirmed: Boolean(quota.confirmed),
              verificationStatus: String(quota.verificationStatus || group.quota.verification_status || (quota.confirmed ? 'manually_confirmed' : 'unverified'))
            };
          }
        });
      }
    } catch (_) { localStorage.removeItem(storageKey); }

    function saveState() {
      localStorage.setItem(storageKey, JSON.stringify({ selected: [...state.selected], quotas: state.quotas }));
    }

    function selectedForGroup(group) {
      return group.jobs.filter(job => state.selected.has(job.job_key));
    }

    function selectedGroups() {
      return data.groups.filter(group => selectedForGroup(group).length > 0);
    }

    function quotaResolved(quotaState) {
      return quotaState.confirmed || quotaState.verificationStatus === 'public_not_found';
    }

    function exportReady() {
      return state.selected.size > 0 && selectedGroups().every(group => quotaResolved(state.quotas[group.group_id]));
    }

    function matchesFilter(job) {
      const text = [job.title, job.company, ...job.locations, ...job.matched_skills, job.source].join(' ').toLowerCase();
      return (!state.query || text.includes(state.query)) && (!state.source || job.source === state.source) && job.score >= state.minScore;
    }

    function setStatus(message, error = false) {
      elements.status.textContent = message;
      elements.status.className = `status-line${error ? ' error' : ''}`;
    }

    function quotaBadge(quotaState) {
      if (quotaState.confirmed && quotaState.verificationStatus === 'confirmed') return { className: 'badge badge-ok', label: '规则已核验' };
      if (quotaState.confirmed) return { className: 'badge badge-ok', label: '人工已确认' };
      if (quotaState.verificationStatus === 'public_not_found') return { className: 'badge badge-reviewed', label: '已核查·官方未披露' };
      if (quotaState.verificationStatus === 'stale') return { className: 'badge badge-warn', label: '旧规则未采用' };
      return { className: 'badge badge-warn', label: '限额待确认' };
    }

    function render() {
      elements.list.replaceChildren();
      let visibleJobs = 0;
      data.groups.forEach(group => {
        const jobs = group.jobs.filter(matchesFilter);
        if (!jobs.length) return;
        visibleJobs += jobs.length;
        elements.list.appendChild(renderGroup(group, jobs));
      });
      if (!visibleJobs) elements.list.appendChild(el('div', { class: 'empty' }, '当前筛选条件下没有岗位。'));
      renderSelected();
      updateSummary(visibleJobs);
      saveState();
    }

    function renderGroup(group, jobs) {
      const quotaState = state.quotas[group.group_id];
      const selected = selectedForGroup(group);
      const full = selected.length >= quotaState.limit;
      const card = el('article', { class: 'company-card' });
      const head = el('header', { class: 'company-head' });
      const intro = el('div');
      const titleRow = el('div', { class: 'company-title' });
      titleRow.append(el('h2', {}, group.company), el('span', { class: 'badge' }, employmentLabel(group.employment_type)));
      const badge = quotaBadge(quotaState);
      titleRow.append(el('span', { class: badge.className }, badge.label));
      intro.append(titleRow, el('div', { class: 'company-meta' }, `${group.jobs.length} 个候选岗位 · 已选 ${selected.length}/${quotaState.limit}`));
      head.append(intro, quotaControls(group));
      card.appendChild(head);

      const wrap = el('div', { class: 'table-wrap' });
      const table = el('table');
      const thead = el('thead');
      const hr = el('tr');
      ['选择', '匹配分', '岗位信息', '地点', '薪资', '渠道', '操作'].forEach(label => hr.appendChild(el('th', {}, label)));
      thead.appendChild(hr);
      const tbody = el('tbody');
      jobs.forEach(job => {
        const checked = state.selected.has(job.job_key);
        const disabled = !checked && full;
        const row = el('tr', { class: `${checked ? 'selected' : ''}${disabled ? ' blocked' : ''}`.trim() });
        const selectCell = el('td', { class: 'select-cell' });
        const checkbox = el('input', { class: 'checkbox', type: 'checkbox', 'aria-label': `选择 ${job.company} ${job.title}`, checked, disabled });
        checkbox.addEventListener('change', () => toggleJob(group, job, checkbox.checked));
        selectCell.appendChild(checkbox);
        row.appendChild(selectCell);
        row.appendChild(el('td', { class: 'score' }, `${job.score.toFixed(1)} ${job.grade}`));
        const jobCell = el('td');
        jobCell.append(el('div', { class: 'job-title' }, job.title));
        const detail = [job.education, job.experience, job.employment_type ? employmentLabel(job.employment_type) : ''].filter(Boolean).join(' · ');
        if (detail) jobCell.append(el('div', { class: 'job-sub' }, detail));
        const reasons = [...job.reasons, ...job.warnings].join('；');
        if (reasons) jobCell.append(el('div', { class: 'job-reason' }, reasons));
        row.appendChild(jobCell);
        row.appendChild(el('td', {}, job.locations.join('、') || '未披露'));
        row.appendChild(el('td', {}, job.salary || '未披露'));
        row.appendChild(el('td', {}, job.source || '未知'));
        const linkCell = el('td');
        const links = el('div', { class: 'links' });
        if (job.source_url) links.appendChild(el('a', { href: job.source_url, target: '_blank', rel: 'noopener noreferrer' }, '查看'));
        if (job.application_url) links.appendChild(el('a', { href: job.application_url, target: '_blank', rel: 'noopener noreferrer' }, '投递'));
        linkCell.appendChild(links);
        row.appendChild(linkCell);
        tbody.appendChild(row);
      });
      table.append(thead, tbody);
      wrap.appendChild(table);
      card.appendChild(wrap);
      return card;
    }

    function quotaControls(group) {
      const current = state.quotas[group.group_id];
      const editableMax = Math.max(group.jobs.length, current.limit);
      const container = el('div', { class: 'quota-box' });
      const field = el('div', { class: 'field' });
      const inputId = `quota-${group.group_id}`;
      field.appendChild(el('label', { for: inputId }, '最多可投岗位'));
      const input = el('input', { id: inputId, type: 'number', min: '1', max: String(editableMax), value: String(current.limit) });
      input.addEventListener('change', () => {
        const value = Number.parseInt(input.value, 10);
        const selectedCount = selectedForGroup(group).length;
        if (!Number.isInteger(value) || value < 1 || value > editableMax) {
          input.value = String(current.limit);
          return setStatus(`“${group.company}”的限额必须在 1 到 ${editableMax} 之间。`, true);
        }
        if (value < selectedCount) {
          input.value = String(current.limit);
          return setStatus(`“${group.company}”已选择 ${selectedCount} 个岗位，不能把限额降为 ${value}。`, true);
        }
        state.quotas[group.group_id] = { limit: value, confirmed: false, verificationStatus: 'unverified' };
        setStatus(`已修改“${group.company}”限额，请核对后确认。`);
        render();
      });
      field.appendChild(input);
      const confirm = el('button', { class: current.confirmed ? 'button' : 'button button-primary', type: 'button' }, current.confirmed ? '取消确认' : '确认限额');
      confirm.addEventListener('click', () => {
        const latest = state.quotas[group.group_id];
        const displayed = Number.parseInt(input.value, 10);
        const selectedCount = selectedForGroup(group).length;
        const validLimit = Number.isInteger(displayed) && displayed >= 1 && displayed <= editableMax && displayed >= selectedCount;
        if (!validLimit) {
          input.value = String(latest.limit);
          return setStatus(`“${group.company}”的限额必须在 ${Math.max(1, selectedCount)} 到 ${editableMax} 之间。`, true);
        }
        const limit = displayed;
        const confirmed = !latest.confirmed;
        state.quotas[group.group_id] = { limit, confirmed, verificationStatus: confirmed ? 'manually_confirmed' : 'unverified' };
        setStatus(confirmed ? `已确认“${group.company}”最多投递 ${limit} 个岗位。` : `已取消“${group.company}”的限额确认。`);
        render();
      });
      container.append(field, confirm);
      const source = group.quota.source === 'conservative_default' ? '默认保守值' : group.quota.source === 'company_config' ? '公司规则配置' : '岗位数据';
      const help = el('div', { class: 'quota-help' }, `${source}${group.quota.verified_at ? ` · 核验于 ${group.quota.verified_at}` : ''}${group.quota.note ? ` · ${group.quota.note}` : ''}`);
      if (group.quota.source_url) {
        help.append(' · ', el('a', { href: group.quota.source_url, target: '_blank', rel: 'noopener noreferrer' }, '查看依据'));
      }
      container.appendChild(help);
      return container;
    }

    function toggleJob(group, job, checked) {
      const quota = state.quotas[group.group_id];
      if (checked) {
        if (selectedForGroup(group).length >= quota.limit) {
          setStatus(`“${group.company}”最多选择 ${quota.limit} 个岗位，请先取消其他岗位或调整并确认限额。`, true);
          return render();
        }
        state.selected.add(job.job_key);
      } else state.selected.delete(job.job_key);
      setStatus(`已选择 ${state.selected.size} 个待投递岗位。`);
      render();
    }

    function updateSummary(visibleJobs) {
      const unconfirmed = selectedGroups().filter(group => !quotaResolved(state.quotas[group.group_id])).length;
      elements.metricJobs.textContent = String(visibleJobs);
      elements.metricSelected.textContent = String(state.selected.size);
      elements.metricUnconfirmed.textContent = String(unconfirmed);
      elements.exportJson.disabled = !exportReady();
      elements.exportCsv.disabled = !exportReady();
      if (state.selected.size && unconfirmed) setStatus(`还有 ${unconfirmed} 个已选岗位所在公司的投递限额尚未确认，确认后才能导出。`, true);
    }

    function selectedRows() {
      return allJobs.filter(job => state.selected.has(job.job_key)).map(job => {
        const group = groupById.get(job.groupId);
        return {
          ...job,
          application_limit: state.quotas[job.groupId].limit,
          application_limit_confirmed: state.quotas[job.groupId].confirmed,
          application_limit_verification_status: state.quotas[job.groupId].verificationStatus,
          quota_group: group.group_id
        };
      });
    }

    function renderSelected() {
      const jobs = selectedRows();
      elements.selectedTable.replaceChildren();
      if (!jobs.length) return elements.selectedTable.appendChild(el('div', { class: 'empty' }, '尚未选择岗位。'));
      const wrap = el('div', { class: 'table-wrap' });
      const table = el('table');
      const head = el('thead');
      const hr = el('tr');
      ['序号', '岗位', '公司', '地点', '匹配分', '公司限额', '渠道', '投递'].forEach(label => hr.appendChild(el('th', {}, label)));
      head.appendChild(hr);
      const body = el('tbody');
      jobs.forEach((job, index) => {
        const row = el('tr');
        row.append(el('td', {}, String(index + 1)), el('td', {}, job.title), el('td', {}, job.company), el('td', {}, job.locations.join('、')), el('td', { class: 'score' }, job.score.toFixed(1)), el('td', {}, String(job.application_limit)), el('td', {}, job.source));
        const linkCell = el('td');
        if (job.application_url) linkCell.appendChild(el('a', { href: job.application_url, target: '_blank', rel: 'noopener noreferrer' }, '打开'));
        row.appendChild(linkCell);
        body.appendChild(row);
      });
      table.append(head, body); wrap.appendChild(table); elements.selectedTable.appendChild(wrap);
    }

    function download(name, type, content) {
      const url = URL.createObjectURL(new Blob([content], { type }));
      const link = el('a', { href: url, download: name });
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function exportPayload() {
      return {
        schema_version: '1.0', component: 'filter', component_version: '0.1.0',
        profile_id: data.profile_id, source_matcher_json: data.source_matcher_json,
        source_matcher_sha256: data.source_matcher_sha256, exported_at: new Date().toISOString(),
        summary: { selected_job_count: state.selected.size, company_count: new Set(selectedRows().map(job => job.company)).size },
        jobs: selectedRows()
      };
    }

    function csvCell(value) {
      let text = Array.isArray(value) ? value.join('、') : String(value ?? '');
      if (/^[=+\-@]/.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    }

    elements.search.addEventListener('input', event => { state.query = event.target.value.trim().toLowerCase(); render(); });
    elements.source.addEventListener('change', event => { state.source = event.target.value; render(); });
    elements.score.addEventListener('change', event => { state.minScore = Number(event.target.value); render(); });
    elements.reset.addEventListener('click', () => { state.selected.clear(); setStatus('已清空岗位选择，已确认的限额仍会保留。'); render(); });
    elements.exportJson.addEventListener('click', () => download('selected-jobs.json', 'application/json;charset=utf-8', JSON.stringify(exportPayload(), null, 2)));
    elements.exportCsv.addEventListener('click', () => {
      const columns = ['序号', '岗位', '公司', '地点', '岗位类型', '匹配分', '公司投递限额', '渠道', '岗位链接', '投递链接'];
      const rows = selectedRows().map((job, index) => [index + 1, job.title, job.company, job.locations, employmentLabel(job.employment_type), job.score, job.application_limit, job.source, job.source_url, job.application_url]);
      download('selected-jobs.csv', 'text/csv;charset=utf-8', '\ufeff' + [columns, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n'));
    });

    document.getElementById('source-summary').textContent = `${data.profile_id} · ${data.summary.job_count} 个候选岗位 · ${data.summary.company_count} 家公司`;
    [...new Set(allJobs.map(job => job.source).filter(Boolean))].sort().forEach(source => elements.source.appendChild(el('option', { value: source }, source)));
    render();
  })();
  </script>
</body>
</html>
'''


def render_html(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return HTML_TEMPLATE.replace("__JOBPILOT_DATA__", encoded)
