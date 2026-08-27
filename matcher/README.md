# JobPilot 岗位匹配组件

第三组件读取 `profile_builder` 生成的 `profile.json`，先搜索维护清单中的企业招聘官网，再从公开招聘平台补充候选岗位；完成统一字段、跨渠道去重和覆盖审计后，才使用本地规则计算人岗匹配分。结果按公司轮转选取，先覆盖每家公司的最高匹配岗位，再进入下一轮，避免少数公司占满推荐列表。本组件不自动投递，也不调用大模型。

固定顺序为：`企业官网（大厂 / 中型公司 / 独角兽 / 成长型公司） → 公开招聘平台补充 → 去重 → 匹配评分`。官网无法解析时会记录覆盖缺口，不会把“未能采集”误报成“没有岗位”。

## 已接入渠道

| 渠道 | 接入方式 | 说明 |
|---|---|---|
| 牛客网 | 公开职位检索接口 | 支持校招、实习和社招；对大厂逐家公司定向检索，只作为补充来源并如实标记 |
| OfferShow | 公开招聘栏目 | 汇总招聘计划，并优先保留公司官网投递链接 |
| 实习僧 | 公开搜索结果页 | 仅当画像选择 `internship` 时采集 |
| BOSS 直聘 | 公开搜索入口 | 遇到环境校验时不绕过，输出浏览器检索链接和 `needs_browser` 状态 |
| 公司招聘官网 | 官网 API / `JobPosting` JSON-LD / 动态页面 | 默认优先搜索 `config/company_catalog.json`；腾讯、快手、百度使用公开接口，字节、美团使用 Playwright 渲染官方动态招聘页 |
| 任意渠道导出 | JSON / CSV | 使用 `--import-jobs` 导入人工导出或授权取得的岗位 |

站点结构和访问规则可能变化。每次结果都会记录各渠道的 `success`、`partial`、`empty`、`skipped`、`needs_browser` 或 `failed` 状态，访问失败不会被误报为“没有岗位”。

## 运行

要求 Python 3.10 或更高版本。从项目根目录执行：

```bash
# 自动读取最新用户画像，并采集默认渠道
PYTHONPATH=matcher python3 -m matcher

# 指定画像、最低分和每个渠道的采集上限
PYTHONPATH=matcher python3 -m matcher \
  --profile profile_builder/outputs/<画像目录>/profile.json \
  --min-score 50 \
  --max-per-source 30

# 只使用指定在线渠道
PYTHONPATH=matcher python3 -m matcher --sources nowcoder,offershow

# 添加公司招聘官网
PYTHONPATH=matcher python3 -m matcher \
  --career-url https://example.com/careers

# 完全离线，仅匹配导入数据
PYTHONPATH=matcher python3 -m matcher \
  --offline \
  --import-jobs matcher/examples/jobs.example.csv
```

也可以安装命令行入口：

```bash
python3 -m venv matcher/.venv
source matcher/.venv/bin/activate
pip install -e matcher
playwright install chromium
job-match
```

## 匹配规则

组件沿用用户画像 `matching_config.weights` 中的九类权重：岗位方向、技能、经验、学历、地点、到岗时间、行业、薪资和公司偏好。

- 每条岗位保留总分、等级、分项得分、命中技能、缺失技能和解释文本。
- `must_have_keywords`、`excluded_keywords` 与 `deal_breakers` 作为硬约束处理。
- 缺少薪资或地点偏好时采用中性处理，不把“渠道未披露”误判为“不匹配”。
- 评分为确定性本地规则，默认不调用模型。

## 输出

```text
matcher/outputs/
├── manifest.json
└── <profile_id>/<运行时间>/
    ├── jobs.json    # 完整岗位、评分、渠道状态及可追溯元数据
    ├── jobs.csv     # 可在 Excel 中打开的岗位汇总表
    └── jobs.md      # 人工可读的 Markdown 汇总表
```

导入文件可使用中英文表头，至少需要 `title`/`职位`。常用字段包括 `company`/`公司`、`location`/`地点`、`requirements`/`岗位要求`、`url`/`岗位链接` 和 `application_url`/`投递链接`。

## 边界

- 组件只读取公开页面、公开接口或用户显式提供的数据。
- 不绕过验证码、登录、环境校验或反自动化措施。
- 不保存账号密码、Cookie，也不执行投递操作。
- 岗位可能下线或变更，投递前应打开原始链接确认。

## 测试

```bash
PYTHONPATH=matcher python3 -m unittest discover -s matcher/tests -v
```
