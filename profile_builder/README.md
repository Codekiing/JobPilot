# JobPilot 用户画像建立组件

第二组件读取第一组件生成的 `resume.json`，自动建立可解释的求职画像，再通过一份 12 题简版问卷补齐岗位匹配所需信息。代码、测试、文档和输出统一位于 `profile_builder/`；本组件不抓取职位，也不执行岗位匹配。

## 核心能力

- 自动继承姓名、联系方式、教育、实习/工作、论文、开源和技能栏目。
- 确定性抽取学历、毕业年月、职业阶段、经验月数、目标岗位和标准化技能。
- 每个推断技能保留 `evidence_refs`，第三组件可以解释匹配依据。
- 12 道自然语言问题覆盖基本状态、目标岗位、地点、入职、薪资、技能、证据、公司偏好、硬约束、语言、匹配词和其他偏好。
- 回收答案后先通过透明规则提取城市、日期、薪资、实习安排、办公方式和硬约束等确定信息。
- 可选调用 Responses API，以结构化输出补充规则无法稳定理解的自由文本。
- 模型只能填充空字段，不能覆盖简历或规则已经确认的内容。
- 生成完成度、必填缺口及 `match_ready` 状态。
- 支持交互终端，也支持 JSON 批量答案，便于未来接入前端。

问卷正文见 [docs/simple_questionnaire.md](docs/simple_questionnaire.md)，字段设计依据见 [docs/field_design.md](docs/field_design.md)。

## 运行

从项目根目录运行：

```bash
# 自动读取第一组件最新的 resume.json，并进入交互问询
python3 -m profile_builder.profile_builder

# 只生成自动推断草稿和12题问卷
python3 -m profile_builder.profile_builder --draft --list-questions

# 指定第一组件输出
python3 -m profile_builder.profile_builder \
  --resume-json extractor/outputs/<简历目录>/resume.json

# 继续完善已有画像
python3 -m profile_builder.profile_builder \
  --profile profile_builder/outputs/<画像目录>/profile.json
```

安装命令行入口：

```bash
python3 -m venv profile_builder/.venv
source profile_builder/.venv/bin/activate
pip install -e profile_builder
profile-build --draft
```

## 提交问卷答案

复制并编辑 [examples/survey_answers.example.json](examples/survey_answers.example.json)，其结构如下：

```json
{
  "survey_answers": {
    "basic_status": "目前在深圳，2027届硕士，正在积极求职",
    "job_targets": "全职；首选大模型后训练算法工程师，其次Agent算法工程师",
    "location_work_mode": "首选深圳、北京，可接受上海；接受现场或混合办公",
    "availability": "2027-07-01可以入职",
    "compensation": "最低30K，期望35K-45K，14薪以上，可商议",
    "strengths_skills": "GRPO、RLHF、分布式训练"
  }
}
```

然后运行：

```bash
python3 -m profile_builder.profile_builder \
  --draft \
  --answers profile_builder/examples/survey_answers.example.json
```

规则处理记录写入 `questionnaire.rule_enrichment`，原始答案保存在 `questionnaire.survey_answers`。

## 可选模型补全

本地规则已经可以独立工作。仅当问卷包含复杂自由文本时，才需要启用模型：

```bash
export OPENAI_API_KEY="..."
export JOBPILOT_PROFILE_MODEL="<支持结构化输出的模型名称>"

python3 -m profile_builder.profile_builder \
  --draft \
  --answers profile_builder/examples/survey_answers.example.json \
  --use-model
```

模型客户端使用 Responses API 的 JSON Schema 结构化输出。请求设置 `store: false`，不发送联系方式和完整经历正文；问卷中的姓名、邮箱和电话会先被脱敏。接口实现依据 [OpenAI Responses API 官方文档](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)。

## 输出

```text
profile_builder/outputs/<姓名>-<画像哈希>/
├── profile.json          # 第三组件的正式输入
├── questions.json        # 12题问卷定义及已回收答案
└── profile_summary.md    # 人工可读摘要
```

`profile.json` 的顶层栏目为：

- `identity`
- `career`
- `target`
- `capabilities`
- `evidence`
- `preferences`
- `constraints`
- `matching_config`
- `questionnaire`
- `completion`

第三组件可以使用 [schemas/user_profile.schema.json](schemas/user_profile.schema.json) 校验输入契约。

## 测试

```bash
PYTHONPATH=profile_builder python3 -m unittest discover -s profile_builder/tests -v
```
