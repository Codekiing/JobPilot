# JobPilot

JobPilot 是一个面向求职场景的本地化工具项目。目前包含简历拆解、用户画像建立、岗位匹配、岗位过滤、个人信息填充和统一 API 六部分。整体流程为：

```text
inputs/ 中的简历
    ↓
简历拆解组件（extractor）
    ↓ resume.json
用户画像建立组件（profile_builder）
    ↓ profile.json
岗位候选池（企业官网优先，公开平台补充）
    ↓ 标准化 / 跨渠道去重 / 来源覆盖报告
岗位匹配组件（matcher）
    ↓ jobs.json / jobs.csv / jobs.md
岗位过滤组件（filter）
    ↓ selected-jobs.json
个人信息内容填充组件（filler）
    ↓ 本地填表草稿 / 浏览器辅助填充
人工检查并提交
```

## 组件介绍

### 1. 简历拆解组件 `extractor/`

读取项目根目录 `inputs/` 中的简历，将内容拆解为基本信息、教育背景、实习/工作经历、项目、技能、论文、奖励等栏目。

- 输入：`inputs/` 下的 PDF、DOC/DOCX、ODT、LaTeX、Markdown 或纯文本简历。
- 输出：`extractor/outputs/<简历名>-<哈希>/` 下的 `resume.json`、`raw.txt` 和分栏目 Markdown 文件。

- 支持 PDF、DOC/DOCX、ODT、LaTeX、Markdown 和纯文本格式。
- 默认完全在本地解析，不上传简历，不依赖外部模型。
- 结果保存在 `extractor/outputs/`，核心产物为结构化的 `resume.json`。
- 详细说明见 [extractor/README.md](extractor/README.md)。

### 2. 用户画像建立组件 `profile_builder/`

读取简历拆解组件生成的 `resume.json`，建立可供岗位匹配使用的结构化用户画像。

- 输入：`extractor/outputs/.../resume.json`，以及用户填写的问卷答案（可选）。
- 输出：`profile_builder/outputs/<用户目录>/` 下的 `profile.json`、`questions.json` 和 `profile_summary.md`。

- 自动整理职业阶段、求职目标、能力技能、经历证据、工作偏好和硬性约束。
- 通过一份 12 题简版问卷补充简历中缺失的信息。
- 默认使用透明的本地规则处理问卷；只有显式启用时才调用模型。
- 结果保存在 `profile_builder/outputs/`，核心产物为 `profile.json`。
- 详细说明见 [profile_builder/README.md](profile_builder/README.md)。

### 3. 岗位匹配组件 `matcher/`

读取用户画像，聚合主流招聘渠道的公开岗位，完成字段标准化、跨渠道去重和可解释的本地规则评分。

- 输入：`profile_builder/outputs/.../profile.json`，以及公开招聘渠道或用户导入的 JSON/CSV 岗位数据。
- 输出：`matcher/outputs/<profile_id>/<运行时间>/` 下的 `jobs.json`、`jobs.csv` 和 `jobs.md`。

- 默认先逐家公司搜索维护清单中的大厂、中型公司、独角兽和成长型公司官网，再使用牛客网、OfferShow、实习僧和 BOSS 公开入口补充候选池。
- 官网搜索失败会记录为覆盖缺口，不会被解释成“该公司没有相关岗位”。
- BOSS 遇到环境校验时返回浏览器搜索入口，不绕过验证。
- 支持读取公司招聘官网的 `JobPosting` 数据，以及导入任意渠道的 JSON/CSV 导出文件。
- 结果保存在 `matcher/outputs/`，同时生成 JSON、CSV 和 Markdown 汇总表。
- 详细说明见 [matcher/README.md](matcher/README.md)。

### 4. 岗位过滤组件 `filter/`

读取岗位汇总表，按公司和招聘类型组织候选岗位，让用户在公司投递数量限制内主动选择最终岗位。

- 输入：matcher 生成的 `jobs.json`，以及 `filter/config/company_limits.json` 中的公司投递限额规则。
- 输出：可交互的 `job-filter.html`；用户确认后由页面导出 `selected-jobs.json` 或 `selected-jobs.csv`。

- 生成无需后端即可打开的交互式 HTML。
- 支持按当前招聘批次记录公司限额、核验状态与证据链接；规则未公开时保守处理并支持人工复核。
- 最终导出 CSV 或 JSON 待投递岗位表。
- 详细说明见 [filter/README.md](filter/README.md)。

### 5. 个人信息内容填充组件 `filler/`

读取用户画像和过滤组件导出的待投递岗位表，生成逐岗位申请草稿，并可在用户逐站点确认后辅助填写招聘页面。

- 输入：`profile.json`、filter 导出的 `selected-jobs.json`，以及公司官方招聘入口配置。
- 输出：包含共享字段与逐岗位计划的 `fill-plan.json`、浏览器填充报告，以及经用户确认后保存在招聘网站账户中的草稿。

- 默认只生成本地草稿，不访问招聘网站、不发送个人信息；执行模式会先打开公司官方招聘入口，等待用户手动登录和进入申请表。
- 浏览器执行会等待用户完成登录，并在发送姓名、联系方式和经历前再次确认。
- 只填充唯一识别的文本框和下拉框；简历附件必须显式配置并逐岗位确认，不处理验证码、不自动提交申请。
- 真实填入和保存网站草稿均需要分别确认；本地始终保存字段映射和执行报告。
- 详细说明见 [filler/README.md](filler/README.md)。

### 6. 统一 API `jobpilot/`

为各组件保留统一的本地 HTTP 接口。目前提供健康检查、问卷、用户画像、岗位匹配、过滤页面和填表草稿接口。

- 输入：发送到 `/jobpilot/*` 的本地 HTTP 请求及项目目录内的组件数据文件。
- 输出：JSON 接口响应，以及按请求生成的用户画像、岗位汇总、筛选页面或填表计划等本地产物。

- API 路径统一使用 `/jobpilot` 前缀。
- 默认只监听 `127.0.0.1`。
- 默认不调用任何外部模型 API；只有请求明确设置 `use_model: true` 时才会启用模型能力。
- OpenAPI 契约位于 `jobpilot/openapi.json`。
- 详细说明见 [jobpilot/README.md](jobpilot/README.md)。

## 项目目录

```text
JobPilot/
├── inputs/             # 待处理的原始简历
├── extractor/          # 第一组件：简历拆解
├── profile_builder/    # 第二组件：用户画像建立
├── matcher/            # 第三组件：岗位聚合与匹配
├── filter/             # 第四组件：岗位限额过滤与最终选择
├── filler/             # 第五组件：个人信息填充与本地申请草稿
├── jobpilot/           # 统一 API
└── README.md           # 项目总览
```

## 快速开始

要求 Python 3.10 或更高版本。从项目根目录执行：

```bash
# 拆解 inputs/ 中的简历
PYTHONPATH=extractor python3 -m resume_splitter

# 根据最新拆解结果建立用户画像
PYTHONPATH=profile_builder python3 -m profile_builder

# 根据最新用户画像采集并匹配岗位
PYTHONPATH=matcher python3 -m matcher

# 根据最新岗位汇总生成交互式筛选页面
PYTHONPATH=filter python3 -m job_filter

# 根据画像和 filter 导出结果生成本地填表草稿
PYTHONPATH=filler python3 -m filler --jobs filler/inputs/selected-jobs.json

# 启动本地统一 API（uv 会按根目录 pyproject.toml 安装 PDF、Word 与岗位采集依赖）
uv run --python 3.12 python -m jobpilot --host 127.0.0.1 --port 8765
```

网页前端会自动检查 `http://127.0.0.1:8765/jobpilot`。连接成功后，上传简历会真实调用 `extractor` 和 `profile_builder` 填充待确认画像；用户补充并确认保存后，`matcher` 才会动态搜索官网与公开平台并返回岗位。未启动本地 API 时，网页只展示示例画像且岗位列表为空，不会模拟解析或岗位搜索成功。
