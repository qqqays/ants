# ANTS 实现方案详细设计：LangGraph vs Google ADK

> **版本**：v1.0  
> **日期**：2026-03-04  
> **状态**：供讨论  
> **关联文档**：[洞察报告](./AGENT_LANDSCAPE_2025_2026.md)、[精简落地方案](./ANTS_LITE.md)、[进化系统设计](./AGENT_EVOLUTION.md)

---

## 目录

1. [方案定位与最小验证原则](#1-方案定位与最小验证原则)
2. [核心竞争力回顾：项目级经验积累的挑战](#2-核心竞争力回顾项目级经验积累的挑战)
3. [渐进式披露策略（Progressive Disclosure）](#3-渐进式披露策略progressive-disclosure)
4. [LangGraph 方案详细设计](#4-langgraph-方案详细设计)
5. [Google ADK 方案详细设计](#5-google-adk-方案详细设计)
6. [两方案共用的 ExperienceLibrary 集成层](#6-两方案共用的-experiencelibrary-集成层)
7. [方案对比与选型建议](#7-方案对比与选型建议)
8. [MVP 最小验证计划](#8-mvp-最小验证计划)
9. [参考资料](#9-参考资料)

---

## 1. 方案定位与最小验证原则

### 1.1 设计约束

本文档遵循 [ANTS_LITE.md](./ANTS_LITE.md) 的精简原则，
在 [AGENT_LANDSCAPE_2025_2026.md §9](./AGENT_LANDSCAPE_2025_2026.md#9-结论是否需要独立开发) 结论基础上展开：

> **不从零构建基础设施，最大化复用现有成熟框架。核心开发量聚焦在经验库、代码库索引和阶段边界 HITL 三个模块。**

### 1.2 最小验证原则（MVP 判断标准）

一个合格的 MVP 只需证明以下三件事：

| 验证点 | 判断标准 |
|--------|---------|
| **经验能被积累** | 第 1 次会话完成后，`.ants/experience/` 目录有新的 JSONL 条目 |
| **经验能被复用** | 第 2 次处理同类任务时，Agent 的 prompt 中包含来自经验库的相关条目 |
| **注意力不被稀释** | 每次注入的经验总 token 数 ≤ 2000；模型在测试任务上的输出质量与无经验时相当或更好 |

不需要在 MVP 阶段验证：向量检索、跨项目迁移、Web UI、A2A 协议。

---

## 2. 核心竞争力回顾：项目级经验积累的挑战

### 2.1 为什么经验加载会成为弊端

ANTS 的核心差异化是**项目级经验积累**。但"把经验注入 context"存在一个真实风险：

```
风险一：Token 消耗过大
  若不加限制地注入，成熟项目的经验库可能有 200+ 条，
  按每条 150 tokens 计算 = 30,000+ tokens 仅用于经验，
  占 GPT-4o 128K 窗口的 23%，严重挤压代码和指令空间。

风险二：注意力稀释（"Lost in the Middle" 效应）
  学术研究（Liu et al. 2023, "Lost in the Middle"）表明：
  当关键信息位于长上下文的"中间"位置时，LLM 对其的利用率显著下降。
  注入 20 条经验但只有 2 条真正相关时，模型可能"忽视"这 2 条真正有价值的经验，
  反而被无关条目干扰，导致输出质量不升反降。

风险三：经验与指令的优先级混乱
  如果经验条目与当前任务指令在表述上有冲突（例如：
  经验说"用 Poetry"，但当前任务是迁移到 pip），
  大量经验会让模型难以判断"当前任务意图"优先于"历史经验"。
```

**结论：经验不是越多越好，而是越精准越好。关键不在于"加载多少"，而在于"何时加载什么"。**

### 2.2 是否会成为弊端？

| 场景 | 有无弊端 | 条件 |
|------|---------|------|
| 精准检索，注入 3~5 条高度相关经验 | ✅ 显著收益 | 检索质量高、经验质量高 |
| 注入 15+ 条经验，大多数不相关 | ❌ 弊大于利 | 检索质量低或无过滤 |
| 经验与当前任务指令有矛盾 | ❌ 有害 | 经验库质量管理不足 |
| 经验放在 context 末尾 | ⚠️ 效果减弱 | 应放在 context 前部（研究支持）|

这说明经验加载机制的设计质量，直接决定了它是竞争力还是负担。
**渐进式披露（Progressive Disclosure）** 是解决这一矛盾的核心策略。

---

## 3. 渐进式披露策略（Progressive Disclosure）

### 3.1 核心思想

渐进式披露：**不在任务开始时一次性注入所有可能相关的经验，而是按照任务执行的节奏、随着信息需求逐步浮现，分批次、分层级、按需注入最相关的经验片段。**

类比：好的技术文档不会在首页展示所有细节，而是先给摘要，再在需要的地方提供细节链接。

### 3.2 三级加载模型（与 AGENT_EVOLUTION.md §7 一致，本节聚焦在框架集成）

```
┌─────────────────────────────────────────────────────────────────────┐
│                       经验加载时间轴                                   │
│                                                                       │
│  会话启动       任务开始          任务执行中         任务完成           │
│     │              │                  │                │              │
│     ▼              ▼                  ▼                ▼              │
│  [Level 0]      [Level 1]          [Level 2]       [reflect()]       │
│  元信息注入     固定基础经验        按需动态检索      写回新经验         │
│  ~100 tokens   ~750 tokens         ~450 tokens      (异步)            │
│                                                                       │
│  ─────────────────────────────────── ◄ 总上限 ≤ 2000 tokens ──────── │
└─────────────────────────────────────────────────────────────────────┘
```

**Level 0 — 会话元信息（~100 tokens，写入 System Prompt 固定部分）**

```
此项目：{project_name}，技术栈：{tech_stack}
经验库状态：已有 {n} 条项目经验可检索。
执行任务前请先查阅相关经验（调用 query_experience 工具），再开始操作。
```

作用：让模型知道"有经验库存在"且"如何查询"，不占用大量 token。

**Level 1 — 任务开始时固定注入（~750 tokens，每次任务必注入）**

```python
# 构建依据：agent 角色 + 当前任务描述
experiences_l1 = await library.query(
    problem=task.description,
    agent_id=agent.id,
    categories=agent.preferred_categories,   # 例如 Coder 优先 project_convention
    top_k=5,
    min_score=0.5
)
```

选择标准：与当前 **任务描述** 最相关的 top-5 经验，分数 ≥ 0.5。  
注入位置：**Agent 的 System Prompt 结尾**（研究表明首尾位置注意力最强）。

**Level 2 — 执行中按需动态检索（~450 tokens，Agent 主动调用）**

Agent 在执行中遇到不确定的情况时，可主动调用工具：

```python
# 工具定义（MCP 或框架原生工具）
@tool
async def query_experience(problem_description: str) -> str:
    """
    检索项目经验库，查找与当前问题相关的已知解法。
    当遇到错误、不确定工具用法、或不确定项目约定时调用。
    返回最多 3 条最相关经验（已格式化为文本）。
    """
    results = await library.query(
        problem=problem_description,
        agent_id=current_agent_id,
        top_k=3,
        min_score=0.4
    )
    return format_experiences(results)  # ≤ 450 tokens
```

关键：这是 **Agent 主动拉取**，而非系统被动推送。Agent 只在真正需要时才调用，
避免无关经验污染上下文。

**Level 3 — 错误触发紧急检索（~750 tokens，错误时自动触发）**

```python
# Orchestrator 层：当 Agent 调用工具失败或 LLM 输出包含错误标志时触发
if task_result.has_error:
    error_experiences = await library.query(
        problem=task_result.error_message,
        agent_id=agent.id,
        categories=["environment", "debug_pattern"],
        top_k=5,
        min_score=0.4
    )
    # 将检索结果注入下一轮 Agent 调用的 context
    await agent.retry_with_context(error_experiences)
```

### 3.3 Token 预算管理

```python
class ExperienceBudgetManager:
    """
    管理单次任务的经验 token 总预算，防止溢出。
    """
    MAX_BUDGET = 2000  # tokens

    def __init__(self):
        self._used = 0
        self._entries: list[RetrievedExperience] = []

    def try_add(self, experiences: list[RetrievedExperience]) -> list[RetrievedExperience]:
        """尝试加入新经验，超过预算时优先保留 score 更高的。"""
        accepted = []
        for exp in sorted(experiences, key=lambda e: e.score, reverse=True):
            cost = estimate_tokens(compress_entry(exp.entry))
            if self._used + cost <= self.MAX_BUDGET:
                self._used += cost
                self._entries.append(exp)
                accepted.append(exp)
        return accepted

    def to_prompt_section(self) -> str:
        """格式化为可注入 prompt 的文本块。"""
        if not self._entries:
            return ""
        lines = ["【项目历史经验（按相关度排序）】"]
        for exp in self._entries:
            lines.append(compress_entry(exp.entry))
        return "\n".join(lines)
```

### 3.4 经验的位置策略

基于"Lost in the Middle"研究结论，经验块应放在 **System Prompt 的靠近开头或靠近结尾** 的位置，
避免被长段代码上下文"夹在中间"：

```
推荐的 Agent Prompt 结构：

[System Prompt]
  ① 角色定义（必须，~200 tokens）
  ② 项目元信息（Level 0，~100 tokens）
  ③ 【项目历史经验】（Level 1，~750 tokens）← 紧跟角色定义之后
  ④ 任务指令（必须）
  ⑤ 代码上下文（代码片段、文件内容等）
  ⑥ 任务执行中动态追加的经验（Level 2/3）← 放在末尾
```

---

## 4. LangGraph 方案详细设计

### 4.1 方案总览

**选择 LangGraph 的理由**（复用已有能力）：
- 状态检查点（Checkpointing）：直接对应 ANTS 的 `.ants/sessions/` 持久化需求
- 原生 interrupt()：LangGraph 1.0 的 interrupt 机制精确满足"阶段边界暂停审批"需求
- SQLiteCheckpointer：本地文件持久化，不依赖 Redis，符合 ANTS Lite 轻量原则
- 与 LangChain 工具生态（RAG、文件操作、代码执行）直接复用

### 4.2 状态定义

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph import add_messages

class TaskItem(TypedDict):
    id: str
    title: str
    description: str
    assigned_agent: str
    phase: int
    depends_on: list[str]
    status: Literal["pending", "in_progress", "completed", "needs_redo", "skipped"]
    output: dict | None

class ANTSState(TypedDict):
    # ── 会话核心 ──────────────────────────────────────────────────
    session_id: str
    goal: str
    project_path: str
    current_phase: int              # 当前执行阶段（1=规划, 2=执行, 3=验证）

    # ── 任务管理 ──────────────────────────────────────────────────
    tasks: list[TaskItem]           # Planner 生成，Orchestrator 更新
    current_task_id: str | None     # 当前正在执行的任务

    # ── 消息/记忆 ─────────────────────────────────────────────────
    messages: Annotated[list, add_messages]  # 会话消息流（支持流式输出）
    session_memory: str             # 步骤摘要（各 Agent 追加）

    # ── 经验上下文（渐进式披露状态）──────────────────────────────
    experience_budget_used: int     # 已使用的经验 token 数
    injected_experience_ids: list[str]  # 本次已注入的经验 ID（避免重复）

    # ── 人工审批 ──────────────────────────────────────────────────
    human_decision: str | None      # "approve" | "redo" | "edit" | "abort"
    human_note: str | None

    # ── 流程控制 ──────────────────────────────────────────────────
    phase_status: Literal["running", "waiting_human", "completed"]
    workflow_status: Literal["running", "paused", "completed", "aborted"]
```

### 4.3 图结构设计

```
                    ┌─────────────────────────────┐
                    │         START               │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │      setup_session          │  初始化会话、加载知识库
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │      planner_node           │  生成任务清单（Phase 1）
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
         ┌──────── │  phase_checkpoint_node       │ ─────────┐
         │          │  （Phase 1 完成，等待审批）   │          │
         │          └──────────────────────────────┘          │
         │                       │ interrupt()                 │
         │                       ▼                            │
         │          ┌─────────────────────────────┐          │
         │          │      HUMAN INPUT            │          │
         │          │   approve / redo / edit /   │          │
         │          │       abort                 │          │
         │          └──────────────┬──────────────┘          │
    redo │                         │ approve/edit             │ abort
         │                         ▼                          │
         │          ┌─────────────────────────────┐          │
         │          │    execution_phase_node     │          │
         │          │（并行执行 Phase 2 任务）      │          │
         │          │ asyncio.gather(coder×N)     │          │
         │          └──────────────┬──────────────┘          │
         │                         │                          │
         │                         ▼                          │
         │          ┌─────────────────────────────┐          │
         └──────── │  phase_checkpoint_node       │ ─────────┘
                    │  （Phase 2 完成，等待审批）   │
                    └──────────────┬──────────────┘
                                   │ approve
                                   ▼
                    ┌─────────────────────────────┐
                    │    verification_phase_node  │  Reviewer + Tester
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │  phase_checkpoint_node      │  Phase 3 审批
                    └──────────────┬──────────────┘
                                   │ approve
                                   ▼
                    ┌─────────────────────────────┐
                    │      finalize_session       │  写回经验、生成报告
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                                  END
```

### 4.4 核心节点实现

#### 4.4.1 setup_session 节点

```python
async def setup_session(state: ANTSState) -> ANTSState:
    """初始化会话：扫描代码库、预加载 Level 0 元信息。"""
    project_path = state["project_path"]

    # 1. 扫描代码库（复用 Tree-sitter 工具）
    index = await CodebaseIndexer(project_path).build_or_load()

    # 2. 写入会话元信息到 .ants/sessions/{session_id}/
    ctx = SharedContext(project_path, state["session_id"])
    ctx.init_session(state["goal"])

    # 3. 预热经验库（读取元数据，不加载全部条目）
    lib = get_experience_library(project_path)
    meta = await lib.get_meta()

    return {
        **state,
        "session_memory": f"[会话启动] 目标：{state['goal']}\n"
                          f"代码库：{index.file_count} 个文件\n"
                          f"经验库：已有 {meta.total_entries} 条经验\n",
        "experience_budget_used": 0,
        "injected_experience_ids": [],
    }
```

#### 4.4.2 planner_node 节点（含 Level 1 经验注入）

```python
async def planner_node(state: ANTSState) -> ANTSState:
    """Planner 执行：生成任务清单，注入 Level 1 经验。"""
    lib = get_experience_library(state["project_path"])

    # ── Level 1 经验注入 ──────────────────────────────────────
    budget = ExperienceBudgetManager()
    l1_experiences = await lib.query(
        problem=state["goal"],
        agent_id="planner",
        categories=["project_convention", "arch_pattern", "domain_knowledge"],
        top_k=5,
        min_score=0.5,
    )
    accepted = budget.try_add(l1_experiences)

    # ── 构建 Planner Prompt ───────────────────────────────────
    system_prompt = build_planner_system_prompt(
        project_meta=state["session_memory"],
        experience_section=budget.to_prompt_section(),  # 经验块放在前部
    )

    # ── 调用 LLM 生成任务清单 ─────────────────────────────────
    llm = get_llm(model="complex")   # Planner 用大模型
    tasks_json = await llm.invoke(
        [SystemMessage(content=system_prompt),
         HumanMessage(content=f"目标：{state['goal']}\n\n请生成任务清单（JSON 数组）")]
    )
    tasks = parse_tasks(tasks_json.content)

    # ── 记录经验使用 ──────────────────────────────────────────
    for exp in accepted:
        await lib.feedback(exp.entry.id, helpful=None)  # 标记"已被加载"

    return {
        **state,
        "tasks": tasks,
        "current_phase": 1,
        "phase_status": "completed",
        "experience_budget_used": budget._used,
        "injected_experience_ids": [e.entry.id for e in accepted],
        "session_memory": state["session_memory"] + f"\n[Phase 1] Planner 生成 {len(tasks)} 个任务",
    }
```

#### 4.4.3 phase_checkpoint_node 节点（HITL）

```python
from langgraph.types import interrupt

async def phase_checkpoint_node(state: ANTSState) -> ANTSState:
    """
    阶段边界检查点：暂停等待人工审批。
    使用 LangGraph 1.0 的 interrupt() 机制，精确挂起当前执行流。
    """
    phase = state["current_phase"]
    summary = build_phase_summary(state)

    # interrupt() 挂起图执行，将摘要返回给调用方，等待恢复时的 human_decision
    human_response = interrupt({
        "phase": phase,
        "summary": summary,
        "tasks": [t for t in state["tasks"] if t["phase"] == phase],
        "actions": ["approve", "redo", "edit", "abort"],
    })

    decision = human_response.get("action", "approve")
    note = human_response.get("note", "")

    if decision == "abort":
        return {**state, "workflow_status": "aborted", "human_decision": "abort"}

    if decision == "redo":
        # 重置本阶段所有任务为 pending
        updated_tasks = [
            {**t, "status": "pending", "output": None}
            if t["phase"] == phase else t
            for t in state["tasks"]
        ]
        return {**state, "tasks": updated_tasks, "human_decision": "redo"}

    if decision == "edit" and phase == 1:
        # 将人工编辑的任务清单写回状态
        edited_tasks = human_response.get("edited_tasks", state["tasks"])
        return {**state, "tasks": edited_tasks, "human_decision": "edit"}

    # approve
    return {**state, "human_decision": "approve", "human_note": note,
            "phase_status": "completed"}
```

#### 4.4.4 execution_phase_node 节点（并行 Coder）

```python
async def execution_phase_node(state: ANTSState) -> ANTSState:
    """并行执行 Phase 2 任务（多个 Coder）。"""
    pending_tasks = [t for t in state["tasks"]
                     if t["phase"] == 2 and t["status"] == "pending"]

    while pending_tasks:
        # 找出本轮所有就绪任务（依赖已全部完成）
        completed_ids = {t["id"] for t in state["tasks"] if t["status"] == "completed"}
        ready = [t for t in pending_tasks
                 if all(dep in completed_ids for dep in t["depends_on"])]

        if not ready:
            break  # 死锁保护

        # 并行执行就绪任务
        results = await asyncio.gather(*[
            run_coder_task(task, state) for task in ready
        ])

        # 更新任务状态
        result_map = {r["task_id"]: r for r in results}
        updated_tasks = []
        for t in state["tasks"]:
            if t["id"] in result_map:
                r = result_map[t["id"]]
                updated_tasks.append({
                    **t,
                    "status": "completed" if r["passed"] else "needs_redo",
                    "output": r["output"],
                })
            else:
                updated_tasks.append(t)

        state = {**state, "tasks": updated_tasks}
        pending_tasks = [t for t in state["tasks"]
                         if t["phase"] == 2 and t["status"] == "pending"]

    return {**state, "current_phase": 2, "phase_status": "completed"}


async def run_coder_task(task: TaskItem, state: ANTSState) -> dict:
    """单个 Coder 任务执行（包含 Level 1 + Level 2 经验注入）。"""
    lib = get_experience_library(state["project_path"])
    budget = ExperienceBudgetManager()

    # Level 1：任务级别经验
    l1 = await lib.query(task["description"], "coder", top_k=5, min_score=0.5)
    budget.try_add(l1)

    # 构建 Coder Agent（LangChain ReAct 结构，工具调用支持 Level 2 + 3 动态检索）
    coder_agent = build_coder_agent(
        tools=[
            read_file_tool,
            write_file_tool,
            run_shell_tool,
            query_experience_tool(lib, "coder", budget),  # Level 2/3 动态检索工具
        ],
        system_prompt=build_coder_prompt(
            task=task,
            session_memory=state["session_memory"],
            experience_section=budget.to_prompt_section(),
        )
    )

    result = await coder_agent.ainvoke({"task": task})

    # Supervisor 审核
    supervisor = Supervisor(get_llm(model="default"))
    verdict = await supervisor.check(task, result)

    # reflect：提炼经验（异步，不阻塞主流程）
    asyncio.create_task(reflect_and_save(task, result, lib))

    return {
        "task_id": task["id"],
        "passed": verdict.passed,
        "output": result,
    }
```

### 4.5 图注册与运行

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

def build_ants_graph():
    graph = StateGraph(ANTSState)

    # 注册节点
    graph.add_node("setup_session", setup_session)
    graph.add_node("planner", planner_node)
    graph.add_node("phase1_checkpoint", phase_checkpoint_node)
    graph.add_node("execution_phase", execution_phase_node)
    graph.add_node("phase2_checkpoint", phase_checkpoint_node)
    graph.add_node("verification_phase", verification_phase_node)
    graph.add_node("phase3_checkpoint", phase_checkpoint_node)
    graph.add_node("finalize", finalize_session_node)

    # 注册边
    graph.set_entry_point("setup_session")
    graph.add_edge("setup_session", "planner")
    graph.add_edge("planner", "phase1_checkpoint")

    # 条件边：Phase 1 审批结果路由
    graph.add_conditional_edges(
        "phase1_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "execution_phase",
            "redo": "planner",
            "abort": END,
        }
    )

    graph.add_edge("execution_phase", "phase2_checkpoint")
    graph.add_conditional_edges(
        "phase2_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "verification_phase",
            "redo": "execution_phase",
            "abort": END,
        }
    )

    graph.add_edge("verification_phase", "phase3_checkpoint")
    graph.add_conditional_edges(
        "phase3_checkpoint",
        route_after_checkpoint,
        {
            "proceed": "finalize",
            "redo": "verification_phase",
            "abort": END,
        }
    )

    graph.add_edge("finalize", END)

    # SQLite 检查点（本地文件，无需 Redis）
    checkpointer = SqliteSaver.from_conn_string(".ants/checkpoints.db")
    return graph.compile(checkpointer=checkpointer, interrupt_before=["phase1_checkpoint",
                                                                        "phase2_checkpoint",
                                                                        "phase3_checkpoint"])


def route_after_checkpoint(state: ANTSState) -> str:
    decision = state.get("human_decision")
    if decision == "abort":
        return "abort"
    if decision == "redo":
        return "redo"
    return "proceed"
```

### 4.6 CLI 入口（MVP 级）

```python
# ants/cli.py
import asyncio
from langgraph.types import Command

async def run_session(goal: str, project_path: str):
    graph = build_ants_graph()
    config = {"configurable": {"thread_id": generate_session_id()}}

    initial_state = {
        "session_id": config["configurable"]["thread_id"],
        "goal": goal,
        "project_path": project_path,
        "current_phase": 0,
        "tasks": [],
        "messages": [],
        "session_memory": "",
        "experience_budget_used": 0,
        "injected_experience_ids": [],
        "human_decision": None,
        "human_note": None,
        "phase_status": "running",
        "workflow_status": "running",
    }

    async for event in graph.astream(initial_state, config, stream_mode="updates"):
        # 处理 interrupt 暂停点
        if "__interrupt__" in event:
            interrupt_data = event["__interrupt__"][0].value
            print(f"\n⏸  Phase {interrupt_data['phase']} 完成")
            print(interrupt_data["summary"])
            print("\n操作：[Enter] 批准 | [r] 重做 | [e] 编辑任务 | [q] 终止")

            action = input("> ").strip() or "approve"
            action_map = {"": "approve", "r": "redo", "e": "edit", "q": "abort"}
            action = action_map.get(action, "approve")

            # 恢复图执行
            await graph.aupdate_state(config, {"human_decision": action}, as_node="__interrupt__")
            async for resume_event in graph.astream(Command(resume={"action": action}),
                                                     config, stream_mode="updates"):
                print_progress(resume_event)
        else:
            print_progress(event)
```

### 4.7 LangGraph 方案的目录结构

```
ants/
├── graph/
│   ├── state.py          # ANTSState TypedDict
│   ├── builder.py        # build_ants_graph()
│   └── nodes/
│       ├── setup.py      # setup_session
│       ├── planner.py    # planner_node
│       ├── execution.py  # execution_phase_node + run_coder_task
│       ├── verification.py
│       ├── checkpoint.py # phase_checkpoint_node
│       └── finalize.py
├── agents/
│   ├── base.py           # BaseAgent 接口
│   ├── planner.py
│   ├── coder.py
│   ├── reviewer.py
│   └── tester.py
├── experience/           # 共用，见第 6 节
│   ├── library.py
│   ├── reflect.py
│   ├── entry.py
│   └── retriever.py
├── shared_context/
│   └── context.py        # SharedContext 类
└── cli.py
```

---

## 5. Google ADK 方案详细设计

### 5.1 方案总览

**选择 Google ADK 的理由**（复用已有能力）：
- 原生层次化多 Agent 编排：Root Agent → Sub-Agents，天然映射 ANTS 的 Orchestrator → Planner/Coder/Reviewer/Tester
- 原生 A2A 支持：未来扩展跨框架协作时直接受益
- 原生 MCP 客户端：直接复用 2000+ 现有 MCP Server 生态
- Session/Memory 管理：ADK 内置跨轮次记忆，简化 SharedContext 实现
- 多语言支持：Python + Java，适合未来企业级扩展

### 5.2 Agent 层次结构

```
                    ┌──────────────────────────────┐
                    │     OrchestratorAgent        │  Root Agent
                    │   （控制阶段流转 + HITL）      │
                    └──────────┬───────────────────┘
                               │ delegates to
              ┌────────────────┼─────────────────────┐
              │                │                     │
              ▼                ▼                     ▼
   ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ PlannerAgent │  │   CoderAgentPool │  │  VerifyAgentPool │
   │              │  │  （并行多实例）    │  │                  │
   │  顺序执行     │  │  CoderAgent × N  │  │  ReviewerAgent   │
   └──────────────┘  │  （asyncio并发）  │  │  TesterAgent     │
                     └──────────────────┘  └──────────────────┘
```

### 5.3 OrchestratorAgent（Root Agent）

```python
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.events import Event, EventActions

class OrchestratorAgent(LlmAgent):
    """
    ANTS 主编排 Agent。管理阶段流转、触发子 Agent、执行 HITL 检查点。
    """

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.lib = get_experience_library(project_path)
        self.ctx = SharedContext(project_path)

        super().__init__(
            name="ants_orchestrator",
            model="gemini-2.0-flash",   # ADK 默认 Gemini；可通过 LiteLLM 切换为 GPT-4o
            instruction=self._build_instruction(),
            tools=[
                FunctionTool(self.get_phase_summary),
                FunctionTool(self.request_human_approval),  # HITL 工具
                FunctionTool(self.mark_phase_complete),
            ],
            sub_agents=[
                PlannerAgent(project_path),
                CoderAgentPool(project_path),
                VerifyAgentPool(project_path),
            ],
        )

    def _build_instruction(self) -> str:
        return """
你是 ANTS 多 Agent 编排器，负责协调多个专业 Agent 完成编码任务。

工作流程：
1. 委派 PlannerAgent 生成任务清单（Phase 1）
2. 调用 request_human_approval(phase=1) 等待人工审批
3. 委派 CoderAgentPool 并行执行编码任务（Phase 2）
4. 调用 request_human_approval(phase=2) 等待人工审批
5. 委派 VerifyAgentPool 执行代码审查和测试（Phase 3）
6. 调用 request_human_approval(phase=3) 等待最终审批

规则：
- 每个阶段完成后必须调用 request_human_approval，不能跳过
- 人工返回 "redo" 时重新执行本阶段
- 人工返回 "abort" 时立即终止
"""
```

### 5.4 PlannerAgent

```python
class PlannerAgent(LlmAgent):
    """生成任务清单，注入项目级经验（Level 1）。"""

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.lib = get_experience_library(project_path)

        # 经验工具：ADK 中以 FunctionTool 形式注入
        experience_tool = FunctionTool(
            self._query_experience,
            description="查询项目历史经验，解决规划中的疑问。"
        )

        super().__init__(
            name="planner",
            model="gemini-2.0-pro",
            instruction=self._build_instruction(),
            tools=[
                experience_tool,
                FunctionTool(self._read_codebase_index),
                FunctionTool(self._write_task_plan),
            ],
        )

    async def before_invoke(self, ctx: InvocationContext) -> None:
        """ADK 生命周期钩子：在 Agent 调用 LLM 之前注入 Level 1 经验。"""
        goal = ctx.session.state.get("goal", "")

        budget = ExperienceBudgetManager()
        l1_exps = await self.lib.query(
            problem=goal,
            agent_id="planner",
            categories=["project_convention", "arch_pattern"],
            top_k=5,
            min_score=0.5,
        )
        budget.try_add(l1_exps)

        # 将经验块写入 ADK Session State（供本次 LLM 调用读取）
        ctx.session.state["planner_experience_section"] = budget.to_prompt_section()
        ctx.session.state["experience_budget_used"] = budget._used

    def _build_instruction(self) -> str:
        return """
你是 ANTS 任务规划 Agent。

任务：根据用户目标，分析代码库，生成分阶段的任务清单（JSON 格式）。

规则：
- 每个任务必须指定 phase（2=执行, 3=验证）、assigned_agent、depends_on
- 执行阶段的独立任务设置相同 phase，Orchestrator 会并行执行
- 如有历史经验可参考，优先遵循项目约定

项目历史经验：
{planner_experience_section}
"""
```

### 5.5 CoderAgentPool（并行 Coder）

ADK 原生支持并行执行（`ParallelAgent`），可直接复用：

```python
from google.adk.agents import ParallelAgent, LlmAgent

class CoderAgentPool:
    """
    动态创建 N 个 CoderAgent 实例并行执行任务。
    ADK ParallelAgent 实现并发，每个 Coder 独立处理一个任务。
    """

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.lib = get_experience_library(project_path)

    async def execute_tasks(self, tasks: list[TaskItem],
                            session: Session) -> list[dict]:
        """
        按依赖图批量并行执行任务。
        依赖已满足的任务一批并行，等待完成后继续下一批。
        """
        completed_ids = set()
        results = []

        while True:
            ready = [t for t in tasks
                     if t["status"] == "pending"
                     and all(dep in completed_ids for dep in t["depends_on"])]
            if not ready:
                break

            # 为本批次任务各创建一个 CoderAgent 实例
            coder_agents = [
                CoderAgent(
                    task=task,
                    project_path=self.project_path,
                    lib=self.lib,
                    agent_id=f"coder_{task['id']}",
                )
                for task in ready
            ]

            # ADK ParallelAgent 并行执行
            parallel = ParallelAgent(
                name=f"coder_pool_batch_{len(completed_ids)}",
                sub_agents=coder_agents,
            )
            batch_results = await parallel.run_async(session)

            for result in batch_results:
                results.append(result)
                if result["passed"]:
                    completed_ids.add(result["task_id"])

        return results


class CoderAgent(LlmAgent):
    """单个 Coder Agent：执行一个编码任务，集成 Level 1/2/3 经验注入。"""

    def __init__(self, task: TaskItem, project_path: str,
                 lib: ExperienceLibrary, agent_id: str):
        self.task = task
        self.lib = lib

        super().__init__(
            name=agent_id,
            model="gemini-2.0-flash",
            instruction=self._build_instruction(),
            tools=[
                FunctionTool(self._read_file),
                FunctionTool(self._write_file),
                FunctionTool(self._run_shell),
                # Level 2/3：动态经验检索工具
                FunctionTool(
                    self._query_experience,
                    description=(
                        "查询项目历史经验。当遇到错误、不确定工具用法、"
                        "或不确定项目约定时调用。"
                    )
                ),
            ],
        )

    async def _query_experience(self, problem_description: str) -> str:
        """Level 2/3 动态经验检索（由 Agent 主动调用）。"""
        results = await self.lib.query(
            problem=problem_description,
            agent_id=self.name,
            top_k=3,
            min_score=0.4,
        )
        if not results:
            return "（未找到相关历史经验）"
        lines = ["相关历史经验："]
        for r in results:
            lines.append(f"  • {compress_entry(r.entry)}  (相关度: {r.score:.2f})")
            # 标记为"被检索"，后续由 Agent 决定是否反馈 helpful
        return "\n".join(lines)

    async def after_invoke(self, ctx: InvocationContext, result: dict) -> None:
        """ADK 生命周期钩子：任务完成后触发 reflect()。"""
        asyncio.create_task(
            reflect_and_save(self.task, result, self.lib)
        )
```

### 5.6 HITL 实现（ADK 方式）

ADK 通过 **自定义 Event + 外部等待** 实现 HITL，与 LangGraph 的 interrupt() 逻辑等价：

```python
from google.adk.events import Event

class HumanApprovalTool:
    """
    ADK HITL 工具：挂起 Agent 执行，等待人工输入。
    实现原理：OrchestratorAgent 调用此工具后，ADK Runner 返回 LongRunningFunctionCall 事件；
    前端或 CLI 接收到事件后显示审批界面；人工提交后调用 resume()。
    """

    async def request_approval(self, phase: int, summary: str) -> dict:
        """
        此函数会触发 ADK 的 long-running 模式，实质上挂起 Agent 等待外部输入。
        返回值由外部（CLI/Web）在 resume() 时注入。
        """
        # ADK 的 long-running tool 机制：返回 pending 状态，等待外部恢复
        return {
            "status": "pending",
            "phase": phase,
            "summary": summary,
            "message": f"Phase {phase} 完成，请审批后继续",
        }


# CLI 端处理 HITL
async def run_with_hitl(runner: Runner, session: Session, goal: str):
    async for event in runner.run_async(session=session, message=goal):
        if event.is_long_running_tool_call("request_approval"):
            # 显示审批界面
            approval_data = event.tool_call_args
            print(f"\n⏸  Phase {approval_data['phase']} 完成")
            print(approval_data["summary"])
            print("\n操作：[Enter] 批准 | [r] 重做 | [q] 终止")

            action = input("> ").strip() or "approve"
            action_map = {"": "approve", "r": "redo", "q": "abort"}
            action = action_map.get(action, "approve")

            # 恢复 Agent 执行，注入人工决策
            await runner.resume(
                session=session,
                tool_call_id=event.tool_call_id,
                result={"action": action, "note": ""},
            )
        else:
            print_event(event)
```

### 5.7 ADK 方案的 Session State 管理

ADK 内置的 `Session.state` 充当跨轮次的共享状态，直接对应 ANTS 的 SharedContext：

```python
# ADK Session State 的键名约定（对应 ANTSState）
SESSION_KEYS = {
    "goal":               "ants.goal",
    "project_path":       "ants.project_path",
    "tasks":              "ants.tasks",
    "current_phase":      "ants.current_phase",
    "session_memory":     "ants.session_memory",
    "experience_budget":  "ants.experience_budget_used",
}

# 持久化：ADK 默认使用内存 Session，切换为文件持久化：
from google.adk.sessions import DatabaseSessionService
session_service = DatabaseSessionService(db_url="sqlite:///.ants/sessions.db")
runner = Runner(agent=orchestrator, session_service=session_service)
```

### 5.8 ADK 方案的目录结构

```
ants/
├── adk_agents/
│   ├── orchestrator.py    # OrchestratorAgent
│   ├── planner.py         # PlannerAgent
│   ├── coder_pool.py      # CoderAgentPool + CoderAgent
│   ├── verify_pool.py     # VerifyAgentPool（ReviewerAgent + TesterAgent）
│   └── hitl_tool.py       # HumanApprovalTool
├── experience/            # 共用，见第 6 节
│   ├── library.py
│   ├── reflect.py
│   ├── entry.py
│   └── retriever.py
├── shared_context/
│   └── context.py
└── cli.py
```

---

## 6. 两方案共用的 ExperienceLibrary 集成层

**ExperienceLibrary 是 ANTS 的核心差异化能力，与编排框架完全解耦。**  
LangGraph 方案和 ADK 方案使用同一套 ExperienceLibrary 实现，接口见 [AGENT_EVOLUTION.md §5.2](./AGENT_EVOLUTION.md#52-experiencelibrary-接口)。

### 6.1 与框架的集成点

| 集成点 | LangGraph 方式 | ADK 方式 |
|--------|--------------|---------|
| **Level 1 注入** | 在节点函数中调用 `library.query()`，将结果写入 State | 在 `before_invoke()` 钩子中调用，写入 `session.state` |
| **Level 2/3 动态检索** | 作为 LangChain `@tool` 注入 Agent | 作为 ADK `FunctionTool` 注入 Agent |
| **reflect() 写回** | `asyncio.create_task()` 异步调用 | `after_invoke()` 钩子中异步调用 |
| **预算管理** | `ExperienceBudgetManager` 在节点内实例化 | `ExperienceBudgetManager` 在 `before_invoke()` 内实例化 |

### 6.2 experience 工具的一致性

两方案中的动态检索工具的文档字符串（供 LLM 理解）保持一致：

```
查询项目历史经验库。

当遇到以下情况时主动调用：
1. 遇到错误或异常，希望知道项目中是否有已知解法
2. 不确定某个工具/命令在这个项目中的正确用法
3. 不确定这个项目的编码规范（命名、格式、架构模式）
4. 遇到可能与项目环境相关的问题（Python 版本、依赖管理工具等）

参数：
  problem_description（str）：当前遇到的问题或疑问的自然语言描述

返回：最多 3 条最相关的项目历史经验，含具体解决方案。
```

---

## 7. 方案对比与选型建议

### 7.1 功能对比

| 维度 | LangGraph 方案 | Google ADK 方案 |
|------|--------------|---------------|
| **学习曲线** | ⭐⭐（图模型较陡） | ⭐⭐⭐（层次化 Agent 直观） |
| **HITL 机制** | ✅ interrupt() 原生支持，精确 | ✅ long-running tool，需适配 |
| **并行执行** | ✅ asyncio.gather()，手动控制 | ✅ ParallelAgent 原生支持 |
| **状态持久化** | ✅ SQLiteCheckpointer 开箱即用 | ✅ DatabaseSessionService（SQLite）|
| **可观测性** | ✅ LangSmith（需账号）| ✅ ADK Web UI（本地免费）|
| **错误恢复/时间旅行** | ✅ Checkpointing + 回溯任意历史 | ⚠️ 需手动实现 |
| **MCP 工具集成** | ✅ LangChain MCP 适配层 | ✅ 原生 MCP Client |
| **A2A 协议** | ⚠️ 适配中 | ✅ 原生支持 |
| **多语言支持** | ❌ 仅 Python | ✅ Python + Java |
| **本地调试 UI** | ⚠️ LangSmith 需网络 | ✅ `adk web` 本地 UI |
| **模型无关性** | ✅ LiteLLM 支持多模型 | ✅ LiteLLM 支持多模型 |
| **社区活跃度** | ⭐⭐⭐⭐（25k+ Stars，生产案例多）| ⭐⭐⭐（快速增长，发布于 2025 年 4 月，尚在积累生产案例）|

### 7.2 与 ANTS 特定需求的匹配度

| ANTS 需求 | LangGraph | ADK |
|---------|-----------|-----|
| 阶段边界 HITL（"Phase 完成后审批"模型）| ✅ interrupt() 精确契合 | 🟡 需额外适配 |
| 并行 Coder 执行 | 🟡 asyncio.gather() 手动实现 | ✅ ParallelAgent 原生 |
| 状态回溯（重做阶段）| ✅ 时间旅行直接支持 | 🟡 需手动 rollback |
| 代码库索引集成 | ✅ LangChain 工具链 | ✅ MCP Server |
| 经验库集成 | ✅ 节点 + Tool | ✅ FunctionTool + 钩子 |
| 轻量部署（SQLite）| ✅ SqliteSaver | ✅ DatabaseSessionService |

### 7.3 推荐选型

**MVP 首选：LangGraph**

原因：
1. **阶段边界 HITL 开箱即用**：interrupt() 机制与"阶段完成后审批"范式完美匹配，ADK 需要额外封装。
2. **时间旅行回溯**：LangGraph 的 Checkpointing 支持"重做阶段"（回滚到上一个检查点重新执行），ADK 需手动实现。
3. **生产案例更成熟**：Klarna、GitLab 等公司已验证，减少未知风险。
4. **调试方便**：LangGraph Studio（本地版）提供可视化图调试，ADK Web UI 更依赖 Gemini 生态。

**中期建议：ADK 作为备选或并行探索**

原因：
1. ADK 的 ParallelAgent 和层次化 Agent 在并行编码场景表达更自然。
2. A2A 原生支持是未来跨框架扩展的基础。
3. 多语言支持对企业级扩展有价值。

**结论**：先用 LangGraph 跑通 MVP，同时保持 ExperienceLibrary 与框架解耦，以便未来迁移 ADK。

---

## 8. MVP 最小验证计划

### 8.1 MVP 范围（最小可验证集）

**目标**：用 LangGraph 方案，在 2 周内跑通以下验证场景，证明"经验积累"的核心价值。

| 模块 | MVP 范围 | 排除范围 |
|------|---------|--------|
| 编排 | LangGraph 图（3 节点：planner → phase1_checkpoint → coder） | Phase 3 验证阶段（暂缓）|
| Agent | Planner + 1 个 Coder（不并行） | Reviewer、Tester |
| 经验库 | BM25 检索（rank-bm25 库） | 向量检索 |
| 持久化 | SQLiteCheckpointer + JSONL 文件 | Redis、向量数据库 |
| HITL | Phase 1 后人工审批（CLI 交互） | Phase 3 审批、Web UI |
| 代码库索引 | 简单文件列表 + BM25 内容搜索 | Tree-sitter 符号索引 |

### 8.2 验证脚本（1 周交付）

```python
# tests/mvp_validation.py
"""
MVP 验证脚本：证明经验积累和复用的完整闭环。
运行两次相同类型的任务，第二次应看到经验被检索并注入。
"""

async def test_experience_accumulation():
    """验证点 1：经验能被积累。"""
    project_path = "/tmp/test_project"
    setup_test_project(project_path)  # 创建一个小型 Python 项目

    graph = build_ants_graph()
    config = {"configurable": {"thread_id": "test_session_001"}}

    # 第一次运行（不含历史经验）
    result1 = await run_session_auto_approve(
        graph, config,
        goal="实现一个读取 CSV 文件的函数",
        project_path=project_path,
    )

    lib = get_experience_library(project_path)
    entries = await lib.list_all()

    assert len(entries) > 0, "第一次运行后经验库应有新条目"
    print(f"✅ 验证点 1 通过：经验库新增 {len(entries)} 条经验")


async def test_experience_reuse():
    """验证点 2：经验能被复用（第二次任务注入了相关经验）。"""
    project_path = "/tmp/test_project"  # 复用上一步的项目

    # 第二次运行同类任务
    captured_prompts = []

    async def prompt_capture_hook(prompt: str):
        captured_prompts.append(prompt)

    result2 = await run_session_auto_approve(
        graph, config,
        goal="实现一个读取 JSON 文件的函数",  # 类似任务
        project_path=project_path,
        prompt_hook=prompt_capture_hook,
    )

    # 检查第二次运行的 prompt 是否包含经验库内容
    combined_prompt = "\n".join(captured_prompts)
    assert "项目历史经验" in combined_prompt, "第二次运行的 prompt 中应包含经验注入"
    print(f"✅ 验证点 2 通过：第二次任务 prompt 包含历史经验")


async def test_attention_budget():
    """验证点 3：经验注入不超过 token 预算。"""
    # 预填充大量经验（模拟成熟项目）
    project_path = "/tmp/large_exp_project"
    lib = get_experience_library(project_path)
    for i in range(50):  # 50 条经验
        await lib.add(make_mock_experience(i))

    budget = ExperienceBudgetManager()
    all_exps = await lib.query("读取文件", "coder", top_k=50)
    budget.try_add(all_exps)

    assert budget._used <= ExperienceBudgetManager.MAX_BUDGET, \
        f"经验 token 超预算：{budget._used} > {ExperienceBudgetManager.MAX_BUDGET}"
    print(f"✅ 验证点 3 通过：经验 token 用量 {budget._used} ≤ {ExperienceBudgetManager.MAX_BUDGET}")
```

### 8.3 MVP 交付物清单

| 文件 | 说明 | 估计工时 |
|------|------|---------|
| `ants/experience/entry.py` | ExperienceEntry dataclass | 0.5 天 |
| `ants/experience/library.py` | ExperienceLibrary（BM25 版）| 1.5 天 |
| `ants/experience/reflect.py` | reflect() + build_reflection_input() | 1 天 |
| `ants/graph/state.py` | ANTSState TypedDict | 0.5 天 |
| `ants/graph/nodes/planner.py` | planner_node（含 Level 1 注入）| 1 天 |
| `ants/graph/nodes/execution.py` | run_coder_task（含 Level 2 工具）| 1 天 |
| `ants/graph/nodes/checkpoint.py` | phase_checkpoint_node（interrupt）| 0.5 天 |
| `ants/graph/builder.py` | build_ants_graph() | 0.5 天 |
| `ants/cli.py` | CLI 入口（含 HITL 交互）| 0.5 天 |
| `tests/mvp_validation.py` | MVP 验证脚本 | 0.5 天 |
| **合计** | | **约 7.5 天** |

### 8.4 里程碑

```
Week 1（Day 1-5）：
  Day 1-2: ExperienceLibrary 实现（BM25 + 写入 + reflect）
  Day 3-4: LangGraph 图骨架（状态 + 节点 + 检查点 + CLI）
  Day 5:   集成：planner_node + Level 1 经验注入

Week 2（Day 6-10）：
  Day 6-7: Coder 节点 + Level 2 工具 + reflect 调用
  Day 8:   端到端测试（场景 A：新项目）
  Day 9:   验证脚本跑通，修复 Bug
  Day 10:  文档整理，MVP Review
```

---

## 9. 参考资料

| # | 来源 | 说明 |
|---|------|------|
| [ref-1] | Liu et al. (2023), "Lost in the Middle: How Language Models Use Long Contexts" | Lost in the Middle 注意力研究 |
| [ref-2] | LangGraph interrupt() 文档 | https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/ |
| [ref-3] | LangGraph SqliteSaver 文档 | https://langchain-ai.github.io/langgraph/reference/checkpoints/#langgraph.checkpoint.sqlite.SqliteSaver |
| [ref-4] | Google ADK ParallelAgent 文档 | https://google.github.io/adk-docs/agents/workflow-agents/parallel-agents/ |
| [ref-5] | Google ADK Session/Memory 文档 | https://google.github.io/adk-docs/sessions/memory/ |
| [ref-6] | Google ADK Long-running Tools | https://google.github.io/adk-docs/tools/long-running-tools/ |
| [ref-7] | rank-bm25 Python 库 | https://github.com/dorianbrown/rank_bm25 |
| [ref-8] | ANTS 精简落地方案 | [ANTS_LITE.md](./ANTS_LITE.md) |
| [ref-9] | ANTS 经验进化系统 | [AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md) |
| [ref-10] | Agent 协作平台洞察报告 | [AGENT_LANDSCAPE_2025_2026.md](./AGENT_LANDSCAPE_2025_2026.md) |

---

*文档版本 v1.0，与 ANTS_LITE.md v0.2、AGENT_EVOLUTION.md v1.0 配套。如有修改建议请提交 Issue 或 PR。*
