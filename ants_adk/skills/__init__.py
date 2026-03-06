"""Skills — on-demand role/capability loading for ANTS agents."""

from .skill import Skill
from .registry import SkillRegistry, get_skill_registry

__all__ = ["Skill", "SkillRegistry", "get_skill_registry"]
