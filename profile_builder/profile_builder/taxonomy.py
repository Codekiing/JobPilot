from __future__ import annotations

import re


# Canonical vocabulary used by the future job-matching component. Patterns are
# deliberately explicit so inference remains deterministic and reviewable.
SKILL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("Python", "programming_language", r"(?<![A-Za-z])Python(?![A-Za-z])"),
    ("C++", "programming_language", r"C\+\+"),
    ("Java", "programming_language", r"(?<![A-Za-z])Java(?![A-Za-z])"),
    ("Linux", "engineering_tool", r"(?<![A-Za-z])Linux(?![A-Za-z])"),
    ("Git", "engineering_tool", r"(?<![A-Za-z])Git(?![A-Za-z])"),
    ("PyTorch", "ml_framework", r"PyTorch|Pytorch"),
    ("TensorFlow", "ml_framework", r"TensorFlow"),
    ("DeepSpeed", "training_framework", r"DeepSpeed"),
    ("PEFT", "training_framework", r"(?<![A-Za-z])PEFT(?![A-Za-z])"),
    ("TRL", "training_framework", r"(?<![A-Za-z])TRL(?![A-Za-z])"),
    ("veRL", "training_framework", r"(?<![A-Za-z])veRL(?![A-Za-z])"),
    ("Ray", "distributed_system", r"(?<![A-Za-z])Ray(?![A-Za-z])"),
    ("vLLM", "inference_framework", r"vLLM"),
    ("SGLang", "inference_framework", r"SGLang"),
    ("LoRA", "fine_tuning", r"LoRA"),
    ("SFT", "post_training", r"(?<![A-Za-z])SFT(?![A-Za-z])"),
    ("RLHF", "post_training", r"RLHF"),
    ("PPO", "post_training", r"(?<![A-Za-z])PPO(?![A-Za-z])"),
    ("GRPO", "post_training", r"(?<![A-Za-z])GRPO(?![A-Za-z])"),
    ("DPO", "post_training", r"(?<![A-Za-z])DPO(?![A-Za-z])"),
    ("强化学习", "machine_learning", r"强化学习|Reinforcement Learning"),
    ("深度学习", "machine_learning", r"深度学习|Deep Learning"),
    ("机器学习", "machine_learning", r"机器学习|Machine Learning"),
    ("自然语言处理", "ai_domain", r"自然语言处理|NLP"),
    ("多模态", "ai_domain", r"多模态|multimodal"),
    ("Agent", "ai_domain", r"(?<![A-Za-z])Agent(?:ic)?(?![A-Za-z])"),
    ("RAG", "ai_domain", r"(?<![A-Za-z])RAG(?![A-Za-z])|检索增强生成"),
    ("模型评测", "ai_engineering", r"模型评测|自动评测|评测体系|model evaluation"),
    ("分布式训练", "ai_engineering", r"分布式训练|多维并行|千亿参数|训推分离"),
    ("推理加速", "ai_engineering", r"推理加速|推理优化|inference optimization"),
    ("Ascend", "hardware_platform", r"Ascend|昇腾"),
)


def infer_skills(sections: list[dict[str, object]]) -> list[dict[str, object]]:
    skills: list[dict[str, object]] = []
    for name, category, pattern in SKILL_PATTERNS:
        evidence_refs: list[str] = []
        best_level = "unspecified"
        for section in sections:
            content = str(section.get("content", ""))
            match = re.search(pattern, content, re.IGNORECASE)
            if not match:
                continue
            evidence_refs.append(f"resume-section-{section.get('order', len(evidence_refs) + 1)}")
            window = content[max(0, match.start() - 24) : match.end() + 24]
            level = _proficiency_from_context(window)
            if _level_rank(level) > _level_rank(best_level):
                best_level = level
        if evidence_refs:
            skills.append(
                {
                    "name": name,
                    "category": category,
                    "proficiency": best_level,
                    "source": "resume_inference",
                    "evidence_refs": list(dict.fromkeys(evidence_refs)),
                }
            )
    return skills


def _proficiency_from_context(text: str) -> str:
    if re.search(r"精通|专家|expert", text, re.IGNORECASE):
        return "expert"
    if re.search(r"熟练|主导|独立负责|设计与落地", text, re.IGNORECASE):
        return "advanced"
    if re.search(r"熟悉|掌握|负责|搭建|实现", text, re.IGNORECASE):
        return "intermediate"
    if re.search(r"了解|基础|入门", text, re.IGNORECASE):
        return "foundational"
    return "unspecified"


def _level_rank(level: str) -> int:
    return {"unspecified": 0, "foundational": 1, "intermediate": 2, "advanced": 3, "expert": 4}[level]
