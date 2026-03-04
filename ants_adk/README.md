# ANTS — Google ADK 实现

基于 [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) 的 ANTS 多 Agent 编码助手。

## 目录结构

```
ants_adk/
├── adk_agents/
│   ├── orchestrator.py    # OrchestratorAgent（Root Agent，管理阶段流转 + HITL）
│   ├── planner.py         # PlannerAgent（生成任务清单，含 Level 1 经验注入）
│   ├── coder_pool.py      # CoderAgentPool + CoderAgent（并行编码）
│   ├── verify_pool.py     # VerifyAgentPool（ReviewerAgent + TesterAgent）
│   └── hitl_tool.py       # HumanApprovalTool（长运行工具 HITL 模式）
├── experience/            # 与 ants_langgraph 共用相同接口
│   ├── entry.py
│   ├── library.py
│   ├── retriever.py
│   ├── reflect.py
│   └── budget.py
├── shared_context/
│   └── context.py
├── cli.py                 # CLI 入口
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
  ├── PlannerAgent         → Phase 1：生成任务清单
  ├── CoderAgentPool       → Phase 2：并行执行编码任务
  │   ├── CoderAgent × N
  └── VerifyAgentPool      → Phase 3：代码审查 + 测试
      ├── ReviewerAgent
      └── TesterAgent
```

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

**推荐**：先用 `ants_langgraph` 验证 MVP，成熟后迁移到 `ants_adk`。

## 设计文档

详见根目录的 [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)。
