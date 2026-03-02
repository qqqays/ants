# ANTS Lite — 精简落地方案

> **版本**：v0.1  
> **日期**：2026-03-02  
> **定位**：可落地的精简版，不追求"大而全"，先跑通核心价值

---

## 目录

1. [为什么要精简](#1-为什么要精简)
2. [两个核心目标](#2-两个核心目标)
3. [精简架构](#3-精简架构)
4. [资料共享机制](#4-资料共享机制)
5. [人工干预与纠偏机制](#5-人工干预与纠偏机制)
6. [最小可验证设计（MVP）详细设计](#6-最小可验证设计mvp详细设计)
7. [与完整版的关系](#7-与完整版的关系)

---

## 1. 为什么要精简

完整版 ANTS（见 [DESIGN_REPORT.md](./DESIGN_REPORT.md)）覆盖了生产级多 Agent 系统的所有短板，
但**系统越复杂越难落地**。精简版原则：

| 精简原则 | 说明 |
|----------|------|
| **目标驱动** | 只保留支撑两个核心目标的最小模块集 |
| **依赖轻量** | 优先用本地文件/SQLite，而非 Redis/Kafka |
| **可穿插人工** | 任意节点都允许人随时介入修正 |
| **渐进扩展** | 先跑通，再按需叠加生产级特性 |

---

## 2. 两个核心目标

### 目标一：开发新项目

```
人类 → 描述需求 → ANTS → [规划 → 编码 → 测试 → 总结] → 交付代码
             ↑__________________________|（随时纠偏）
```

涉及的典型 Agent：
- **Planner**：将需求拆解为任务清单（含文件/模块级别）
- **Coder**：逐任务生成/修改代码
- **Reviewer**：检查代码质量，输出问题列表
- **Tester**：生成并执行测试用例，报告通过/失败

### 目标二：维护老项目

```
人类 → 描述问题/需求 → ANTS → [读取代码库 → 定位 → 修改 → 验证] → 交付补丁
                ↑_______________________________________________|（随时纠偏）
```

额外需要的能力：
- **代码库索引**：能快速定位相关文件和函数（不读全库）
- **变更最小化**：只改必要的代码，不引入无关变动
- **回归检测**：修改后自动运行已有测试，确认没有破坏

---

## 3. 精简架构

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

---

## 4. 资料共享机制

多 Agent 协作的核心挑战：**每个 Agent 只看到自己的上下文，但需要基于共同的"世界观"工作。**

### 4.1 共享资料的三层结构

```
┌─────────────────────────────────────────┐
│  Layer 3: 领域知识（只读，人工维护）        │
│  • 项目背景文档、架构决策记录（ADR）        │
│  • 编码规范、测试规范                      │
│  • 第三方 API 文档摘要                    │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  Layer 2: 项目状态（读写，Agent 维护）      │
│  • 代码库文件树 + 函数/类索引              │
│  • 任务清单（含状态：待做/进行中/完成）      │
│  • 当前 PR / Issue 列表                  │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  Layer 1: 会话上下文（读写，本次任务专属）  │
│  • 本次任务目标和约束                     │
│  • 已完成步骤的摘要输出                   │
│  • 待处理问题列表                        │
└─────────────────────────────────────────┘
```

### 4.2 数据流：Agent 如何读写共享资料

```
  Planner 生成任务清单
       │
       ▼
  tasks.json ──────────────────────────────────┐
       │                                        │
  Coder 读取任务 → 修改代码 → 写入 code_diff.md │
       │                                        │
  Reviewer 读取 code_diff.md → 写入 review.json │
       │                                        │
  Tester 读取变更 → 运行测试 → 写入 test_result.json
       │
  Supervisor 读取所有输出 → 汇总 → 向人报告
```

实现要点：
- **每个 Agent 只写自己负责的文件**，其他文件只读 → 避免并发冲突
- **文件格式用 JSON/Markdown**，LLM 天然擅长读写
- **增量写入**：用 append 模式写日志，用 replace 模式写状态文件

### 4.3 老项目的代码库索引

老项目维护时，Agent 需要快速定位代码，不能让 LLM 读完整个代码库：

```python
# 代码库索引结构（context/codebase_index.json）
{
  "files": [
    {
      "path": "src/auth/login.py",
      "symbols": ["login_user", "validate_token", "LoginForm"],
      "summary": "用户登录逻辑，包含 JWT 验证",
      "last_modified": "2026-02-20"
    },
    ...
  ],
  "dependencies": {
    "src/auth/login.py": ["src/models/user.py", "src/utils/jwt.py"]
  }
}
```

建立索引的方式（选其一）：
1. **Tree-sitter**：精准提取所有语言的符号表（推荐）
2. **ctags**：轻量工具，支持多语言
3. **LLM 摘要**：首次运行时逐文件生成摘要，缓存到文件

---

## 5. 人工干预与纠偏机制

**核心设计理念**：人不是在任务"卡住"时才介入，而是**随时都能穿插进来纠偏**。

### 5.1 干预时机

| 干预时机 | 触发方式 | 人工可做的操作 |
|----------|----------|----------------|
| **任务规划完成后** | 自动暂停（可配置） | 修改/删除/增加任务 |
| **单步完成后** | 查看输出，主动插入 | 追加指令、修正输出、跳过/重做某步 |
| **Agent 遇到不确定时** | Agent 主动询问 | 澄清需求、提供缺失信息 |
| **质量检查不通过时** | 自动暂停 | 接受/拒绝/手动修改后继续 |
| **任意时刻** | 发送中断信号 | 终止/暂停，修改目标后重新启动 |

### 5.2 干预接口设计

人工干预通过**统一的指令通道**注入，Agent 在每轮循环开始前检查：

```
人类输入
    │
    ▼
┌──────────────────────────────────────────────┐
│              HIL Gateway（人工干预网关）        │
│                                               │
│  • 标准指令：pause / resume / abort           │
│  • 纠偏指令：inject "你漏掉了错误处理"         │
│  • 替换指令：replace_task "3" "改用 async/await │
│  • 回滚指令：rollback_to "step_2"             │
└──────────────────────────────────────────────┘
    │
    ▼
Orchestrator 在下一个 Agent 调度前处理干预指令
```

### 5.3 干预的实现方式（Lite 版）

**方式一：命令行交互式模式**（最简单）

```bash
$ ants run --task "给 login 模块加速率限制"
[ANTS] Step 1/4: Planner 分析代码库...
[ANTS] 任务清单已生成，请确认后继续（按 Enter / 输入修改指令）:
> 把第 3 步改成：只改 API 层，不改数据库层
[ANTS] 已更新任务 3。继续执行...
[ANTS] Step 2/4: Coder 读取 src/auth/login.py...
[ANTS] Step 2 完成。代码修改如下：（输出 diff）
按 Enter 继续，或输入修改意见:
> 这个变量名要用 rate_limit_remaining，不要用 remaining_count
[ANTS] 已注入修改意见，Coder 将在下一步重新生成...
```

**方式二：文件注入**（适合异步场景）

在运行目录创建 `.ants_inject` 文件，Orchestrator 每步前检查：

```
# .ants_inject（人工创建此文件即触发注入）
INJECT: 请在修改前先写单元测试
```

Orchestrator 读取后删除该文件，将内容注入下一个 Agent 的上下文。

**方式三：Web UI**（后续迭代）

运行时启动本地 Web 服务，提供可视化任务进度和实时干预界面。

### 5.4 纠偏后的一致性保证

纠偏不能只修改一处，还要同步状态：

```
人工修改指令 → HIL Gateway
    │
    ├─► 更新 tasks.json（修改受影响任务的状态为"待重做"）
    ├─► 清除受影响 Agent 的缓存输出
    ├─► 记录纠偏日志（correction_log.md：时间 + 原因 + 内容）
    └─► 通知 Supervisor 从哪一步重新开始
```

---

## 6. 最小可验证设计（MVP）详细设计

> **MVP 目标**：用最少代码，端到端跑通一个真实场景，证明核心机制有效。

### 6.1 MVP 范围

仅实现以下内容，其余全部推后：

| 包含 | 不包含 |
|------|--------|
| Planner + Coder + Reviewer 三个 Agent | Tester Agent（暂用人工验证） |
| SQLite 任务状态存储 | Redis / Kafka |
| 代码库文件索引（JSON） | 向量数据库 |
| 命令行人工干预（交互模式） | Web UI |
| 结构化日志（文件） | OpenTelemetry |
| MCP 工具：read/write/search/run_shell | 复杂权限控制 |

### 6.2 目录结构

```
ants/
├── ants/                       # 核心包
│   ├── __init__.py
│   ├── orchestrator.py         # 编排器（调度 + 干预检测）
│   ├── supervisor.py           # 质检 Agent
│   ├── agents/
│   │   ├── base.py             # BaseAgent 抽象
│   │   ├── planner.py          # 任务规划 Agent
│   │   ├── coder.py            # 编码 Agent
│   │   └── reviewer.py         # 审查 Agent
│   ├── context/
│   │   ├── shared_context.py   # 共享资料读写接口
│   │   ├── codebase_index.py   # 代码库索引建立与查询
│   │   └── session_memory.py   # 会话记忆
│   ├── hil/
│   │   └── gateway.py          # 人工干预网关
│   ├── tools/
│   │   ├── file_tools.py       # read_file / write_file
│   │   ├── code_tools.py       # search_code / run_shell
│   │   └── git_tools.py        # git_diff / git_log
│   └── storage/
│       └── sqlite_store.py     # SQLite 任务状态存储
├── cli.py                      # 命令行入口
├── config.yaml                 # 配置（LLM 模型、路径等）
├── pyproject.toml
└── tests/
    ├── test_orchestrator.py
    ├── test_hil_gateway.py
    └── test_shared_context.py
```

### 6.3 核心数据结构

#### 任务（Task）

```python
@dataclass
class Task:
    id: str                          # 唯一 ID，如 "task_001"
    title: str                       # 简短描述
    description: str                 # 详细说明
    assigned_agent: str              # 负责 Agent 类型
    depends_on: list[str]            # 依赖的任务 ID
    status: Literal[
        "pending",                   # 待执行
        "in_progress",               # 执行中
        "completed",                 # 完成
        "needs_redo",                # 被人工/Supervisor 标记重做
        "skipped"                    # 跳过
    ]
    output: dict | None              # Agent 的输出（完成后填入）
    correction_notes: list[str]      # 人工纠偏记录
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

### 6.4 各模块详细设计

#### 6.4.1 SharedContext（共享资料层）

```python
class SharedContext:
    """所有 Agent 通过此类读写共享资料，避免直接操作文件。"""

    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        # 固定文件路径
        self.tasks_file      = f"{session_dir}/tasks.json"
        self.codebase_index  = f"{session_dir}/codebase_index.json"
        self.session_memory  = f"{session_dir}/session_memory.md"
        self.correction_log  = f"{session_dir}/correction_log.md"

    def read_tasks(self) -> list[Task]: ...
    def update_task(self, task_id: str, **kwargs): ...

    def read_codebase_index(self) -> dict: ...
    def search_code(self, query: str, top_k: int = 5) -> list[dict]: ...

    def append_memory(self, agent: str, content: str): ...
    def read_memory(self) -> str: ...      # 返回完整的 session_memory.md

    def log_correction(self, note: str): ...
```

每个 Agent 在执行前调用 `read_memory()` 获取已发生的上下文摘要，
执行后调用 `append_memory()` 追加自己的输出摘要。

#### 6.4.2 CodebaseIndex（代码库索引）

```python
class CodebaseIndex:
    """为老项目维护场景建立代码快速检索能力。"""

    def build(self, project_path: str) -> dict:
        """
        遍历项目，对每个代码文件提取：
        1. 文件路径
        2. 符号列表（函数名/类名，用 ast.parse 或 tree-sitter）
        3. 文件大小（超过 500 行的标记为"大文件"）
        4. 最后修改时间
        结果写入 codebase_index.json
        """

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        BM25 关键词检索 + 符号名称精确匹配，返回最相关文件列表。
        query 示例："登录验证 JWT"  →  返回 src/auth/login.py 等
        """

    def get_file_context(self, file_path: str, symbol: str = None) -> str:
        """
        读取文件内容。如果 symbol 不为空，只返回该函数/类的代码片段。
        避免向 Agent 传入整个大文件。
        """
```

#### 6.4.3 HILGateway（人工干预网关）

```python
class HILGateway:
    """
    人工干预网关。Orchestrator 在每次调度前调用 check()。
    """

    INJECT_FILE = ".ants_inject"

    async def check(self, session: Session) -> HILAction | None:
        """
        检查是否有人工干预指令。返回 None 表示无干预，继续执行。
        """
        # 1. 检查 .ants_inject 文件
        if os.path.exists(self.INJECT_FILE):
            content = open(self.INJECT_FILE).read().strip()
            os.remove(self.INJECT_FILE)
            return HILAction(type="inject", content=content)

        # 2. 如果是交互模式，在 checkpoint 处等待用户输入
        if self.interactive and self._at_checkpoint(session):
            return await self._prompt_user(session)

        return None

    async def _prompt_user(self, session: Session) -> HILAction | None:
        """
        在终端展示当前进度，等待用户输入。
        支持：Enter（继续）、修改指令、pause、abort
        """

@dataclass
class HILAction:
    type: Literal["inject", "replace_task", "rollback_to", "pause", "abort", "resume"]
    content: str = ""
    target_task_id: str = ""
```

#### 6.4.4 Orchestrator（编排器）

```python
class Orchestrator:
    """
    核心调度循环。按依赖顺序执行任务，每步前检查 HIL 干预。
    """

    async def run(self, session: Session):
        while not session.is_done():

            # 1. 检查人工干预
            action = await self.hil.check(session)
            if action:
                await self._apply_hil_action(action, session)
                continue

            # 2. 找到下一个可执行任务（依赖已满足的 pending 任务）
            task = self._next_ready_task(session)
            if not task:
                await asyncio.sleep(0.5)
                continue

            # 3. 标记为进行中
            session.ctx.update_task(task.id, status="in_progress")

            # 4. 调用对应 Agent
            agent = self.agents[task.assigned_agent]
            result = await agent.invoke(task, session.ctx)

            # 5. Supervisor 质检
            verdict = await self.supervisor.check(task, result)
            if not verdict.passed:
                session.ctx.update_task(task.id, status="needs_redo",
                                        correction_notes=[verdict.reason])
                continue

            # 6. 完成
            session.ctx.update_task(task.id, status="completed", output=result)
            self._log(f"✅ Task {task.id} completed: {task.title}")
```

#### 6.4.5 BaseAgent 接口

```python
class BaseAgent:
    def __init__(self, llm_client, tools: list):
        self.llm = llm_client
        self.tools = tools

    async def invoke(self, task: Task, ctx: SharedContext) -> dict:
        """
        执行一个任务步骤。
        标准流程：
          1. 读取 session_memory（了解整体进度）
          2. 读取任务相关的代码/文件（通过 CodebaseIndex）
          3. 调用 LLM，允许调用工具
          4. 输出结构化结果
          5. 追加摘要到 session_memory
        """
        raise NotImplementedError
```

### 6.5 端到端场景演示

#### 场景 A：新项目 — 实现用户注册功能

```
$ ants run --goal "在 FastAPI 项目中实现用户注册接口" --project ./my_project

[ANTS] 🔍 扫描代码库...（已有 12 个文件）
[ANTS] 📋 Planner 生成任务清单：
  task_001: 分析现有用户模型和数据库配置      [Planner]
  task_002: 设计注册接口（路由 + 请求体）      [Planner]
  task_003: 实现注册逻辑（含密码 Hash）        [Coder]   依赖: task_002
  task_004: 代码审查                           [Reviewer] 依赖: task_003

[ANTS] ⏸ 任务清单已就绪，请确认（Enter 继续 / 输入修改意见）:
> 第 3 步要加邮件验证逻辑
[ANTS] 已更新 task_003。
[ANTS] ▶ 执行 task_001...
[ANTS] ✅ task_001 完成
[ANTS] ▶ 执行 task_002...
[ANTS] ✅ task_002 完成
[ANTS] ▶ 执行 task_003...（Coder 正在生成代码）
[ANTS] ✅ task_003 完成，修改了 2 个文件：
  + src/api/users.py（新增 register 路由）
  + src/services/auth.py（新增 send_verification_email）

按 Enter 继续代码审查，或输入意见:
> 邮件模板要用中文
[ANTS] 已注入意见，Reviewer 将带入此上下文...
[ANTS] ▶ 执行 task_004...（Reviewer 审查中）
[ANTS] ✅ 审查通过，共 2 条建议（已记录到 review.json）
[ANTS] 🎉 全部完成！查看输出：./my_project/.ants/session_001/
```

#### 场景 B：维护老项目 — 修复登录超时问题

```
$ ants run --goal "修复用户反馈的登录 30 秒超时问题" --project ./legacy_project

[ANTS] 🔍 建立代码库索引（共 87 个文件）...
[ANTS] 📋 Planner 生成任务清单：
  task_001: 定位登录相关代码（搜索 login, auth, timeout）  [Planner]
  task_002: 分析超时原因（数据库查询？外部 API？）          [Planner]
  task_003: 修复超时问题                                    [Coder]   依赖: task_002
  task_004: 验证修复（检查相关测试）                         [Reviewer] 依赖: task_003

[ANTS] ▶ 执行 task_001...
[ANTS] 🔍 搜索到相关文件：
  - src/auth/login_handler.py（含 login(), _validate_session()）
  - src/db/user_repository.py（含 find_by_email()）
  - config/timeouts.py

[ANTS] ▶ 执行 task_002...
[ANTS] 分析结果：find_by_email() 缺少索引，全表扫描导致超时。

[ANTS] ⏸ 确认修复方向（Enter 继续 / 输入意见）:
> 不要直接加数据库索引，先加缓存，索引让 DBA 评审后再加
[ANTS] 已更新修复策略。
[ANTS] ▶ 执行 task_003...（Coder 添加 Redis 缓存）
...
```

### 6.6 关键配置（config.yaml）

```yaml
llm:
  default_model: gpt-4o-mini      # 日常任务用小模型
  complex_model: gpt-4o           # Planner / Reviewer 用大模型
  api_key_env: OPENAI_API_KEY

project:
  default_path: "."
  index_cache_ttl: 3600           # 代码索引缓存时间（秒）

hil:
  interactive: true               # 是否开启交互式干预
  checkpoint_after:               # 哪些步骤后自动暂停等待确认
    - planning_done
    - code_generated

budget:
  max_steps: 30                   # 最大任务步数
  max_tokens: 50000               # 最大 Token 消耗

output:
  session_dir: ".ants"            # 会话数据保存目录
  log_level: INFO
```

### 6.7 验证标准

MVP 跑通的判断标准：

| 验证点 | 期望结果 |
|--------|----------|
| 新项目场景（场景 A） | 能生成可运行的代码，代码审查通过 |
| 老项目场景（场景 B） | 能定位到正确文件并生成精准 diff |
| 资料共享 | 后一个 Agent 的输出基于前一个 Agent 的结果 |
| 人工干预 | 注入意见后，下一个 Agent 的输出体现该意见 |
| 任务重做 | Supervisor 打回后，Agent 重新生成不同的输出 |

---

## 7. 与完整版的关系

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

*文档为精简方案设计草案，欢迎通过 Issue 或 PR 提出修改建议。*
