# JobPilot 本地 API

该目录保留 JobPilot 的统一 API 入口，覆盖用户画像、岗位匹配、岗位过滤和填表草稿。默认只执行本地规则，不调用外部模型、不访问在线招聘渠道，也不打开浏览器。

## 启动

从项目根目录运行：

```bash
python3 -m jobpilot --host 127.0.0.1 --port 8765
```

默认只监听本机地址。

## 接口

### `GET /jobpilot/health`

返回服务状态及 `model_call_default: false`。

### `GET /jobpilot/questionnaire`

返回 12 题用户画像问卷定义。

### `GET /jobpilot/openapi.json`

返回 [OpenAPI 3.1 契约](openapi.json)。

### `POST /jobpilot/profile`

根据第一组件输出及问卷答案建立用户画像。最小请求：

```json
{
  "survey_answers": {
    "basic_status": "目前在深圳，2027届硕士，正在积极求职",
    "job_targets": "全职；大模型后训练算法工程师"
  }
}
```

主要字段：

- `resume_json`：第一组件输出路径；省略时读取最新结果。
- `profile_json`：继续完善已有画像，与 `resume_json` 二选一。
- `survey_answers`：12题问卷答案。
- `save`：是否保存结果，默认 `true`。
- `output_dir`：项目内输出目录，默认 `profile_builder/outputs`。
- `use_model`：是否调用外部模型，默认且必须显式为 `false` 才是规则模式；省略也等同 `false`。
- `model`：仅在 `use_model=true` 时必填。
- `api_base`：可选模型 API 基地址。

默认规则模式：

```bash
curl -X POST http://127.0.0.1:8765/jobpilot/profile \
  -H 'Content-Type: application/json' \
  -d '{"survey_answers":{"location_work_mode":"首选深圳，接受现场办公"},"save":false}'
```

只有以下请求会调用模型：

```json
{
  "survey_answers": {
    "additional_context": "希望团队有导师制度和论文发表机会"
  },
  "use_model": true,
  "model": "<模型名称>"
}
```

API Key 不允许通过请求体传入，只从服务端环境变量 `OPENAI_API_KEY` 读取。响应中的 `meta.processing_mode` 为 `rules_only` 或 `rules_and_model`，并明确返回 `model_called`。

### `POST /jobpilot/match`

读取用户画像并生成岗位汇总。API 默认离线，不产生外部网络请求：

```json
{
  "profile_json": "profile_builder/outputs/<画像目录>/profile.json",
  "online": false,
  "import_jobs": ["matcher/examples/jobs.example.csv"]
}
```

只有显式设置 `"online": true` 才访问公开招聘渠道：

```json
{
  "online": true,
  "sources": ["nowcoder", "offershow"],
  "min_score": 50
}
```

响应通过 `meta.external_network_called` 明确标记是否访问了在线渠道。

### `POST /jobpilot/filter`

根据最新岗位汇总表生成交互式岗位选择页面，全程本地处理：

```json
{
  "matcher_json": "matcher/outputs/<profile_id>/<运行时间>/jobs.json",
  "limits_json": "filter/config/company_limits.json"
}
```

响应返回生成的 `html_path`、候选岗位数、公司数和已确认限额数。

### `POST /jobpilot/filler`

根据用户画像和 filter 导出的 `selected-jobs.json` 生成逐岗位本地填表草稿。该接口只负责本地规划，不会打开浏览器、发送个人信息或提交申请。

```json
{
  "profile_json": "profile_builder/outputs/<用户目录>/profile.json",
  "selected_jobs_json": "filler/inputs/selected-jobs.json",
  "official_sites_json": "filler/config/official_sites.json",
  "output_dir": "filler/outputs"
}
```

浏览器辅助填充必须通过 `filler` 命令行显式执行。它会先打开公司官方招聘入口，等待用户手动登录和进入申请表，再分别确认个人信息填入与网站草稿保存；API 始终只生成本地计划。
