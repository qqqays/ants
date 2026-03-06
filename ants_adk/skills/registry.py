"""SkillRegistry — central registry of built-in and custom skills."""

from __future__ import annotations

from .skill import Skill

# ── Built-in skills ───────────────────────────────────────────────────────────

_BUILTIN_SKILLS: dict[str, Skill] = {
    "requirements_analyst": Skill(
        name="requirements_analyst",
        description="收集、分析并整理用户需求，产出需求文档",
        role_prompt=(
            "你是一名需求分析师。你的职责是：\n"
            "1. 理解并拆解用户目标\n"
            "2. 识别功能需求与非功能需求\n"
            "3. 输出清晰的需求列表和验收标准\n"
            "4. 发现歧义时主动提问澄清"
        ),
        experience_categories=["domain_knowledge", "project_convention"],
    ),
    "system_designer": Skill(
        name="system_designer",
        description="设计系统架构、模块划分与接口规范，产出设计文档",
        role_prompt=(
            "你是一名系统设计师。你的职责是：\n"
            "1. 根据需求设计高层架构\n"
            "2. 划分模块与组件，定义接口契约\n"
            "3. 识别技术风险并提出缓解方案\n"
            "4. 遵循项目已有的架构模式"
        ),
        experience_categories=["arch_pattern", "project_convention", "domain_knowledge"],
    ),
    "coder": Skill(
        name="coder",
        description="实现具体功能，编写高质量、可维护的代码",
        role_prompt=(
            "你是一名编码工程师。你的职责是：\n"
            "1. 按照设计文档实现功能\n"
            "2. 遵循项目编码规范\n"
            "3. 编写必要的单元测试\n"
            "4. 遇到不确定情况时查询项目历史经验"
        ),
        experience_categories=["project_convention", "tool_usage", "debug_pattern"],
    ),
    "code_reviewer": Skill(
        name="code_reviewer",
        description="审查代码质量、安全性与可维护性",
        role_prompt=(
            "你是一名代码审查员。你的职责是：\n"
            "1. 检查代码是否符合项目规范\n"
            "2. 识别潜在的安全漏洞\n"
            "3. 评估可读性与可维护性\n"
            "4. 给出具体的改进建议"
        ),
        experience_categories=["project_convention", "debug_pattern"],
    ),
    "tester": Skill(
        name="tester",
        description="设计并执行测试用例，确保功能正确性",
        role_prompt=(
            "你是一名测试工程师。你的职责是：\n"
            "1. 根据需求设计测试用例（覆盖正常路径与边界条件）\n"
            "2. 执行测试并记录结果\n"
            "3. 对失败用例定位根因并反馈给开发团队\n"
            "4. 维护测试文档"
        ),
        experience_categories=["environment", "tool_usage", "debug_pattern"],
    ),
    "debugger": Skill(
        name="debugger",
        description="排查已知问题并加载问题文档辅助定位",
        role_prompt=(
            "你是一名调试专家。你的职责是：\n"
            "1. 分析错误信息和堆栈追踪\n"
            "2. 查询项目历史问题文档寻找已知解法\n"
            "3. 提出并验证假设\n"
            "4. 将解决方案记录回问题文档"
        ),
        experience_categories=["debug_pattern", "environment", "tool_usage"],
    ),
}


class SkillRegistry:
    """Registry of available skills.

    Supports built-in skills and allows registering custom ones.
    Thread-safe for reads; writes should happen at startup.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = dict(_BUILTIN_SKILLS)

    # ── Registration ─────────────────────────────────────────────────

    def register(self, skill: Skill) -> None:
        """Register a custom skill (overwrites if name already exists)."""
        self._skills[skill.name] = skill

    # ── Lookup ───────────────────────────────────────────────────────

    def get(self, name: str) -> Skill | None:
        """Return a skill by name, or None if not found."""
        return self._skills.get(name)

    def load_skills(self, names: list[str]) -> list[Skill]:
        """Return skills for the given names, silently skipping unknowns."""
        result: list[Skill] = []
        for name in names:
            skill = self._skills.get(name)
            if skill:
                result.append(skill)
        return result

    def list_names(self) -> list[str]:
        """Return all registered skill names."""
        return list(self._skills.keys())

    # ── Prompt assembly ──────────────────────────────────────────────

    @staticmethod
    def build_role_prompt(skills: list[Skill]) -> str:
        """Combine multiple skill role_prompts into a single system-prompt block."""
        if not skills:
            return ""
        if len(skills) == 1:
            return skills[0].role_prompt
        parts = ["你同时承担以下角色和能力：\n"]
        for skill in skills:
            parts.append(f"【{skill.description}】\n{skill.role_prompt}")
        return "\n\n".join(parts)

    @staticmethod
    def combined_experience_categories(skills: list[Skill]) -> list[str]:
        """Merge and deduplicate experience categories from all skills."""
        seen: set[str] = set()
        result: list[str] = []
        for skill in skills:
            for cat in skill.experience_categories:
                if cat not in seen:
                    seen.add(cat)
                    result.append(cat)
        return result


# ── Module-level singleton ────────────────────────────────────────────────────

_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Return the module-level singleton SkillRegistry."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
