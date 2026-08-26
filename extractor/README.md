# JobPilot 简历拆解组件

一个完全本地运行的简历解析组件。组件的代码、测试、文档和拆解结果均统一放在项目根目录的 `extractor/` 下；源简历仍从项目根目录的 `inputs/` 读取。解析过程不上传文件，也不依赖在线大模型。

## 支持格式

- PDF：`.pdf`（文本型 PDF；扫描件需先 OCR）
- Word：`.docx`，以及通过 LibreOffice 转换的 `.doc`、`.odt`
- LaTeX：`.tex`、`.latex`
- Markdown / 文本：`.md`、`.markdown`、`.txt`

## 安装与运行

```bash
python3 -m venv extractor/.venv
source extractor/.venv/bin/activate
pip install -e extractor

# 默认处理项目根目录 inputs 下的全部简历，结果保存到 extractor/outputs
resume-split

# 指定目录或文件
resume-split -i inputs -o extractor/outputs --recursive
resume-split inputs/resume.pdf -o extractor/outputs
resume-split inputs/resume.md --json
```

不安装命令行入口也可以直接运行：

```bash
python3 -m extractor.resume_splitter
```

## 作为 Python 组件使用

```python
from resume_splitter import ResumeParser

parser = ResumeParser()
document, saved_to = parser.parse_and_save("inputs/resume.pdf", "extractor/outputs")

print(document.profile.name)
for section in document.sections:
    print(section.type, section.title)
```

批量处理：

```python
records = parser.parse_directory("inputs", "extractor/outputs", recursive=True)
```

## 本地输出结构

输出目录使用“原文件名 + 内容 SHA-256 前 8 位”命名，避免重名简历互相覆盖：

```text
extractor/outputs/
├── manifest.json
└── resume-a1b2c3d4/
    ├── resume.json
    ├── raw.txt
    └── sections/
        ├── 01-基本信息.md
        ├── 02-教育背景.md
        └── 03-项目经历.md
```

`resume.json` 包含：

- `source`：源文件名、路径、格式、哈希、大小和处理时间
- `profile`：姓名、邮箱、电话、所在地、求职意向和链接
- `sections`：栏目类型、原始标题、顺序、正文和按日期进一步拆分的条目
- `raw_text`：标准化后的完整原文，便于追溯
- `warnings`：扫描件、栏目未识别等质量提示
- `extraction`：所用抽取器和页数等元数据

默认识别中英文常见栏目，包括教育、工作、实习、项目、科研、开源、论文、技能、奖项、证书、语言、校园经历和自我评价。别名表位于 `resume_splitter/sectioner.py` 的 `SECTION_ALIASES`，可按团队简历模板继续扩展。

## 验证

```bash
PYTHONPATH=extractor python3 -m unittest discover -s extractor/tests -v
```
