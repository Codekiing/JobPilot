from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from .models import UserProfile


@dataclass(slots=True)
class SurveyQuestion:
    id: str
    angle: str
    prompt: str
    placeholder: str
    covers: list[str] = field(default_factory=list)
    required: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SIMPLE_SURVEY: tuple[SurveyQuestion, ...] = (
    SurveyQuestion(
        "basic_status",
        "基本情况与职业阶段",
        "请用一句话说明姓名、当前城市、职业阶段和求职状态；联系方式有变化时一并填写。",
        "例如：张三，目前在深圳，2027届硕士，正在积极求职；邮箱 zhangsan@example.com",
        ["identity.name", "identity.contact.email", "identity.contact.phone", "career.current_city", "career.career_stage", "career.job_search_status", "career.graduation_date"],
        True,
    ),
    SurveyQuestion(
        "job_targets",
        "目标岗位",
        "你希望找什么类型的工作和哪些岗位？请按优先级填写。",
        "例如：全职；首选大模型后训练算法工程师，其次Agent算法工程师",
        ["target.employment_types", "target.primary_roles", "target.secondary_roles"],
        True,
    ),
    SurveyQuestion(
        "location_work_mode",
        "地点与办公方式",
        "首选和可接受的工作城市有哪些？是否接受远程、混合办公或搬迁？",
        "例如：首选深圳、北京，可接受上海；接受现场或混合办公，可以搬迁",
        ["target.preferred_locations", "target.acceptable_locations", "target.work_modes", "constraints.relocation"],
        True,
    ),
    SurveyQuestion(
        "availability",
        "入职与实习安排",
        "最早何时可以入职？如果考虑实习，请说明每周天数、持续月数和转正意愿。",
        "例如：2027-07-01入职；实习可每周5天、连续6个月，希望转正",
        ["target.available_from", "target.internship.days_per_week", "target.internship.duration_months", "target.internship.conversion_intent"],
        True,
    ),
    SurveyQuestion(
        "compensation",
        "薪资期望",
        "你的最低和期望税前月薪是多少？对年终薪数是否有要求？",
        "例如：最低30K，期望35K-45K，14薪以上，可商议",
        ["target.salary.monthly_min_cny", "target.salary.monthly_max_cny", "target.salary.expected_salary_months", "target.salary.negotiable"],
    ),
    SurveyQuestion(
        "strengths_skills",
        "技能与核心优势",
        "最希望岗位匹配突出你的哪些技能、领域能力或个人优势？",
        "例如：GRPO、RLHF、分布式训练；能独立定位训练稳定性问题",
        ["capabilities.skills", "capabilities.user_confirmed_strengths"],
        True,
    ),
    SurveyQuestion(
        "achievements",
        "经历与成果证据",
        "请补充最能证明能力的1–3项经历或量化成果；简历已有内容可不重复。",
        "例如：主导284B模型训练；准确率提升11%；调参成本降低60%",
        ["evidence.user_highlights", "evidence.quantified_achievements"],
    ),
    SurveyQuestion(
        "company_industry",
        "行业与公司偏好",
        "偏好或排除哪些行业、业务方向、公司规模或发展阶段？",
        "例如：偏好AI基础设施或大模型公司，大中型/成长期以上；不考虑游戏博彩",
        ["target.preferred_industries", "target.excluded_industries", "preferences.company_sizes", "preferences.company_stages", "preferences.business_domains"],
    ),
    SurveyQuestion(
        "constraints",
        "求职硬约束",
        "有哪些不能接受的工作条件？对出差和加班强度有什么要求？",
        "例如：不接受长期出差和单休；可接受适度加班",
        ["constraints.travel_frequency", "constraints.overtime_preference", "constraints.deal_breakers"],
    ),
    SurveyQuestion(
        "languages_authorization",
        "语言与工作许可",
        "请说明可用于工作的语言水平，以及拥有工作许可的国家或地区。",
        "例如：中文母语、英语可工作交流；中国大陆和香港工作许可",
        ["capabilities.languages", "constraints.work_authorization"],
    ),
    SurveyQuestion(
        "matching_keywords",
        "匹配规则偏好",
        "岗位描述中有哪些必须词、加分词或排除词？",
        "例如：必须：RLHF；加分：Agent、多模态；排除：纯数据标注",
        ["matching_config.must_have_keywords", "matching_config.nice_to_have_keywords", "matching_config.excluded_keywords"],
    ),
    SurveyQuestion(
        "additional_context",
        "其他补充",
        "还有哪些会影响你选择岗位的信息？没有可留空。",
        "例如：希望团队有公开发表机会，重视技术成长和导师制度",
        ["preferences.culture_keywords", "questionnaire.additional_context"],
    ),
)


class SimpleSurvey:
    def questions(self) -> list[SurveyQuestion]:
        return list(SIMPLE_SURVEY)

    def collect_interactively(
        self,
        profile: UserProfile,
        *,
        previous_answers: dict[str, str] | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> dict[str, str]:
        answers = dict(previous_answers or {})
        output_fn("\n用户画像简版问卷（共12题）。直接回车可跳过，输入 :quit 保存当前进度。")
        output_fn(
            f"简历已识别：{profile.identity.get('name') or '未知姓名'} / "
            f"{profile.career.get('career_stage') or '职业阶段待确认'} / "
            f"{', '.join(profile.target.get('primary_roles', [])) or '目标岗位待确认'}"
        )
        for index, question in enumerate(SIMPLE_SURVEY, start=1):
            output_fn(f"\n{index}/12 [{question.angle}] {question.prompt}")
            output_fn(f"  {question.placeholder}")
            if answers.get(question.id):
                output_fn(f"  上次回答：{answers[question.id]}")
            raw = input_fn("> ").strip()
            if raw == ":quit":
                break
            if raw:
                answers[question.id] = raw
        return answers
