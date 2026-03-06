# ANTS Skills、问题文档与 Agent Plan 设计方案

> **版本**：v1.0  
> **日期**：2026-03-06  
> **定位**：描述 Skills 系统、ProblemDocument（问题文档）、SubAgent 和 AgentPlan 的设计思路、模块结构与改动点，为后续维护提供完整参考。  
> **关联文档**：[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)、[AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md)、[ANTS_LITE.md](./ANTS_LITE.md)

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [整体架构变化](#2-整体架构变化)
3. [Skills 系统](#3-skills-系统)
4. [问题文档（ProblemDocument）](#4-问题文档problemdocument)
5. [SubAgent](#5-subagent)
6. [AgentPlanItem 与 AgentPlan](#6-agentplanitem-与-agentplan)
7. [Planner 改动](#7-planner-改动)
8. [OrchestratorAgent 改动（ADK）](#8-orchestratoragent-改动adk)
9. [BaseAgent 改动](#9-baseagent-改动)
10. [ANTSState 改动](#10-antsstate-改动)
11. [目录结构变更](#11-目录结构变更)
12. [数据流说明](#12-数据流说明)
13. [维护指南](#13-维护指南)

---

## 1. 背景与动机

### 1.1 原有架构的局限

原有的 ANTS 实现将 Agent 角色硬编码为三类：`coder`、`reviewer`、`tester`。每次 Planner 产出任务清单后，Orchestrator 把任务分发给对应的固定池（`CoderAgentPool` / `VerifyAgentPool`），Agent 行为完全由代码逻辑决定，无法按需扩展角色或能力。

痛点总结：

| 问题 | 影响 |
|------|------|
| 角色固定，无法灵活组合 | 新增"需求分析师"或"架构师"角色需要修改核心代码 |
| Agent 不感知已知问题 | 同一个 bug 多次被不同 Agent 踩中 |
| 无法按任务特点定制能力 | 安全审查任务和普通代码审查用同一个 Reviewer |
| 项目经验与角色能力混为一谈 | 经验库解决"项目知识"，但"角色能力"缺乏独立抽象 |

### 1.2 设计目标

本次改动引入三个互相配合的新概念，实现以下目标：

1. **Skills（技能）**：将 Agent 的角色和能力从代码中提取为数据，可按需加载、组合。
2. **ProblemDocument（问题文档）**：在经验库之外，专门维护项目已知问题（含解决方案），Agent 遇到问题时可主动查询。
3. **AgentPlan（Agent 计划）**：Planner 不再只产出任务清单，同时产出"谁来做、带什么技能"的 SubAgent 计划，Orchestrator 按计划动态实例化 SubAgent。

这三点合起来，让 ANTS 实现了问题陈述中的核心诉求：

> **一个 Agent Plan + 多个按需加载 Skill 的 SubAgent = 完整的任务执行体系**

---

## 2. 整体架构变化

### 2.1 旧架构（固定角色池）

```
Planner → 任务清单
                ↓
Orchestrator → CoderAgentPool（固定 N 个 CoderAgent）
             → VerifyAgentPool（固定 ReviewerAgent + TesterAgent）
```

### 2.2 新架构（动态 Skill 加载）

```
Planner → 任务清单 + AgentPlan（含每个 SubAgent 的 skill_names）
                ↓
Orchestrator → 按 AgentPlan 动态实例化 SubAgent（每个带指定 Skills）
             → SubAgent 加载 Skills → 构建角色 Prompt + 查询经验库 + 查询问题文档
             → 执行任务
             → 回写经验库 & 问题文档
```

### 2.3 关键交互图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ANTS 新架构                                 │
│                                                                       │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐  │
│  │  Planner    │────▶│  AgentPlan                               │  │
│  │  Agent      │     │  [{phase_name, agent_id, skill_names,    │  │
│  └─────────────┘     │    task_ids}, ...]                       │  │
│         │            └──────────────────────────────────────────┘  │
│         │ tasks                         │                            │
│         ▼                               ▼                            │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐  │
│  │ Orchestrator│────▶│  SubAgent（动态实例化）                   │  │
│  │  Agent      │     │                                          │  │
│  └─────────────┘     │  load_skills([skill_names])              │  │
│                       │       │                                   │  │
│                       │       ├── build_role_prompt()            │  │
│                       │       ├── query ExperienceLibrary        │  │
│                       │       └── query ProblemDocument          │  │
│                       │                                          │  │
│                       │  → LLM with assembled system prompt      │  │
│                       └──────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  .ants/                                                       │   │
│  │  ├── experience/    ← ExperienceLibrary（原有，积累经验）       │   │
│  │  └── problems/      ← ProblemDocument（新增，记录已知问题）     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Skills 系统

### 3.1 设计思路

Skills 系统把"Agent 扮演什么角色、具备什么能力"从代码逻辑中分离出来，变成可配置的数据结构。每个 Skill 包含：

- **role_prompt**：注入 Agent 系统提示词的角色描述
- **experience_categories**：该 Skill 优先查询的经验类别（对 ExperienceLibrary 的 query 参数进行定向过滤）

这样，"需求分析师"、"架构师"、"安全审查员"等新角色只需增加一条 Skill 注册，无需修改 Agent 执行代码。

### 3.2 Skill 数据结构

```python
@dataclass
class Skill:
    name: str                        # 唯一标识，如 "coder"
    description: str                 # 人类可读描述
    role_prompt: str                 # 注入 system prompt 的角色描述块
    experience_categories: list[str] # 优先查询的经验类别
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 注册键，全局唯一；用于 `skill_names` 列表引用 |
| `description` | `str` | 在 Agent 计划摘要中展示，方便人工审阅 |
| `role_prompt` | `str` | 完整的角色描述文本，多 Skill 时会合并 |
| `experience_categories` | `list[str]` | 影响 ExperienceLibrary.query 的 categories 参数 |

### 3.3 内置技能清单

| 技能名 | 描述 | 适用阶段 |
|--------|------|---------|
| `requirements_analyst` | 需求分析师 — 收集、分析并整理用户需求 | requirements |
| `system_designer` | 系统设计师 — 设计架构、接口规范 | design |
| `coder` | 编码工程师 — 实现功能，遵循项目规范 | development |
| `code_reviewer` | 代码审查员 — 检查质量、安全性 | testing |
| `tester` | 测试工程师 — 设计并执行测试用例 | testing |
| `debugger` | 调试专家 — 分析错误、查询问题文档 | development / testing |

### 3.4 SkillRegistry

`SkillRegistry` 是技能的中央注册表，提供以下接口：

```python
registry = get_skill_registry()               # 全局单例

skill = registry.get("coder")                 # 按名称查询
skills = registry.load_skills(["coder", "tester"])  # 批量加载
registry.register(custom_skill)              # 注册自定义技能

# 静态方法：合并多技能的 prompt 和经验类别
prompt = SkillRegistry.build_role_prompt(skills)
cats   = SkillRegistry.combined_experience_categories(skills)
```

**多技能组合规则**：
- 单技能：直接使用该技能的 `role_prompt`
- 多技能：前置"你同时承担以下角色和能力："，各 Skill 的 `role_prompt` 依次拼接
- 经验类别：取所有技能的 `experience_categories` 去重合并

### 3.5 文件位置

```
ants_langgraph/skills/
├── __init__.py     # 导出 Skill, SkillRegistry, get_skill_registry
├── skill.py        # Skill dataclass
└── registry.py     # SkillRegistry + 内置技能 + get_skill_registry()

ants_adk/skills/    # 与 ants_langgraph/skills/ 完全相同
├── __init__.py
├── skill.py
└── registry.py
```

> **注意**：两个包目前使用相同的 Skills 实现（文件内容一致），未来可考虑提取为共用包。

---

## 4. 问题文档（ProblemDocument）

### 4.1 设计思路

经验库（ExperienceLibrary）记录的是"已完成任务中提炼出的通用经验"，侧重于正向的方法论积累。**问题文档**则专门记录项目中出现的具体问题（bug、环境错误、配置陷阱等），以及已知解决方案。

两者定位对比：

| 维度 | ExperienceLibrary | ProblemDocument |
|------|-------------------|-----------------|
| 内容 | 通用规范、架构模式、工具用法 | 具体问题及其解法 |
| 写入时机 | 任务完成后自动反思（reflect） | Agent 遇到问题时手动记录 |
| 检索方式 | BM25 关键词相关度 | 关键词评分 |
| 生命周期 | active / deprecated / merged | open / resolved / wont_fix |
| 存储路径 | `.ants/experience/*.jsonl` | `.ants/problems/problems.jsonl` |

### 4.2 ProblemEntry 数据结构

```python
@dataclass
class ProblemEntry:
    id: str          # 唯一标识，如 "prob_20260306_120000_a1b2c3"
    title: str       # 简短标题
    description: str # 问题详细描述
    context: str     # 错误信息、堆栈追踪、相关代码片段
    solution: str    # 解决方案（解决后填写）
    status: str      # "open" | "resolved" | "wont_fix"
    tags: list[str]  # 标签，用于检索
    source_agent: str
    session_id: str
    created_at: str
    resolved_at: str | None
```

### 4.3 ProblemDocument 接口

```python
doc = get_problem_document(project_path)

# 记录新问题
pid = await doc.record(title, description, context, tags, source_agent, session_id)

# 解决问题
ok = await doc.resolve(problem_id, solution, status="resolved")

# 检索相关问题（关键词匹配，返回 top_k）
entries = await doc.query(problem, top_k=3)

# 列出所有（可按 status 过滤）
entries = await doc.list_all(status_filter="open")

# 生成 prompt 注入块
section = await doc.to_prompt_section(problem="当前问题描述", top_k=3)
```

### 4.4 Prompt 注入示例

当 Agent 执行任务时，如果问题文档中有相关条目，会在 system prompt 中注入如下文本：

```
【已知项目问题（按相关度排序）】
⚠️ [prob_001] ModuleNotFoundError: pytest 找不到 src 模块 → pip install -e .
✅ [prob_002] 数据库连接超时: 生产环境未配置连接池 → 参见 database/pool.py
```

图标含义：`⚠️` = open，`✅` = resolved，`🚫` = wont_fix

### 4.5 文件位置

```
ants_langgraph/problems/
├── __init__.py     # 导出 ProblemEntry, ProblemDocument, get_problem_document
└── document.py     # ProblemEntry + ProblemDocument + get_problem_document()

ants_adk/problems/  # 与 ants_langgraph/problems/ 完全相同
├── __init__.py
└── document.py
```

### 4.6 存储路径

```
<project_root>/.ants/problems/problems.jsonl
```

每行一条 JSON 记录，追加写入。解决（resolve）时全量重写该文件。

---

## 5. SubAgent

### 5.1 设计思路

`SubAgent` 是由 Orchestrator 按 AgentPlan 动态实例化的 Agent。与固定角色的 `CoderAgent` / `ReviewerAgent` 不同，SubAgent 的行为完全由它加载的 Skills 决定：

```
SubAgent(skill_names=["coder", "system_designer"])
  → load_skills() 加载两个 Skill 对象
  → build_role_prompt() 合并两个 role_prompt
  → skill_experience_categories() 合并两个 experience_categories
  → 执行任务时：查询经验库（用合并后的类别）+ 查询问题文档 + 组装 system prompt + 调用 LLM
```

### 5.2 System Prompt 组装逻辑

SubAgent 的 system prompt 按以下顺序拼接：

```
1. [技能角色 prompt]       ← build_role_prompt(loaded_skills)
2. [项目背景]              ← session_memory
3. [项目历史经验]           ← ExperienceLibrary.query() → budget.to_prompt_section()
4. [已知项目问题]           ← ProblemDocument.to_prompt_section()
5. [当前任务描述]           ← task.id + task.title + task.description
6. [执行规则]              ← 固定规则文本
```

每个块之间用空行分隔。任何空块（无经验、无问题）自动跳过，不产生冗余空段。

### 5.3 接口

```python
agent = SubAgent(
    agent_id="sub_coder_task_001",
    skill_names=["coder", "system_designer"],
    project_path="/path/to/project",
    phase_name="development",  # 仅用于日志
)
result = await agent.run(task, context)
# result: {"passed": bool, "output": dict}
```

### 5.4 LLM 后端

- **ants_langgraph**：使用 `langchain_openai.ChatOpenAI`（model="gpt-4o-mini"）
- **ants_adk**：使用 `google.generativeai.GenerativeModel`（model="gemini-2.0-flash"）

两个包的 SubAgent 实现逻辑相同，只有 LLM 调用方式不同。

### 5.5 与 CoderAgent 的关系

SubAgent **不替换** 原有的 CoderAgent / ReviewerAgent / TesterAgent。OrchestratorAgent 在执行时：
1. 先按 AgentPlan 运行对应 SubAgent（有 skill_names 指定的任务）
2. 对 AgentPlan 未覆盖的剩余 pending 任务，回退到 CoderAgentPool（保持向后兼容）

### 5.6 文件位置

```
ants_langgraph/agents/subagent.py
ants_adk/adk_agents/subagent.py
```

---

## 6. AgentPlanItem 与 AgentPlan

### 6.1 数据结构

```python
class AgentPlanItem(TypedDict):
    phase_name: str        # 阶段名，如 "requirements", "design", "development", "testing"
    agent_id: str          # 唯一标识，如 "sub_coder_task_001"
    skill_names: list[str] # 要加载的技能名列表
    task_ids: list[str]    # 分配给此 SubAgent 的任务 ID 列表
```

### 6.2 AgentPlan 在 ANTSState 中的位置

```python
class ANTSState(TypedDict):
    ...
    agent_plan: list[AgentPlanItem]   # Planner 产出，Orchestrator 消费
    loaded_skill_names: list[str]     # agent_plan 中所有 skill_names 的去重合集
    ...
```

### 6.3 phase_name 约定

| phase_name | 对应 Task.phase | 说明 |
|------------|-----------------|------|
| `planning` | 1 | 由 PlannerAgent 处理，通常无 SubAgent |
| `requirements` | 1/2 | 需求分析子阶段（可选） |
| `design` | 1/2 | 系统设计子阶段（可选） |
| `development` | 2 | 编码阶段，Orchestrator 默认使用此名称运行 Phase 2 SubAgent |
| `testing` | 3 | 验证阶段，Orchestrator 默认使用此名称运行 Phase 3 SubAgent |

> **重要**：OrchestratorAgent 的 `_run_subagents_for_phase()` 通过匹配 `phase_name` 字段来过滤 AgentPlan 中对应阶段的 SubAgent。Planner 输出的 `phase_name` 必须与 Orchestrator 使用的字符串一致（`"development"` 和 `"testing"`）。

---

## 7. Planner 改动

### 7.1 改动前后对比

| 维度 | 改动前 | 改动后 |
|------|--------|--------|
| 输出 | 任务清单（JSON 数组） | 任务清单 + AgentPlan（JSON 对象） |
| 系统提示词 | 无技能相关内容 | 列出可用 Skill 名称供 LLM 参考 |
| 返回值（LangGraph 节点） | `{"tasks": [...]}` | `{"tasks": [...], "agent_plan": [...], "loaded_skill_names": [...]}` |
| 返回值（ADK PlannerAgent.run） | `list[dict]` | `tuple[list[dict], list[dict]]` |

### 7.2 新增内部函数

**`_parse_planner_output(content) → (tasks, agent_plan)`**

解析 LLM 输出，支持两种格式：
- **结构化格式**（优先）：`{"tasks": [...], "agent_plan": [...]}`
- **降级格式**（兼容旧版）：`[...]`（纯任务数组），自动调用 `_default_agent_plan()` 补全

**`_default_agent_plan(tasks) → list[AgentPlanItem]`**

当 LLM 未输出 agent_plan 时的降级逻辑：

| `assigned_agent` | 生成的 `skill_names` | `phase_name` |
|------------------|---------------------|--------------|
| `"coder"` | `["coder"]` | `"development"` |
| `"reviewer"` | `["code_reviewer"]` | `"testing"` |
| `"tester"` | `["tester"]` | `"testing"` |

### 7.3 LLM 提示词变化（LangGraph）

新增两处内容：
1. 在系统提示词中列出 `get_skill_registry().list_names()` 的结果，作为 `skill_names` 可选值的参考
2. 明确要求 LLM 同时输出 `agent_plan` 数组

---

## 8. OrchestratorAgent 改动（ADK）

### 8.1 Phase 2 执行流程变化

**改动前**：
```python
await self._coder_pool.execute_tasks(phase2_tasks, session_state)
```

**改动后**：
```python
# 1. 先运行 AgentPlan 中的 SubAgent（"development" 阶段）
await self._run_subagents_for_phase("development", agent_plan, tasks, session_state)

# 2. 对未被 AgentPlan 覆盖的剩余 pending 任务，回退到 CoderAgentPool
uncovered = [t for t in tasks if t["phase"] == 2 and t["status"] == "pending"
             and t["id"] not in covered_ids]
if uncovered:
    await self._coder_pool.execute_tasks(uncovered, session_state)
```

### 8.2 Phase 3 执行流程变化

类似地，先运行 `"testing"` 阶段的 SubAgent，再用 `VerifyAgentPool` 处理剩余任务。

### 8.3 get_phase_summary 改动

新增 SubAgent 信息展示：
```
=== Phase 2 完成摘要 ===
目标：实现 CSV 读取功能
任务：3/3 已完成
SubAgent：2 个
  • [sub_coder_task_001] 技能：coder, system_designer
  • [sub_coder_task_002] 技能：coder
  ✅ [task_001] 实现 read_csv()
  ...
```

### 8.4 SESSION_KEYS 变化

新增 `"agent_plan": "ants.agent_plan"` 键。

---

## 9. BaseAgent 改动

在 `ants_langgraph/agents/base.py` 中，为 `BaseAgent` 抽象基类新增三个方法：

```python
class BaseAgent(ABC):
    loaded_skills: list[Skill]          # 新增：已加载的技能列表

    def load_skills(self, skill_names, registry=None): ...
    # 从注册表加载 Skill 对象，存入 self.loaded_skills

    def build_role_prompt(self) -> str: ...
    # 调用 SkillRegistry.build_role_prompt(self.loaded_skills)

    def skill_experience_categories(self) -> list[str]: ...
    # 调用 SkillRegistry.combined_experience_categories(self.loaded_skills)
```

**向后兼容**：原有的 `PlannerAgent`、`CoderAgent`、`ReviewerAgent`、`TesterAgent` 均继承 `BaseAgent`，但它们的 `run()` 方法不调用上述新方法，因此行为不变。新方法只在 `SubAgent` 中被使用。

---

## 10. ANTSState 改动

在 `ants_langgraph/graph/state.py` 中：

### 10.1 新增 TypedDict

```python
class AgentPlanItem(TypedDict):
    phase_name: str
    agent_id: str
    skill_names: list[str]
    task_ids: list[str]
```

### 10.2 ANTSState 新增字段

```python
class ANTSState(TypedDict):
    ...                                # 原有字段不变
    agent_plan: list[AgentPlanItem]    # 新增
    loaded_skill_names: list[str]      # 新增
```

### 10.3 setup_session 初始化

`setup_session` 节点的返回值新增：
```python
{
    ...
    "agent_plan": [],
    "loaded_skill_names": [],
}
```

---

## 11. 目录结构变更

### 11.1 ants_langgraph

```diff
 ants_langgraph/
+├── skills/                  # 新增
+│   ├── __init__.py
+│   ├── skill.py             # Skill dataclass
+│   └── registry.py          # SkillRegistry + 内置技能
+├── problems/                # 新增
+│   ├── __init__.py
+│   └── document.py          # ProblemEntry + ProblemDocument
 ├── graph/
 │   ├── state.py             # 新增 AgentPlanItem；ANTSState 新增 2 个字段
 │   └── nodes/
-│       └── planner.py       # 改动：输出 agent_plan；新增内部函数
+│       └── planner.py       # 改动：输出 agent_plan；新增 _parse_planner_output、_default_agent_plan
 ├── agents/
 │   ├── base.py              # 改动：新增 load_skills、build_role_prompt、skill_experience_categories
+│   └── subagent.py          # 新增：SubAgent
 └── ...（其余文件不变）
```

### 11.2 ants_adk

```diff
 ants_adk/
+├── skills/                  # 新增（与 ants_langgraph/skills/ 内容相同）
+│   ├── __init__.py
+│   ├── skill.py
+│   └── registry.py
+├── problems/                # 新增（与 ants_langgraph/problems/ 内容相同）
+│   ├── __init__.py
+│   └── document.py
 ├── adk_agents/
-│   ├── planner.py           # 改动：run() 返回 tuple；新增 _parse_planner_output、_default_agent_plan
+│   ├── planner.py           # 改动：run() 返回 (tasks, agent_plan) tuple
+│   ├── subagent.py          # 新增：SubAgent（ADK 版，使用 Gemini）
 │   └── orchestrator.py      # 改动：使用 SubAgent；新增 _run_subagents_for_phase；SESSION_KEYS 新增 agent_plan
 └── ...（其余文件不变）
```

---

## 12. 数据流说明

### 12.1 完整执行流（LangGraph）

```
用户输入 goal
  │
  ▼
setup_session
  → 初始化 agent_plan=[], loaded_skill_names=[]
  │
  ▼
planner_node
  → 查询 ExperienceLibrary（Level 1）
  → 调用 LLM（含可用 Skill 列表）
  → 解析输出：tasks + agent_plan
  → 写回 state: tasks, agent_plan, loaded_skill_names
  │
  ▼
[HITL Phase 1 checkpoint]
  │
  ▼
execution_phase_node
  （注：LangGraph 版当前仍使用 run_coder_task，
    SubAgent 主要在 ADK 版 OrchestratorAgent 中使用；
    LangGraph 版的 SubAgent 集成可在后续迭代中完成）
  │
  ▼
[HITL Phase 2 checkpoint]
  │
  ▼
verification_phase_node
  │
  ▼
[HITL Phase 3 checkpoint]
  │
  ▼
finalize_session_node
```

### 12.2 SubAgent 执行流（ADK）

```
OrchestratorAgent._run_subagents_for_phase("development", agent_plan, tasks, state)
  │
  ├── 过滤 agent_plan 中 phase_name == "development" 的条目
  │
  └── 对每个 AgentPlanItem，asyncio.gather() 并行执行：
      │
      SubAgent(agent_id, skill_names, project_path)
        │
        ├── load_skills(skill_names)        → 从 SkillRegistry 加载 Skill 对象
        ├── skill_experience_categories()  → 合并所有技能的 experience_categories
        │
        ├── ExperienceLibrary.query(desc, agent_id, categories=merged_cats)
        │     → budget.try_add()
        │     → budget.to_prompt_section()
        │
        ├── ProblemDocument.to_prompt_section(desc)
        │
        ├── 组装 system prompt（role + background + experience + problems + task + rules）
        │
        ├── LLM.generate_content()
        │
        └── asyncio.create_task(reflect_and_save(...))  → 异步写回经验库
```

---

## 13. 维护指南

### 13.1 添加新技能

在 `ants_langgraph/skills/registry.py`（和 `ants_adk/skills/registry.py`）的 `_BUILTIN_SKILLS` 字典中添加：

```python
"security_auditor": Skill(
    name="security_auditor",
    description="安全审计员 — 识别安全漏洞和合规问题",
    role_prompt=(
        "你是一名安全审计员。你的职责是：\n"
        "1. 识别 SQL 注入、XSS、CSRF 等安全漏洞\n"
        "2. 检查依赖包的 CVE\n"
        "3. 输出安全报告"
    ),
    experience_categories=["debug_pattern", "project_convention"],
),
```

注册后，Planner 提示词中会自动包含该技能名，LLM 可在 AgentPlan 中引用它。

### 13.2 自定义技能注册（运行时）

```python
from ants_langgraph.skills import Skill, get_skill_registry

registry = get_skill_registry()
registry.register(Skill(
    name="my_custom_skill",
    description="...",
    role_prompt="...",
    experience_categories=["domain_knowledge"],
))
```

### 13.3 记录和解决项目问题

```python
from ants_langgraph.problems import get_problem_document

doc = get_problem_document("/path/to/project")

# Agent 遇到问题时记录
pid = await doc.record(
    title="pytest ModuleNotFoundError",
    description="运行 pytest 时找不到 src 模块",
    context="Error: ModuleNotFoundError: No module named 'src'",
    tags=["pytest", "import"],
    source_agent="tester",
)

# 解决后更新
await doc.resolve(pid, solution="在项目根目录执行 pip install -e .")
```

### 13.4 查询已知问题（Agent 内部）

在 SubAgent.run() 中，问题文档查询已自动完成。若需在其他地方手动查询：

```python
from ants_langgraph.problems import get_problem_document

doc = get_problem_document(project_path)
section = await doc.to_prompt_section(
    problem="当前遇到的问题描述",
    top_k=3,
)
# section 可直接拼接到 system prompt 中
```

### 13.5 扩展 AgentPlan 阶段

若需新增阶段（如独立的 `design` 阶段），需同步修改：
1. `OrchestratorAgent.run()` — 在 Phase 1/2 之间插入 `_run_subagents_for_phase("design", ...)` 调用
2. Planner 提示词 — 在阶段说明中加入 `design` 阶段的描述

### 13.6 LangGraph 版 SubAgent 集成（待完成）

当前 LangGraph 版的 `execution_phase_node` 和 `verification_phase_node` 仍使用原有的 `run_coder_task` / `run_verify_task` 函数。SubAgent 已实现但尚未集成到 LangGraph 执行节点中。后续迭代建议：
- 在 `execution_phase_node` 中读取 `state["agent_plan"]`，按 `phase_name == "development"` 过滤后实例化 SubAgent
- 保留 `run_coder_task` 作为降级备选

### 13.7 测试

新功能的测试位于 `tests/test_skills_and_problems.py`，覆盖：
- `SkillRegistry` 内置技能、自定义注册、Prompt 组合
- `ProblemDocument` 记录 / 查询 / 解决 / 持久化
- `AgentPlanItem` 结构
- `_default_agent_plan` 降级逻辑
- `_parse_planner_output` 结构化与降级解析

运行方式：
```bash
python -m pytest tests/test_skills_and_problems.py -v
```

---

*文档维护建议：本文档应与代码同步更新。每次修改 Skills 定义、ProblemDocument 接口或 AgentPlan 结构时，请同步更新对应章节。*
