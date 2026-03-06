# ANTS — Google ADK 实现

基于 [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 的 ANTS 多 Agent 编码助手。

## 目录结构

```
ants_adk/
├── skills/                    # Skills 系统（与 ants_langgraph/skills/ 相同）
│   ├── skill.py               # Skill dataclass
│   └── registry.py            # SkillRegistry + 6 个内置技能
├── problems/                  # 项目问题文档（与 ants_langgraph/problems/ 相同）
│   └── document.py            # ProblemEntry + ProblemDocument
├── adk_agents/
│   ├── orchestrator.py        # OrchestratorAgent（Root Agent，管理阶段流转 + HITL）
│   ├── planner.py             # PlannerAgent（生成任务清单 + AgentPlan，含 Level 1 经验注入）
│   ├── subagent.py            # SubAgent（动态加载 Skills，ADK/Gemini 版）
│   ├── coder_pool.py          # CoderAgentPool + CoderAgent（并行编码，降级备选）
│   ├── verify_pool.py         # VerifyAgentPool（ReviewerAgent + TesterAgent，降级备选）
│   └── hitl_tool.py           # HumanApprovalTool（长运行工具 HITL 模式）
├── experience/                # 与 ants_langgraph 共用相同接口
│   ├── entry.py
│   ├── library.py
│   ├── retriever.py
│   ├── reflect.py
│   └── budget.py
├── shared_context/
│   └── context.py
├── cli.py                     # CLI 入口
└── requirements.txt
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r ants_adk/requirements.txt

# 2. 设置 Google API Key
export GOOGLE_API_KEY=...

# 3. 运行 ANTS
python -m ants_adk.cli "实现一个读取 CSV 文件的 Python 函数" /path/to/your/project
```

## Agent 层次结构

```
OrchestratorAgent（Root Agent）
  ├── PlannerAgent              → Phase 1：生成任务清单 + AgentPlan
  ├── SubAgent × N（动态实例化）  → Phase 2/3：按 Skills 执行任务
  │   每个 SubAgent 携带指定技能，如 ["coder", "system_designer"]
  ├── CoderAgentPool            → Phase 2 降级：覆盖未被 AgentPlan 分配的任务
  └── VerifyAgentPool           → Phase 3 降级：覆盖未被 AgentPlan 分配的验证任务
```

## Skills 系统

Planner 输出的 AgentPlan 为每个 SubAgent 指定技能。OrchestratorAgent 按计划动态实例化：

```python
agent = SubAgent(
    agent_id="sub_coder_task_001",
    skill_names=["coder", "system_designer"],
    project_path="/path/to/project",
    phase_name="development",
    model="gemini-2.0-flash",
)
result = await agent.run(session_state)
```

内置技能：`requirements_analyst`、`system_designer`、`coder`、`code_reviewer`、`tester`、`debugger`

## HITL 机制

ADK 通过 `HumanApprovalTool` 的 long-running 模式实现 HITL：
1. `OrchestratorAgent` 在每个阶段结束后调用 `request_approval()`
2. ADK Runner 返回 `LongRunningFunctionCall` 事件（挂起 Agent）
3. CLI/Web 显示审批界面，等待人工输入
4. 人工提交决策后，调用 `runner.resume()` 恢复执行

## Session State 键名约定

| 键 | 说明 |
|----|------|
| `ants.goal` | 当前会话目标 |
| `ants.project_path` | 项目路径 |
| `ants.tasks` | 任务清单 |
| `ants.agent_plan` | Agent 计划（SubAgent + 技能分配） |
| `ants.current_phase` | 当前阶段（1/2/3） |
| `ants.session_memory` | 会话记忆摘要 |
| `ants.experience_budget_used` | 已用经验 token 数 |

## 与 LangGraph 方案的区别

| 维度 | LangGraph（ants_langgraph） | ADK（ants_adk） |
|------|--------------------------|---------------|
| HITL | `interrupt()` 原生支持 | Long-running tool |
| 并行 | `asyncio.gather()` | `ParallelAgent`（原生） |
| 状态持久化 | `SqliteSaver` | `DatabaseSessionService` |
| 调试 UI | LangGraph Studio | `adk web`（本地）|
| MCP 集成 | LangChain 适配 | 原生 MCP Client |
| SubAgent 集成 | AgentPlan 已写入 State，执行节点待集成 | OrchestratorAgent 完整集成 |

**推荐**：先用 `ants_langgraph` 验证 MVP，成熟后迁移到 `ants_adk`。

## 设计文档

- [Skills、问题文档与 Agent Plan 设计方案](../SKILLS_AND_AGENT_PLAN.md) — 本次改动的完整设计说明
- [实现方案详细设计](../IMPLEMENTATION_PLAN.md) — LangGraph vs ADK 整体方案
- [Agent 自我进化系统](../AGENT_EVOLUTION.md) — 经验库详细设计

