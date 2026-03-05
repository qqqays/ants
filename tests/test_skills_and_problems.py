"""Tests for the Skills system and ProblemDocument.

Validates:
1. SkillRegistry built-in skills are accessible
2. load_skills returns correct Skill objects
3. build_role_prompt combines prompts correctly
4. combined_experience_categories deduplicates correctly
5. ProblemDocument record / query / resolve lifecycle
6. SubAgent builds a system prompt that includes skill role_prompt
7. Planner _default_agent_plan generates correct skill assignments
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ants_langgraph.skills.skill import Skill
from ants_langgraph.skills.registry import SkillRegistry, get_skill_registry
from ants_langgraph.problems.document import ProblemDocument, get_problem_document
from ants_langgraph.graph.state import AgentPlanItem
from ants_langgraph.graph.nodes.planner import _default_agent_plan, _parse_planner_output


# ── SkillRegistry ─────────────────────────────────────────────────────────────

def test_registry_builtin_skills():
    """All expected built-in skills are registered."""
    reg = SkillRegistry()
    expected = {"requirements_analyst", "system_designer", "coder", "code_reviewer", "tester", "debugger"}
    assert expected.issubset(set(reg.list_names())), (
        f"Missing built-in skills: {expected - set(reg.list_names())}"
    )
    print(f"✅ 内置技能：{reg.list_names()}")


def test_registry_get():
    """get() returns the correct Skill."""
    reg = SkillRegistry()
    skill = reg.get("coder")
    assert skill is not None
    assert skill.name == "coder"
    assert skill.role_prompt
    assert "project_convention" in skill.experience_categories
    print(f"✅ get('coder') → {skill.name}")


def test_registry_get_unknown():
    """get() returns None for unknown skill name."""
    reg = SkillRegistry()
    assert reg.get("nonexistent_skill_xyz") is None
    print("✅ get(unknown) → None")


def test_registry_load_skills():
    """load_skills returns matching Skill objects, skips unknowns."""
    reg = SkillRegistry()
    skills = reg.load_skills(["coder", "tester", "nonexistent"])
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"coder", "tester"}
    print(f"✅ load_skills → {names}")


def test_registry_register_custom():
    """Custom skills can be registered and retrieved."""
    reg = SkillRegistry()
    custom = Skill(
        name="custom_skill",
        description="Custom test skill",
        role_prompt="You are a custom agent.",
        experience_categories=["domain_knowledge"],
    )
    reg.register(custom)
    assert reg.get("custom_skill") is custom
    print("✅ register custom skill")


def test_build_role_prompt_empty():
    """build_role_prompt returns empty string for no skills."""
    assert SkillRegistry.build_role_prompt([]) == ""
    print("✅ build_role_prompt([]) → ''")


def test_build_role_prompt_single():
    """build_role_prompt returns the skill's role_prompt directly."""
    reg = SkillRegistry()
    skills = reg.load_skills(["coder"])
    prompt = SkillRegistry.build_role_prompt(skills)
    assert prompt == skills[0].role_prompt
    print(f"✅ single skill prompt: {prompt[:40]}...")


def test_build_role_prompt_multiple():
    """build_role_prompt combines multiple skills."""
    reg = SkillRegistry()
    skills = reg.load_skills(["coder", "code_reviewer"])
    prompt = SkillRegistry.build_role_prompt(skills)
    assert "编码" in prompt or "coder" in prompt.lower() or skills[0].role_prompt[:10] in prompt
    assert "审查" in prompt or "reviewer" in prompt.lower() or skills[1].role_prompt[:10] in prompt
    print(f"✅ multi-skill prompt length: {len(prompt)}")


def test_combined_experience_categories():
    """combined_experience_categories deduplicates across skills."""
    reg = SkillRegistry()
    # coder has project_convention; code_reviewer also has project_convention
    skills = reg.load_skills(["coder", "code_reviewer"])
    cats = SkillRegistry.combined_experience_categories(skills)
    # project_convention should appear exactly once
    assert cats.count("project_convention") == 1
    print(f"✅ deduped categories: {cats}")


def test_get_skill_registry_singleton():
    """get_skill_registry() returns the same instance each time."""
    r1 = get_skill_registry()
    r2 = get_skill_registry()
    assert r1 is r2
    print("✅ singleton registry")


# ── ProblemDocument ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_problem_record_and_list():
    """Recording a problem persists it and list_all returns it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = get_problem_document(tmpdir)
        pid = await doc.record(
            title="ModuleNotFoundError",
            description="pytest 找不到 src 模块",
            context="ImportError: No module named 'src'",
            tags=["pytest", "import"],
            source_agent="tester",
        )
        assert pid.startswith("prob_")

        entries = await doc.list_all()
        assert len(entries) == 1
        assert entries[0].title == "ModuleNotFoundError"
        assert entries[0].status == "open"
        print(f"✅ record + list_all: {entries[0].id}")


@pytest.mark.asyncio
async def test_problem_query():
    """query() returns relevant problems by keyword match."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = get_problem_document(tmpdir)
        await doc.record("ModuleNotFoundError", "pytest 找不到 src 模块", tags=["pytest"])
        await doc.record("ConnectionRefused", "数据库连接被拒绝", tags=["database"])

        results = await doc.query("pytest import 错误")
        assert len(results) >= 1
        assert any("Module" in r.title or "pytest" in " ".join(r.tags) for r in results)
        print(f"✅ query matched {len(results)} problems")


@pytest.mark.asyncio
async def test_problem_resolve():
    """resolve() updates status and solution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = get_problem_document(tmpdir)
        pid = await doc.record("ImportError", "模块未找到")

        ok = await doc.resolve(pid, solution="pip install -e .")
        assert ok

        entries = await doc.list_all()
        entry = entries[0]
        assert entry.status == "resolved"
        assert entry.solution == "pip install -e ."
        assert entry.resolved_at is not None
        print(f"✅ resolve: {entry.status}, solution={entry.solution}")


@pytest.mark.asyncio
async def test_problem_to_prompt_section():
    """to_prompt_section() returns non-empty string when problems exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = get_problem_document(tmpdir)
        await doc.record(
            "pytest 错误",
            "找不到 conftest.py",
            context="ERRORS: conftest.py not found",
            tags=["pytest"],
        )
        section = await doc.to_prompt_section(problem="pytest 错误 conftest")
        assert "已知项目问题" in section
        assert "pytest" in section.lower() or "conftest" in section.lower() or "错误" in section
        print(f"✅ to_prompt_section:\n{section}")


@pytest.mark.asyncio
async def test_problem_resolve_unknown():
    """resolve() returns False for unknown ID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = get_problem_document(tmpdir)
        ok = await doc.resolve("nonexistent_id", "some solution")
        assert not ok
        print("✅ resolve unknown → False")


@pytest.mark.asyncio
async def test_problem_persistence():
    """Problems persist across ProblemDocument instances (same path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc1 = ProblemDocument(tmpdir)
        pid = await doc1.record("Issue A", "Description A")

        doc2 = ProblemDocument(tmpdir)
        entries = await doc2.list_all()
        assert any(e.id == pid for e in entries)
        print(f"✅ persistence across instances: {pid}")


# ── Default AgentPlan generation ──────────────────────────────────────────────

def test_default_agent_plan_coder():
    """_default_agent_plan maps coder tasks to 'coder' skill."""
    tasks = [
        {"id": "t1", "title": "实现功能", "description": "...",
         "assigned_agent": "coder", "phase": 2, "depends_on": [], "status": "pending", "output": None},
    ]
    plan = _default_agent_plan(tasks)
    assert len(plan) == 1
    assert plan[0]["skill_names"] == ["coder"]
    assert plan[0]["phase_name"] == "development"
    assert "t1" in plan[0]["task_ids"]
    print(f"✅ default plan coder: {plan[0]}")


def test_default_agent_plan_reviewer_tester():
    """_default_agent_plan maps reviewer→code_reviewer, tester→tester."""
    tasks = [
        {"id": "t2", "assigned_agent": "reviewer", "phase": 3,
         "title": "", "description": "", "depends_on": [], "status": "pending", "output": None},
        {"id": "t3", "assigned_agent": "tester", "phase": 3,
         "title": "", "description": "", "depends_on": [], "status": "pending", "output": None},
    ]
    plan = _default_agent_plan(tasks)
    reviewer_item = next(p for p in plan if "t2" in p["task_ids"])
    tester_item = next(p for p in plan if "t3" in p["task_ids"])
    assert reviewer_item["skill_names"] == ["code_reviewer"]
    assert tester_item["skill_names"] == ["tester"]
    assert reviewer_item["phase_name"] == "testing"
    print(f"✅ default plan reviewer/tester: {[p['skill_names'] for p in plan]}")


def test_parse_planner_output_structured():
    """_parse_planner_output handles structured JSON with tasks + agent_plan."""
    import json as _json
    payload = _json.dumps({
        "tasks": [
            {"id": "t1", "title": "T1", "description": "Do it",
             "assigned_agent": "coder", "phase": 2,
             "depends_on": [], "status": "pending", "output": None},
        ],
        "agent_plan": [
            {"phase_name": "development", "agent_id": "sub_coder_t1",
             "skill_names": ["coder", "system_designer"], "task_ids": ["t1"]},
        ],
    })
    tasks, agent_plan = _parse_planner_output(payload)
    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"
    assert len(agent_plan) == 1
    assert agent_plan[0]["skill_names"] == ["coder", "system_designer"]
    assert agent_plan[0]["phase_name"] == "development"
    print(f"✅ parse structured output: {agent_plan[0]}")


def test_parse_planner_output_fallback():
    """_parse_planner_output falls back to default plan on bare array."""
    import json as _json
    payload = _json.dumps([
        {"id": "t1", "title": "T1", "description": "Do it",
         "assigned_agent": "coder", "phase": 2,
         "depends_on": [], "status": "pending", "output": None},
    ])
    tasks, agent_plan = _parse_planner_output(payload)
    assert len(tasks) == 1
    assert len(agent_plan) == 1
    assert agent_plan[0]["skill_names"] == ["coder"]
    print(f"✅ parse fallback: {agent_plan[0]}")


# ── AgentPlanItem TypedDict ───────────────────────────────────────────────────

def test_agent_plan_item_fields():
    """AgentPlanItem TypedDict can be constructed with all required fields."""
    item = AgentPlanItem(
        phase_name="development",
        agent_id="sub_coder_001",
        skill_names=["coder"],
        task_ids=["task_001"],
    )
    assert item["phase_name"] == "development"
    assert item["skill_names"] == ["coder"]
    print(f"✅ AgentPlanItem: {item}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def run_async():
        await test_problem_record_and_list()
        await test_problem_query()
        await test_problem_resolve()
        await test_problem_to_prompt_section()
        await test_problem_resolve_unknown()
        await test_problem_persistence()

    # Sync tests
    test_registry_builtin_skills()
    test_registry_get()
    test_registry_get_unknown()
    test_registry_load_skills()
    test_registry_register_custom()
    test_build_role_prompt_empty()
    test_build_role_prompt_single()
    test_build_role_prompt_multiple()
    test_combined_experience_categories()
    test_get_skill_registry_singleton()
    test_default_agent_plan_coder()
    test_default_agent_plan_reviewer_tester()
    test_parse_planner_output_structured()
    test_parse_planner_output_fallback()
    test_agent_plan_item_fields()

    asyncio.run(run_async())
    print("\n=== 所有技能与问题文档测试通过 ✅ ===")
