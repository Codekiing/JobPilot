# JobPilot 岗位过滤组件

第四组件读取 `matcher` 生成的 `jobs.json` 岗位汇总表，生成一个完全自包含、可直接在浏览器中打开的交互式 HTML。用户按公司核对投递限额、勾选最终岗位，并导出待投递岗位表。

## 核心能力

- 按“公司 + 招聘类型”分组展示候选岗位。
- 保留岗位名称、地点、薪资、匹配分、匹配理由、来源及投递链接。
- 每组都有“最多可投岗位”限额；达到限额后自动禁用其余岗位。
- 显示限额核验状态和证据链接；当期规则已核验的公司无需再次人工确认。
- 官方公开页面未披露规则时保守按 1 个处理，并允许用户依据登录后看到的规则人工修正。
- 选择和限额状态保存在当前浏览器的本地存储中，刷新页面不会丢失。
- 最终可下载 `selected-jobs.csv` 和 `selected-jobs.json`。
- CSV 使用 UTF-8 BOM，可直接在 Excel 中打开，并对公式注入字符进行转义。
- 页面不访问网络，岗位数据直接嵌入 HTML。

## 限额核验策略

公司的可投岗位数通常随招聘批次、岗位类型和时间变化，不能只按公司名称永久写死。组件按以下顺序确定限额：

1. 汇总表岗位自身携带的 `application_limit`。
2. `filter/config/company_limits.json` 中匹配公司及招聘类型的规则。
3. 无可靠规则时采用保守默认值 `1`，并标记为“已核查·官方未披露”或“限额待确认”。

`verification_status` 用于区分核验结果：

- `confirmed`：当前批次存在可追溯的明确数量规则。
- `public_not_found`：已检查当期公告或官方投递门户，但公开页面未披露数量。
- `stale`：只找到旧批次规则，未将其套用到当前批次。
- `unverified`：尚未核验。

`confirmed: true` 表示数量本身已有证据；`public_not_found` 表示公开核验已经完成，页面会按保守上限限制选择并允许导出，同时在导出数据中保留“数量未获官方公开确认”的状态。尚未核验、旧规则或用户自行修改但未确认的限额仍会阻止导出。核验记录应包含 `source_url`、`verified_at` 和说明，避免把旧校招规则套用到社招或新批次。

## 运行

要求 Python 3.10 或更高版本。从项目根目录执行：

```bash
# 自动读取 matcher 最新的 jobs.json
PYTHONPATH=filter python3 -m job_filter

# 指定汇总表
PYTHONPATH=filter python3 -m job_filter \
  --input matcher/outputs/<profile_id>/<运行时间>/jobs.json

# 指定公司投递限额配置
PYTHONPATH=filter python3 -m job_filter \
  --limits filter/config/company_limits.json
```

安装命令行入口：

```bash
python3 -m venv filter/.venv
source filter/.venv/bin/activate
pip install -e filter
job-filter
```

## 限额配置

配置文件格式参考 [company_limits.example.json](config/company_limits.example.json)：

```json
{
  "default_limit": 1,
  "aliases": {
    "示例科技有限公司": "示例科技"
  },
  "companies": {
    "示例科技": [
      {
        "employment_types": ["campus"],
        "limit": 2,
        "confirmed": true,
        "verification_status": "confirmed",
        "source_url": "https://example.com/campus/faq",
        "verified_at": "2026-08-26",
        "note": "该届校园招聘最多选择两个岗位"
      }
    ]
  }
}
```

建议只把公司官网或招聘公告中能够核验的规则设置为 `confirmed: true`，并同时记录 `source_url` 和 `verified_at`。

## 输出

```text
filter/outputs/
├── manifest.json
└── <profile_id>/<生成时间>/
    └── job-filter.html
```

在 HTML 中确认限额、勾选岗位后：

- `导出 CSV`：生成最终待投递岗位汇总表 `selected-jobs.csv`。
- `导出 JSON`：生成带来源哈希和限额确认信息的 `selected-jobs.json`。

## 测试

```bash
PYTHONPATH=filter python3 -m unittest discover -s filter/tests -v
```
