# JobPilot 个人信息内容填充组件

第五组件读取用户画像 `profile.json` 和岗位过滤组件导出的 `selected-jobs.json`，为每个待投递岗位生成字段映射和本地申请草稿。用户显式启用浏览器执行后，组件先打开公司官方招聘入口，等待用户手动登录、找到对应岗位并进入申请表；只有用户再次确认后，才会把画像内容真实写入可明确识别的网页字段。

## 安全边界

- 默认模式仅在本地生成草稿，不打开招聘网站，也不发送个人信息。
- 浏览器先打开 `config/official_sites.json` 中已确认的公司招聘入口。聚合网站链接不会在缺少官网映射时直接用于填充。
- 登录、验证码、岗位搜索、点击申请和进入填表页均由用户手动完成。
- 到达填表页后先输入 `READY <草稿ID>`；组件识别字段并显示接收网站后，再输入 `FILL <草稿ID>` 才会真实填入。
- 不读取或导出浏览器 Cookie、密码和验证码。
- 不填写密码、文件上传、单选框和复选框；简历上传默认关闭。
- 不点击“提交”“申请”“下一步”等按钮，并在页面内拦截标准表单提交事件。
- 填入后默认询问是否保存网站草稿；只有输入 `SAVE <草稿ID>` 且页面上存在唯一的“保存草稿/暂存”按钮时才会点击。
- 草稿包含姓名、电话、邮箱和经历等个人信息，使用仅限当前用户的文件权限保存，并被 `.gitignore` 排除。

招聘网站可能在字段变更时自动保存，因此“填入页面”本身就可能向网站发送个人信息。只有在运行时确认后才会执行。

## 输入

1. `profile_builder/outputs/.../profile.json`
2. 从过滤页面点击“导出 JSON”得到的 `selected-jobs.json`，放到：

```text
filler/inputs/selected-jobs.json
```

组件会校验两个文件的 `profile_id`，避免把甲的个人信息填入乙的岗位清单。

`inputs/profile.example.json` 和 `inputs/selected-jobs.example.json` 提供了一组不含真实个人信息的完整示例。

## 默认运行：只生成本地草稿

```bash
PYTHONPATH=filler python3 -m filler
```

也可以明确指定输入：

```bash
PYTHONPATH=filler python3 -m filler \
  --profile profile_builder/outputs/<用户目录>/profile.json \
  --jobs filler/inputs/selected-jobs.json
```

输出结构：

```text
filler/outputs/
├── manifest.json
└── <profile_id>/<运行时间>/
    ├── fill-plan.json
    ├── application-drafts/
    │   └── draft-*.json
    └── fill-reports/              # 执行浏览器填充后生成
        └── draft-*.json
```

## 浏览器辅助填充

需要 Python 3.10 或更高版本。安装可选依赖：

```bash
python3 -m venv filler/.venv
source filler/.venv/bin/activate
pip install -e 'filler[browser]'
playwright install chromium
```

执行填充：

```bash
PYTHONPATH=filler python3 -m filler --execute
```

组件使用 `filler/.browser-profile/` 作为独立登录会话。每个岗位的流程是：

1. 打开公司官方招聘入口。
2. 用户在浏览器中手动登录、查找目标岗位、点击申请，直至进入表单。
3. 用户输入 `READY <草稿ID>`，组件只读取字段名称，不填写内容。
4. 组件显示将填写的字段和当前接收网站；用户输入 `FILL <草稿ID>` 后，真实填写唯一、明确匹配的输入框。
5. 用户检查结果，并可输入 `SAVE <草稿ID>` 让组件点击精确匹配的“保存草稿/暂存”。组件会读取明确的成功提示；若网站没有提示，则由用户输入 `SAVED <草稿ID>` 确认结果。组件永远不点击投递/提交。

如只想填入页面、不询问点击网站自身的“保存草稿/暂存”按钮：

```bash
PYTHONPATH=filler python3 -m filler --execute --local-draft-only
```

官方入口映射可通过 `--official-sites <路径>` 替换。无法确认的公司会在计划中产生警告并跳过浏览器执行，原岗位链接仍保留在 `original_application_url` 中供人工核对。

## 字段范围

当前自动映射：姓名、邮箱、电话、现居城市、最高学历、毕业时间、求职意向、期望城市、技能、语言、教育经历、工作/实习经历、项目、论文和个人简介。

招聘网站的动态教育卡片、级联选择器、短信验证、附件上传以及自定义问答差异较大。组件会保留完整草稿，但只自动填写能唯一识别且不需要额外决策的字段。

## 测试

```bash
PYTHONPATH=filler python3 -m unittest discover -s filler/tests -v
```
