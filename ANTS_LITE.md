# ANTS Lite — 精简落地方案

> **版本**：v0.2  
> **日期**：2026-03-02  
> **定位**：可落地的精简版，不追求"大而全"，先跑通核心价值

---

## 目录

1. [为什么要精简](#1-为什么要精简)
2. [两个核心目标](#2-两个核心目标)
3. [精简架构与并行规则](#3-精简架构与并行规则)
4. [共享资料库详细结构](#4-共享资料库详细结构)
5. [Agent 注册与动态增减](#5-agent-注册与动态增减)
6. [人工干预机制（阶段边界模型）](#6-人工干预机制阶段边界模型)
7. [Agent 角色定义与自我进化](#7-agent-角色定义与自我进化)
8. [最小可验证设计（MVP）详细设计](#8-最小可验证设计mvp详细设计)
9. [与完整版的关系](#9-与完整版的关系)

---

## 1. 为什么要精简

完整版 ANTS（见 [DESIGN_REPORT.md](./DESIGN_REPORT.md)）覆盖了生产级多 Agent 系统的所有短板，
但**系统越复杂越难落地**。精简版原则：

| 精简原则 | 说明 |
|----------|------|
| **目标驱动** | 只保留支撑两个核心目标的最小模块集 |
| **依赖轻量** | 优先用本地文件/SQLite，而非 Redis/Kafka |
| **阶段边界审批** | 人工在阶段完成后审批，而非在 AI 执行中随意打断 |
| **渐进扩展** | 先跑通，再按需叠加生产级特性 |

---

## 2. 两个核心目标

### 目标一：开发新项目

```
人类 → 描述需求 → ANTS
  阶段1: Planner  → 生成任务清单
         ↓ ⏸ [人工审批：确认 / 修改任务]
  阶段2: Coder × N → 并行编写代码模块
         ↓ ⏸ [人工审批：浏览 diff / 可终止]
  阶段3: Reviewer + Tester → 质检
         ↓ ⏸ [人工审批：接受交付 / 要求重做]
       → 交付代码
```

涉及的典型 Agent：
- **Planner**：将需求拆解为任务清单（含文件/模块级别）
- **Coder**：逐任务生成/修改代码
- **Reviewer**：检查代码质量，输出问题列表
- **Tester**：生成并执行测试用例，报告通过/失败

### 目标二：维护老项目

```
人类 → 描述问题/需求 → ANTS
  阶段1: Planner → 索引代码库，定位相关文件，生成修改方案
         ↓ ⏸ [人工审批：确认定位是否正确]
  阶段2: Coder → 生成最小变更 patch
         ↓ ⏸ [人工审批：浏览 diff]
  阶段3: Tester → 运行回归测试，验证无破坏
         ↓ ⏸ [人工审批：接受 / 拒绝]
       → 交付补丁
```

额外需要的能力：
- **代码库索引**：能快速定位相关文件和函数（不读全库）
- **变更最小化**：只改必要的代码，不引入无关变动
- **回归检测**：修改后自动运行已有测试，确认没有破坏

---

## 3. 精简架构与并行规则

相比完整版，砍掉 Kafka、Redis Cluster、K8s、Vault 等重量级依赖，
用最小栈把核心流程跑通：

```
┌──────────────────────────────────────────────────────────────────┐
│                        ANTS Lite                                  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  编排层（Orchestrator）                    │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │    │
│  │  │ 任务计划器   │  │ Supervisor   │  │  人工干预网关   │  │    │
│  │  │ (Task Plan) │  │ (质检 + 纠偏)│  │ (HIL Gateway)  │  │    │
│  │  └─────────────┘  └──────────────┘  └────────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                              │                                     │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    Agent 层                               │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │    │
│  │  │ Planner  │  │  Coder   │  │ Reviewer │  │ Tester │  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                              │                                     │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              共享资料层（Shared Context）                  │    │
│  │  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐  │    │
│  │  │ 代码库索引    │  │ 任务状态DB  │  │  会话记忆       │  │    │
│  │  │(Tree-sitter) │  │ (SQLite)    │  │ (本地文件/JSON) │  │    │
│  │  └──────────────┘  └─────────────┘  └────────────────┘  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                              │                                     │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              工具层（MCP Tools）                           │    │
│  │  read_file · write_file · run_tests · search_code        │    │
│  │  git_diff · git_log · shell_exec · web_search            │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

**关键简化点**：

| 完整版 | Lite 版 | 说明 |
|--------|---------|------|
| Redis Cluster | SQLite + JSON 文件 | 任务状态/会话记忆本地化 |
| Kafka/RabbitMQ | Python asyncio Queue | 单机内消息传递 |
| K8s + gVisor | Docker Compose（可选） | 运行环境轻量化 |
| 向量数据库（Qdrant） | 代码索引文件 + BM25 | 代码检索先用关键词搜索 |
| OpenTelemetry + Jaeger | 结构化日志（文件） | 先用日志代替全链路追踪 |

### 3.1 Agent 并行规则

**核心原则：无依赖的任务可以并行，有依赖的任务必须串行。**

Orchestrator 在每个调度周期找到所有"依赖已全部完成"的待执行任务，
批量并发启动，用 `asyncio.gather()` 等待本批次全部完成后再进入下一批次。

```
任务依赖图示例：

task_001 (分析代码库)
    │
    ├──► task_002 (实现模块 A)  ─┐
    │                            ├── 并行执行（互不依赖）
    └──► task_003 (实现模块 B)  ─┘
              │
              └──► task_004 (集成测试)  ← 必须等 002 和 003 全部完成
```

| 情形 | 是否并行 | 说明 |
|------|----------|------|
| 多个 Coder 写互不相关的模块/文件 | ✅ 可并行 | `depends_on` 列表无交集 |
| 多个 Reviewer 分别审查不同文件 | ✅ 可并行 | 读操作无冲突 |
| Coder 写代码 + Tester 同时测试同一文件 | ❌ 不可并行 | 写后才能测 |
| 同一文件有两个 Coder 修改 | ❌ 不可并行 | 写冲突 |
| Planner 规划 + Coder 执行 | ❌ 不可并行 | Coder 依赖 Planner 输出 |

**并发安全保证**：共享资料层的每个文件有明确的"唯一写入者"（见第 4 节），
并行 Agent 不会同时写入同一文件，因此无需加锁。

---

## 4. 共享资料库详细结构

多 Agent 协作的核心挑战：**每个 Agent 只看到自己的上下文，但需要基于共同的"世界观"工作。**

### 4.1 目录布局

所有共享资料集中在项目根目录下的 `.ants/` 文件夹，结构固定：

```
<project_root>/
└── .ants/
    ├── knowledge/                  # 【只读】领域知识，由人工维护
    │   ├── project_spec.md         # 项目背景、目标、约束说明
    │   ├── coding_style.md         # 编码规范（语言风格、命名约定等）
    │   ├── arch_decisions/         # 架构决策记录（ADR）
    │   │   └── 001-use-fastapi.md
    │   └── api_docs/               # 第三方 API 文档摘要（按需放入）
    │
    ├── project_state/              # 【读写】项目级持久状态，跨会话共享
    │   ├── codebase_index.json     # 代码库符号索引（首次建立，增量更新）
    │   └── known_issues.json       # 已知问题列表（可选）
    │
    ├── experience/                 # 【读写】Agent 经验库（详见 AGENT_EVOLUTION.md）
    │   ├── entries/                # 按类别分 JSONL 文件，追加写入
    │   ├── index/                  # BM25 + 向量检索索引
    │   └── meta.json
    │
    └── sessions/                   # 【读写】每次任务一个子目录
        └── session_<timestamp>/
            ├── goal.md             # 本次任务目标（人工填写，Agent 只读）
            ├── tasks.json          # 任务清单（Planner 生成，Orchestrator 更新状态）
            ├── session_memory.md   # 步骤摘要流水（各 Agent 追加，所有人可读）
            ├── human_log.md        # 人工审批记录（时间戳 + 意见）
            └── outputs/            # 各 Agent 的输出文件（唯一写入者见下表）
                ├── plan.json       # Planner 输出
                ├── code_diff.md    # Coder 输出
                ├── review.json     # Reviewer 输出
                └── test_result.json# Tester 输出
```

### 4.2 文件与写入者对应表

| 文件 | 唯一写入 Agent | 其他 Agent 权限 | 说明 |
|------|--------------|-----------------|------|
| `knowledge/**` | 人工 | 只读 | 项目启动前一次性准备，或随项目演进人工补充 |
| `project_state/codebase_index.json` | Planner | 只读 | 每次会话开始时 Planner 检查并增量更新 |
| `experience/**` | 所有 Agent（各自 reflect() 写入） | 只读 | 经验库，详见 [AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md) |
| `sessions/*/goal.md` | 人工 | 只读 | 本次任务唯一来源 |
| `sessions/*/tasks.json` | Planner（生成） + Orchestrator（更新状态） | 只读 | 所有 Agent 从这里获取自己的任务 |
| `sessions/*/session_memory.md` | 所有 Agent（追加本步摘要） | 追加 | 追加模式，不覆盖，保证历史完整 |
| `sessions/*/outputs/plan.json` | Planner | 只读 | — |
| `sessions/*/outputs/code_diff.md` | Coder | 只读 | — |
| `sessions/*/outputs/review.json` | Reviewer | 只读 | — |
| `sessions/*/outputs/test_result.json` | Tester | 只读 | — |

### 4.3 Agent 如何使用共享资料

每个 Agent 执行前接收的上下文 = 以下三部分的拼接，由 Orchestrator 组装后传入：

```
system_prompt（来自 Agent 角色定义，见第 7 节）
    +
知识包（knowledge/ 相关文件 + 经验库检索结果，≤ 2000 tokens，详见 AGENT_EVOLUTION.md §7）
    +
当前任务（tasks.json 中分配给本 Agent 的任务）
    +
会话记忆（session_memory.md，了解前序步骤的结果）
    +
必要的代码片段（由 codebase_index 检索，只取相关文件/函数，不传整个代码库）
```

### 4.4 代码库索引（老项目关键能力）

```python
# codebase_index.json 结构
{
  "built_at": "2026-03-02T10:00:00",
  "files": [
    {
      "path": "src/auth/login.py",
      "language": "python",
      "symbols": ["login_user", "validate_token", "LoginForm"],
      "summary": "用户登录逻辑，包含 JWT 验证",
      "line_count": 120,
      "last_modified": "2026-02-20",
      "imports": ["src.models.user", "src.utils.jwt"]
    }
  ],
  "dependency_graph": {
    "src/auth/login.py": ["src/models/user.py", "src/utils/jwt.py"]
  }
}
```

建立/更新索引的方式：
1. **Python AST**：纯标准库，解析 Python 文件符号（MVP 首选）
2. **Tree-sitter**：支持多语言，精度更高（后续升级）
3. **LLM 摘要**：对 AST 无法提取语义的文件（如配置文件），用 LLM 生成一行摘要并缓存

---

## 5. Agent 注册与动态增减

### 5.1 Agent 注册表

所有 Agent 的元数据统一存储在 `.ants/agents/registry.yaml`。
这是整个系统"有哪些 Agent 可用"的唯一权威来源。

```yaml
# .ants/agents/registry.yaml
agents:
  - id: planner
    role_file: roles/planner.yaml
    model: gpt-4o                  # 用大模型做规划
    enabled: true

  - id: coder
    role_file: roles/coder.yaml
    model: gpt-4o-mini
    enabled: true
    max_parallel: 4                # 最多同时启动 4 个 Coder 实例

  - id: reviewer
    role_file: roles/reviewer.yaml
    model: gpt-4o-mini
    enabled: true

  - id: tester
    role_file: roles/tester.yaml
    model: gpt-4o-mini
    enabled: false                 # MVP 阶段暂不启用

  - id: security_auditor           # 按需新增的专项 Agent
    role_file: roles/security_auditor.yaml
    model: gpt-4o
    enabled: false
```

### 5.2 动态新增 Agent

**何时需要新增**：任务规划时 Planner 发现当前注册的 Agent 角色不够用
（如项目新增了移动端需求，需要 iOS Coder）。

新增流程：
```
1. 人工在 registry.yaml 中新增条目，填写 role_file 路径
2. 在 .ants/agents/roles/ 下创建对应的角色定义文件（见第 7 节）
3. 重启 Orchestrator 或在阶段边界热重载（Orchestrator 在每个阶段开始时重新读取 registry）
4. Planner 在下次规划时即可将任务分配给新 Agent
```

### 5.3 动态减少 Agent

**何时需要减少**：某类任务在本项目中不存在（如纯前端项目不需要 DBA Agent）。

减少方式：
- 将 `registry.yaml` 中对应条目的 `enabled` 设为 `false`
- 无需删除角色文件，保留以备将来使用
- Orchestrator 会跳过 disabled 的 Agent；若 Planner 误分配到 disabled Agent，Orchestrator 报错并请求人工确认

### 5.4 Orchestrator 的 Agent 加载逻辑

```
会话开始
  │
  ▼
读取 registry.yaml → 只加载 enabled=true 的 Agent
  │
  ▼
每个阶段开始时检查 registry 变更（热重载）
  │
  ▼
Planner 只能将任务分配给当前已注册且 enabled 的 Agent
```

---

## 6. 人工干预机制（阶段边界模型）

**核心原则：人工在阶段与阶段之间介入，而不是在 AI 执行过程中随意打断。**

AI 执行过程中随意注入指令会导致：Agent 上下文不一致、任务状态混乱、输出难以追溯。
正确的做法是让 AI 把当前阶段走完，在明确的"检查点"交给人工审批。

### 6.1 阶段与检查点

一次完整任务被划分为若干**阶段（Phase）**，每个阶段结束后系统自动暂停等待人工审批：

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: 规划阶段                                                    │
│  Planner 分析代码库，生成任务清单                                      │
│                      ↓                                               │
│  ⏸ 检查点 A ── 人工审批 ──────────────────────────────────────────  │
│  展示：任务清单                                                        │
│  人工可以：✅ 确认继续 │ ✏️ 修改任务（增/删/改）│ 🛑 终止             │
└─────────────────────────────────────────────────────────────────────┘
          ↓ 确认后
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 2: 执行阶段                                                    │
│  Coder 并行执行所有编码任务（AI 全自主，不接受中途打断）                  │
│                      ↓                                               │
│  ⏸ 检查点 B ── 人工审批 ──────────────────────────────────────────  │
│  展示：所有文件 diff、修改摘要                                          │
│  人工可以：✅ 确认继续 │ 🔄 要求重做（附上原因）│ 🛑 终止             │
└─────────────────────────────────────────────────────────────────────┘
          ↓ 确认后
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 3: 验证阶段                                                    │
│  Reviewer 审查代码，Tester 运行测试（AI 全自主）                        │
│                      ↓                                               │
│  ⏸ 检查点 C ── 人工审批 ──────────────────────────────────────────  │
│  展示：审查报告、测试结果                                               │
│  人工可以：✅ 接受交付 │ 🔄 要求修复（退回 Phase 2）│ 🛑 终止         │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 人工在检查点可做的操作

| 操作 | 命令 | 含义 |
|------|------|------|
| 确认继续 | `approve` / Enter | 当前阶段结果满意，进入下一阶段 |
| 要求重做 | `redo <原因>` | 当前阶段输出不满意，AI 重新执行本阶段（携带原因） |
| 修改任务后继续 | `edit` 进入编辑器 | 仅在检查点 A 可用；直接编辑 tasks.json |
| 终止 | `abort` | 立即停止，保存当前会话状态，可稍后恢复 |

### 6.3 紧急停止（仅限异常）

如果 AI 执行过程中出现明显错误（如误删文件、死循环），人工可发送 `Ctrl+C`：
- Orchestrator 捕获中断信号
- **等待当前 Agent 的当前 LLM 调用完成**（不强制中断 LLM，避免半截输出）
- 将会话状态保存为 `paused`，下次可从当前阶段重新开始
- 不允许在 paused 状态下修改已完成的任务输出，只能 abort 或 resume

### 6.4 人工审批记录

每次检查点的人工决策记录在 `human_log.md`：

```markdown
## 检查点 A — 2026-03-02 10:30:15
**操作**：approve
**备注**：任务清单看起来合理，第 3 步要注意不改数据库层

## 检查点 B — 2026-03-02 10:45:02
**操作**：redo
**原因**：登录函数没有处理 token 过期的情况，需要补上
```

---

## 7. Agent 角色定义与自我进化

> **本节为概述，详细设计见独立文档：[AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md)**

自我进化系统是 ANTS 的核心差异化功能：Agent 在项目中持续积累经验，
同类问题越做越快，经验跨 Agent 共享（如环境问题 Tester 写入、Coder 直接复用）。

### 7.1 角色定义文件

每个 Agent 的角色定义存储在 `.ants/agents/roles/<name>.yaml`：

```yaml
# .ants/agents/roles/coder.yaml
name: Coder
description: 根据任务描述生成或修改代码，保证最小变更

# 固定部分（人工维护）
system_prompt: |
  你是一名经验丰富的软件工程师。
  你的职责是根据任务描述，在不破坏现有功能的前提下，做最小必要的代码修改。

tools_allowed: [read_file, write_file, search_code, run_shell]
constraints:
  - 不能修改任务范围以外的文件
  - 不能引入新的第三方依赖（除非任务明确要求）

# 进化部分（由系统从经验库加载，不直接存储在此文件）
# 运行时 Orchestrator 从 .ants/experience/ 检索 top-5 最相关经验注入
```

### 7.2 角色目录结构

```
.ants/agents/
├── registry.yaml           # Agent 注册表（见第 5 节）
└── roles/
    ├── planner.yaml
    ├── coder.yaml
    ├── reviewer.yaml
    ├── tester.yaml
    └── <custom_role>.yaml  # 按需新增
```

### 7.3 经验库概览

进化系统的核心是项目级**经验库**（存储在 `.ants/experience/`）：

| 经验类型 | 示例 | 共享范围 |
|---------|------|---------|
| environment | `pytest ModuleNotFoundError → pip install -e .` | 所有 Agent |
| tool_usage | `subprocess 中文路径 → 设置 PYTHONIOENCODING` | 所有 Agent |
| project_convention | `src/auth/ 函数必须写 docstring` | 所有 Agent |
| debug_pattern | `登录超时 → 检查 find_by_email 是否有索引` | 所有 Agent |
| domain_knowledge | `User 和 Order 的多对多关系` | 所有 Agent |

**Token 控制**：经验以三级方式注入（固定 5 条 + 任务相关 3 条 + 按需 5 条），
总上限 ≤ 2000 tokens，不影响主任务 context 预算。

### 7.4 进化流程（简图）

```
Agent 完成任务
    │
    ▼
reflect()：LLM 提炼 0~3 条经验 → 去重检查 → 写入经验库
    │
    ▼
下次任务开始：Orchestrator 检索经验库 → 注入最相关的经验到 context
```

详细设计（RAG 检索、去重策略、Token 控制、反馈机制、冷启动）
请参阅 **[AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md)**。

---

## 8. 最小可验证设计（MVP）详细设计

> **MVP 目标**：用最少代码，端到端跑通一个真实场景，证明核心机制有效。

### 8.1 MVP 范围

仅实现以下内容，其余全部推后：

| 包含 | 不包含 |
|------|--------|
| Planner + Coder + Reviewer 三个 Agent | Tester Agent（暂用人工验证） |
| SQLite 任务状态存储 | Redis / Kafka |
| `.ants/` 共享资料目录结构 | 向量数据库 |
| Agent 注册表（registry.yaml）+ 角色文件 | 热重载 / 动态注册 API |
| 阶段边界人工审批（CLI 交互） | Web UI |
| 结构化日志（文件） | OpenTelemetry |
| MCP 工具：read/write/search/run_shell | 复杂权限控制 |
| Agent 经验追加到 project_lessons | 自动去重 / 经验蒸馏 |

### 8.2 目录结构

```
ants/
├── ants/                       # 核心包
│   ├── __init__.py
│   ├── orchestrator.py         # 编排器（调度 + 阶段边界审批）
│   ├── supervisor.py           # 质检 Agent
│   ├── agents/
│   │   ├── base.py             # BaseAgent 抽象
│   │   ├── loader.py           # 从 registry.yaml 加载 Agent
│   │   ├── planner.py
│   │   ├── coder.py
│   │   └── reviewer.py
│   ├── context/
│   │   ├── shared_context.py   # 共享资料读写接口（对应 .ants/ 目录）
│   │   └── codebase_index.py   # 代码库索引建立与查询
│   ├── hil/
│   │   └── checkpoint.py       # 阶段边界人工审批（replace old gateway）
│   ├── tools/
│   │   ├── file_tools.py
│   │   ├── code_tools.py
│   │   └── git_tools.py
│   └── storage/
│       └── sqlite_store.py
├── cli.py
├── config.yaml
├── pyproject.toml
└── tests/
    ├── test_orchestrator.py
    ├── test_checkpoint.py
    ├── test_shared_context.py
    └── test_agent_loader.py
```

### 8.3 核心数据结构

#### 任务（Task）

```python
@dataclass
class Task:
    id: str                          # 唯一 ID，如 "task_001"
    title: str                       # 简短描述
    description: str                 # 详细说明
    assigned_agent: str              # 负责 Agent ID（对应 registry.yaml）
    phase: int                       # 所属阶段编号（1=规划, 2=执行, 3=验证）
    depends_on: list[str]            # 依赖的任务 ID（空列表 = 可立即执行）
    status: Literal[
        "pending",
        "in_progress",
        "completed",
        "needs_redo",
        "skipped"
    ]
    output: dict | None
    created_at: str
    completed_at: str | None
```

#### 会话状态（Session）

```python
@dataclass
class Session:
    id: str
    goal: str                        # 本次任务的总目标
    project_path: str                # 目标代码库路径
    tasks: list[Task]                # 任务清单
    shared_context_path: str         # 共享资料目录
    status: Literal["running", "paused", "completed", "aborted"]
    created_at: str
```

### 8.4 各模块详细设计

#### 8.4.1 SharedContext（共享资料层）

```python
class SharedContext:
    """所有 Agent 通过此类读写 .ants/ 目录，禁止直接操作文件。"""

    def __init__(self, project_root: str, session_id: str):
        self.knowledge_dir    = f"{project_root}/.ants/knowledge"
        self.project_state    = f"{project_root}/.ants/project_state"
        self.session_dir      = f"{project_root}/.ants/sessions/{session_id}"

    # 任务管理
    def read_tasks(self) -> list[Task]: ...
    def update_task(self, task_id: str, **kwargs): ...

    # 代码库索引（只读，由 Planner 建立）
    def search_code(self, query: str, top_k: int = 5) -> list[dict]: ...
    def get_file_context(self, path: str, symbol: str = None) -> str: ...

    # 会话记忆（追加，不覆盖）
    def append_memory(self, agent_id: str, content: str): ...
    def read_memory(self) -> str: ...

    # 知识读取（只读）
    def read_knowledge(self, filename: str) -> str: ...

    # 人工审批记录
    def log_human_decision(self, checkpoint: str, action: str, note: str): ...
```

```python
class Orchestrator:
    """
    核心调度循环。按阶段执行任务，阶段边界等待人工审批。
    同一阶段内无依赖的任务并行执行。
    """

    async def run(self, session: Session):
        for phase in self._get_phases(session):

            # 并行执行本阶段所有就绪任务
            await self._run_phase(phase, session)

            # 阶段完成后请求人工审批
            summary = self._summarize_phase(phase, session)
            decision = await self.checkpoint.request_approval(
                phase=phase.number, summary=summary, ctx=session.ctx
            )

            if decision.action == "abort":
                session.status = "aborted"
                return
            elif decision.action == "redo":
                self._reset_phase(phase, session, reason=decision.reason)
                # 重做：退回本阶段，重新执行
                continue
            elif decision.action == "edit" and phase.number == 1:
                # 只有规划阶段（Phase 1）支持编辑任务清单
                await self._interactive_edit_tasks(session)

            session.ctx.log_human_decision(f"phase_{phase.number}",
                                           decision.action, decision.reason)

    async def _run_phase(self, phase, session: Session):
        """并行执行同一阶段内互不依赖的任务批次。"""
        while True:
            ready = self._get_ready_tasks(phase, session)
            if not ready:
                break
            # 同一批次内并发执行
            await asyncio.gather(*[
                self._run_task(task, session) for task in ready
            ])

    async def _run_task(self, task: Task, session: Session):
        session.ctx.update_task(task.id, status="in_progress")
        agent = self.agents[task.assigned_agent]
        result = await agent.invoke(task, session.ctx)
        verdict = await self.supervisor.check(task, result)
        if verdict.passed:
            session.ctx.update_task(task.id, status="completed", output=result)
            await agent.reflect(task, result, session.ctx)   # 经验提炼
        else:
            session.ctx.update_task(task.id, status="needs_redo")
```

#### 8.4.4 BaseAgent 接口

```python
class BaseAgent:
    def __init__(self, llm_client, role: dict, tools: list):
        self.llm = llm_client
        self.role = role          # 来自 roles/<name>.yaml
        self.tools = tools

    async def invoke(self, task: Task, ctx: SharedContext) -> dict:
        """
        执行一个任务步骤。
        标准流程：
          1. 组装 system_prompt（base + project_lessons 最近 10 条）
          2. 读取 session_memory（了解整体进度）
          3. 检索相关代码片段（通过 codebase_index）
          4. 调用 LLM，允许调用工具
          5. 输出结构化结果
          6. 追加摘要到 session_memory
        """
        raise NotImplementedError

    async def reflect(self, task: Task, result: dict, ctx: SharedContext):
        """
        经验提炼：任务成功完成后，提炼本次任务中学到的项目专有知识，
        写入 .ants/experience/ 经验库（详见 AGENT_EVOLUTION.md）。
        """
        # LLM 判断本次执行是否产生了值得记录的项目专有经验
        # 如果有，调用 ExperienceLibrary.add() 写入
        pass
```

### 8.5 端到端场景演示

#### 场景 A：新项目 — 实现用户注册功能

```
$ ants run --goal "在 FastAPI 项目中实现用户注册接口" --project ./my_project

[ANTS] 🔍 扫描代码库...（已有 12 个文件）

━━━━━━━━━━━━━━━━━━ Phase 1: 规划 ━━━━━━━━━━━━━━━━━━
[ANTS] Planner 生成任务清单：
  task_001 [phase=2]: 实现注册路由        [Coder]
  task_002 [phase=2]: 实现密码 Hash 工具  [Coder]   （与 task_001 无依赖，可并行）
  task_003 [phase=2]: 实现邮件验证逻辑    [Coder]   depends_on: task_001
  task_004 [phase=3]: 代码审查            [Reviewer] depends_on: task_001,002,003

⏸  Phase 1 完成，请审批后继续
操作：[Enter] 批准继续 | [r] 重做本阶段 | [e] 编辑任务 | [q] 终止
> e
（打开 tasks.json 编辑器，人工把邮件验证的语言改为"中文模板"）
> （保存退出）
[ANTS] 任务已更新，继续执行。

━━━━━━━━━━━━━━━━━━ Phase 2: 执行 ━━━━━━━━━━━━━━━━━━
[ANTS] ▶ 并行执行 task_001 + task_002...
[ANTS] ✅ task_001 完成 | ✅ task_002 完成
[ANTS] ▶ 执行 task_003（依赖已满足）...
[ANTS] ✅ task_003 完成

⏸  Phase 2 完成，请审批后继续
展示：修改的 3 个文件 diff
操作：[Enter] 批准继续 | [r] 重做本阶段 | ...
> （Enter）

━━━━━━━━━━━━━━━━━━ Phase 3: 验证 ━━━━━━━━━━━━━━━━━━
[ANTS] ▶ Reviewer 审查代码...
[ANTS] ✅ 审查通过，2 条建议已记录。

⏸  Phase 3 完成，请审批后继续
> （Enter）
[ANTS] 🎉 全部完成！输出：./my_project/.ants/sessions/session_001/
```

#### 场景 B：维护老项目 — 修复登录超时问题

```
$ ants run --goal "修复用户反馈的登录 30 秒超时问题" --project ./legacy_project

[ANTS] 🔍 更新代码库索引（共 87 个文件）...

━━━━━━━━━━━━━━━━━━ Phase 1: 规划 ━━━━━━━━━━━━━━━━━━
[ANTS] Planner 分析，搜索 login, auth, timeout 相关文件...
[ANTS] 定位到：src/auth/login_handler.py, src/db/user_repository.py
[ANTS] 根因：find_by_email() 全表扫描。修复方案：加 Redis 缓存

任务清单：
  task_001 [phase=2]: 在 user_repository.py 的 find_by_email 加缓存  [Coder]
  task_002 [phase=3]: 运行登录相关测试，确认无破坏                    [Reviewer]

⏸  Phase 1 完成，请审批后继续
操作：[Enter] 批准继续 | [e] 编辑任务 | [q] 终止
> （Enter，确认修复方向）

━━━━━━━━━━━━━━━━━━ Phase 2: 执行 ━━━━━━━━━━━━━━━━━━
[ANTS] ▶ Coder 修改 user_repository.py（Coder 的 project_lessons 已包含：
        "该项目 Redis 客户端实例在 src/utils/cache.py"）
[ANTS] ✅ task_001 完成，变更 12 行

⏸  Phase 2 完成，diff 如下：...
> （Enter）

━━━━━━━━━━━━━━━━━━ Phase 3: 验证 ━━━━━━━━━━━━━━━━━━
[ANTS] ✅ 回归测试全部通过
[ANTS] 🎉 完成！
```

### 8.6 关键配置（config.yaml）

```yaml
llm:
  default_model: gpt-4o-mini      # 日常任务用小模型
  complex_model: gpt-4o           # Planner / Reviewer 用大模型
  api_key_env: OPENAI_API_KEY

project:
  default_path: "."
  index_cache_ttl: 3600           # 代码索引缓存时间（秒）

phases:
  checkpoints:                    # 哪些阶段边界暂停等待人工审批
    - 1                           # 规划完成后（必须）
    - 2                           # 执行完成后（必须）
    - 3                           # 验证完成后（可选）

budget:
  max_steps: 30
  max_tokens: 50000

output:
  session_dir: ".ants/sessions"
  log_level: INFO
```

### 8.7 验证标准

MVP 跑通的判断标准：

| 验证点 | 期望结果 |
|--------|----------|
| 新项目场景（场景 A） | 能生成可运行的代码，审查通过 |
| 老项目场景（场景 B） | 能定位到正确文件并生成精准 diff |
| 并行执行 | 无依赖的任务被并行调度，有依赖的等待前置完成 |
| 共享资料 | 后一个 Agent 的输出基于前一个的 session_memory |
| 阶段边界审批 | Phase 完成后自动暂停，AI 执行中不被打断 |
| Agent 注册 | disabled Agent 不被调度；新增 Agent 后热重载生效 |
| 经验进化 | 第 2 次运行时 project_lessons 中有上次任务的经验条目 |

---

## 9. 与完整版的关系

Lite 版不是替代，而是完整版的**第一阶段**：

```
ANTS Lite（MVP）
    │  完成并验证核心价值
    ▼
Phase 1: 加入 Tester Agent + 回归检测
    │
    ▼
Phase 2: 替换 SQLite → Redis，加入熔断/重试
    │
    ▼
Phase 3: 加入向量记忆、Web UI、A2A 跨框架支持
    │
    ▼
完整版 ANTS（见 DESIGN_REPORT.md）
```

每次升级都是独立的、可回退的，不需要一次性搭建全部基础设施。

---

*文档为精简方案设计草案（v0.2），欢迎通过 Issue 或 PR 提出修改建议。*
