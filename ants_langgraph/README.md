# ANTS — LangGraph 实现

基于 [LangGraph](https://github.com/langchain-ai/langgraph) 的 ANTS 多 Agent 编码助手 MVP。

## 目录结构

```
ants_langgraph/
├── skills/                   # Skills 系统（技能注册与加载）
│   ├── skill.py              # Skill dataclass
│   └── registry.py           # SkillRegistry + 6 个内置技能
├── problems/                 # 项目问题文档
│   └── document.py           # ProblemEntry + ProblemDocument
├── graph/
│   ├── state.py              # ANTSState TypedDict（含 AgentPlanItem）
│   ├── builder.py            # build_ants_graph()
│   └── nodes/
│       ├── setup.py          # setup_session
│       ├── planner.py        # planner_node（含 Level 1 经验注入 + AgentPlan 生成）
│       ├── execution.py      # execution_phase_node + run_coder_task
│       ├── verification.py
│       ├── checkpoint.py     # phase_checkpoint_node（HITL interrupt）
│       └── finalize.py
├── agents/
│   ├── base.py               # BaseAgent 接口（含 Skills 支持方法）
│   ├── subagent.py           # SubAgent（动态加载 Skills）
│   ├── planner.py
│   ├── coder.py
│   ├── reviewer.py
│   └── tester.py
├── experience/
│   ├── entry.py              # ExperienceEntry dataclass
│   ├── library.py            # ExperienceLibrary（BM25 + 写入 + 反馈）
│   ├── retriever.py          # BM25Retriever + RetrievedExperience
│   ├── reflect.py            # reflect_and_save()
│   └── budget.py             # ExperienceBudgetManager（Token 预算管理）
├── shared_context/
│   └── context.py            # SharedContext（会话记忆持久化）
├── cli.py                    # CLI 入口
└── requirements.txt
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r ants_langgraph/requirements.txt

# 2. 设置 OpenAI API Key（或其他兼容模型）
export OPENAI_API_KEY=sk-...

# 3. 运行 ANTS
python -m ants_langgraph.cli "实现一个读取 CSV 文件的 Python 函数" /path/to/your/project
```

## 工作流程

```
setup_session → planner → [HITL: Phase 1 审批]
              → execution_phase → [HITL: Phase 2 审批]
              → verification_phase → [HITL: Phase 3 审批]
              → finalize
```

Planner 现在会同时生成**任务清单**和 **AgentPlan**（含每个 SubAgent 的技能分配），参见 [SKILLS_AND_AGENT_PLAN.md](../SKILLS_AND_AGENT_PLAN.md)。

每个阶段完成后，CLI 会暂停并等待人工输入：
- **[Enter]** — 批准，继续下一阶段
- **[r]** — 重做本阶段
- **[q]** — 终止会话

## Skills 系统

每个 SubAgent 可按需加载一组 Skills，实现灵活的角色组合：

```python
from ants_langgraph.skills import get_skill_registry
from ants_langgraph.agents.subagent import SubAgent

agent = SubAgent(
    agent_id="sub_coder_001",
    skill_names=["coder", "system_designer"],
    project_path="/path/to/project",
    phase_name="development",
)
result = await agent.run(task, context)
```

内置技能：`requirements_analyst`、`system_designer`、`coder`、`code_reviewer`、`tester`、`debugger`

## 问题文档

```python
from ants_langgraph.problems import get_problem_document

doc = get_problem_document("/path/to/project")
pid = await doc.record("ModuleNotFoundError", "pytest 找不到 src 模块")
await doc.resolve(pid, "pip install -e .")
```

问题文档存储于 `.ants/problems/problems.jsonl`，Agent 执行时自动查询并注入到 prompt。

## 经验库

会话结束后，`.ants/experience/` 目录下会保存本次积累的经验（JSONL 格式）。
下次运行时，相关经验会自动注入到 Agent 的 prompt 中（渐进式披露策略）。

## MVP 验证

参见 `../tests/mvp_validation.py`，验证三个核心指标：
1. **经验能被积累** — 第一次会话后 `.ants/experience/` 有新条目
2. **经验能被复用** — 第二次同类任务的 prompt 中包含历史经验
3. **注意力不被稀释** — 注入的经验总 token 数 ≤ 2000

Skills 与 ProblemDocument 的验证参见 `../tests/test_skills_and_problems.py`。

## 设计文档

- [Skills、问题文档与 Agent Plan 设计方案](../SKILLS_AND_AGENT_PLAN.md) — 本次改动的完整设计说明
- [实现方案详细设计](../IMPLEMENTATION_PLAN.md) — LangGraph vs ADK 整体方案
- [Agent 自我进化系统](../AGENT_EVOLUTION.md) — 经验库详细设计

