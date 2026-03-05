"""Skill — defines a role/capability that an agent can load on-demand."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    """A named capability that shapes how an agent behaves.

    Each skill provides:
    - A ``role_prompt`` injected into the agent's system prompt.
    - A list of ``experience_categories`` the skill prioritises when
      querying the project experience library.
    """

    #: Unique identifier (e.g. "coder", "requirements_analyst").
    name: str

    #: Human-readable description shown in plans and logs.
    description: str

    #: System-prompt block that defines the agent's role when this skill is active.
    role_prompt: str

    #: Experience categories this skill is most interested in.
    experience_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "role_prompt": self.role_prompt,
            "experience_categories": self.experience_categories,
        }
