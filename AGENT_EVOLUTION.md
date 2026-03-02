# ANTS Agent 自我进化系统 — 详细设计

> **版本**：v1.0  
> **日期**：2026-03-02  
> **定位**：ANTS 核心差异化功能。Agent 在项目中积累经验、复用经验，同类问题越做越快。  
> **关联文档**：[ANTS_LITE.md §7](./ANTS_LITE.md#7-agent-角色定义与自我进化)、[DESIGN_REPORT.md](./DESIGN_REPORT.md)

---

## 目录

1. [为什么这是核心功能](#1-为什么这是核心功能)
2. [整体架构](#2-整体架构)
3. [经验条目的结构设计](#3-经验条目的结构设计)
4. [经验类型分类](#4-经验类型分类)
5. [经验库（Experience Library）详细设计](#5-经验库experience-library详细设计)
6. [跨 Agent 经验共享](#6-跨-agent-经验共享)
7. [Token 控制策略](#7-token-控制策略)
8. [检索设计（RAG）](#8-检索设计rag)
9. [经验生命周期](#9-经验生命周期)
10. [reflect() 详细设计](#10-reflect-详细设计)
11. [冷启动与引导](#11-冷启动与引导)
12. [实现路线](#12-实现路线)

---

## 1. 为什么这是核心功能

**现有 AI 编码 Agent 的核心痛点**：每次任务都从零开始，没有项目记忆。
- 同一个环境配置问题，第 10 次踩坑和第 1 次一样慢
- Agent 不知道"这个项目用 Poetry 不用 pip"、"数据库密码在 `.env.local`"
- Tester 发现了一个 CI 配置问题，Coder 下次还会犯同样的错

**ANTS 的目标**：让 Agent 变成一个**越用越懂这个项目**的团队成员。

| 项目第几次运行 | 没有进化系统 | 有进化系统 |
|--------------|------------|----------|
| 第 1 次 | 探索，试错 | 探索，试错，同时记录经验 |
| 第 2 次 | 同样的试错 | 检索到已有经验，直接复用 |
| 第 10 次 | 还是试错 | 经验库成熟，大多数常见问题秒解 |

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     Agent 自我进化系统                             │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   经验库（Experience Library）                │ │
│  │                                                              │ │
│  │  ┌──────────────────┐    ┌──────────────────────────────┐  │ │
│  │  │  经验条目存储      │    │         检索引擎              │  │ │
│  │  │  experience/      │    │   BM25 关键词 + 向量相似度    │  │ │
│  │  │  *.jsonl          │    │   → Top-K 最相关经验片段      │  │ │
│  │  └──────────────────┘    └──────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│          ▲                              │                          │
│   写入（reflect）                    检索（query）                  │
│          │                              ▼                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                       Agent 层                              │  │
│  │                                                              │  │
│  │  执行任务 ──► 遇到困难 ──► 检索经验库 ──► 复用已有方案        │  │
│  │      │                                                       │  │
│  │      └── 任务完成 ──► reflect() ──► 提炼新经验 ──► 写回库    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

经验库是 **项目级别** 的，存储在 `.ants/experience/` 目录下，
所有 Agent 共享同一个库，但写入时标明来源 Agent 和是否允许其他角色读取。

---

## 3. 经验条目的结构设计

每条经验是一个 JSON 对象，序列化为 JSONL 文件（追加友好，不需要全量重写）。

```jsonc
{
  // ── 身份 ──────────────────────────────────────────────────────
  "id": "exp_20260302_coder_a3f7",         // 唯一 ID（时间戳 + agent + 随机后缀）
  "source_agent": "coder",                  // 创建此经验的 Agent
  "session_id": "session_20260302_001",
  "created_at": "2026-03-02T10:30:00Z",

  // ── 分类 ──────────────────────────────────────────────────────
  "category": "environment",               // 见第 4 节的分类体系
  "tags": ["python", "dependency", "poetry"],
  "scope": "shared",                       // "private"=只有源 Agent 用 | "shared"=所有 Agent 可用

  // ── 内容 ──────────────────────────────────────────────────────
  "trigger": "运行 pytest 时出现 ModuleNotFoundError: No module named 'src'",
  // trigger：触发此经验被记录的具体问题/场景描述（用于检索匹配）

  "solution": "在项目根目录执行 `pip install -e .` 或在 pytest.ini 中添加 pythonpath = src",
  // solution：解决方案（具体、可操作）

  "context": {
    "file": "pyproject.toml",              // 相关文件（可选，用于精准检索）
    "symbol": null,
    "project_path_pattern": "*/tests/*"    // 适用路径模式（可选）
  },

  // ── 质量评分 ──────────────────────────────────────────────────
  "usefulness_score": 0.85,               // 被检索后实际解决了问题：+0.1；无效：-0.1
  "use_count": 3,                          // 被检索并采用的次数
  "last_used_at": "2026-03-02T14:00:00Z",

  // ── 生命周期 ──────────────────────────────────────────────────
  "status": "active",                      // "active" | "deprecated" | "merged"
  "superseded_by": null                    // 被更新版本替换时填写新 ID
}
```

### 3.1 向量索引字段

用于语义检索的文本 = `trigger + " " + solution`（拼接后生成 embedding）。
索引构建在 `.ants/experience/index/` 目录，使用轻量的本地向量库（见第 8 节）。

---

## 4. 经验类型分类

```
category（顶层）
│
├── environment（环境类）                ← 最高频，跨 Agent 共享价值最大
│   ├── env_setup        # Python 版本、虚拟环境、PATH 配置
│   ├── dependency       # 包安装、版本冲突、lock 文件
│   ├── ci_config        # CI/CD 流程、环境变量、secrets
│   └── os_quirk         # OS 差异（Linux/Mac/Windows）
│
├── tool_usage（工具使用类）             ← 工具调用技巧
│   ├── shell_command    # 特定命令的用法、参数组合
│   ├── git_workflow     # 分支策略、commit 规范、冲突解决
│   └── test_framework   # pytest/jest 特有用法
│
├── project_convention（项目约定类）     ← 项目专有规范
│   ├── naming_rule      # 命名约定
│   ├── code_style       # 格式化工具、风格规则
│   ├── arch_pattern     # 项目特有架构模式（如 service/repository 层）
│   └── api_contract     # 接口约定（响应格式、错误码）
│
├── debug_pattern（调试模式类）          ← 常见错误的快速定位方法
│   ├── error_mapping    # 特定错误信息 → 根因 + 修复方法
│   ├── log_analysis     # 从日志定位问题的技巧
│   └── perf_issue       # 性能问题定位模式
│
└── domain_knowledge（领域知识类）       ← 业务逻辑相关
    ├── business_rule    # 业务规则（如：用户状态机）
    └── data_model       # 数据模型关系（如：User 和 Order 的关联）
```

**scope 与 category 的默认映射**：

| category | 默认 scope | 说明 |
|----------|-----------|------|
| environment | shared | 环境问题对所有 Agent 都适用 |
| tool_usage | shared | 工具用法所有 Agent 都可能用到 |
| project_convention | shared | 项目约定全员必知 |
| debug_pattern | shared | 调试经验越共享越有价值 |
| domain_knowledge | shared | 业务知识全员共享 |

> 注：`scope="private"` 仅在 Agent 判断经验内容非常特定于某个角色时使用（罕见）。
> 默认全部 shared，让经验在团队中流动。

---

## 5. 经验库（Experience Library）详细设计

### 5.1 目录结构

```
.ants/experience/
├── entries/
│   ├── environment.jsonl       # 按 category 分文件，追加写入
│   ├── tool_usage.jsonl
│   ├── project_convention.jsonl
│   ├── debug_pattern.jsonl
│   └── domain_knowledge.jsonl
│
├── index/
│   ├── bm25_corpus.json        # BM25 倒排索引（关键词检索）
│   └── vectors.npy             # 向量矩阵（语义检索）；条目 ID 映射在 vectors_meta.json
│
└── meta.json                   # 库元数据：条目总数、最后更新时间、索引版本
```

### 5.2 ExperienceLibrary 接口

```python
class ExperienceLibrary:
    """项目级经验库，所有 Agent 共享。线程/协程安全写入。"""

    def __init__(self, experience_dir: str, embed_fn: Callable[[str], list[float]] | None = None):
        self.dir = experience_dir
        self.embed_fn = embed_fn  # None → 纯 BM25 模式（MVP）；有值 → BM25 + 向量混合

    # ── 写入 ──────────────────────────────────────────────────────

    async def add(self, entry: ExperienceEntry) -> str:
        """
        写入一条经验。自动执行去重检查（见 §9.2），返回最终存储的 ID。
        如果与已有条目高度相似，合并而非新增（更新 use_count 和 solution）。
        写入后异步更新 BM25 索引（向量索引批量构建，不实时更新）。
        """

    # ── 检索 ──────────────────────────────────────────────────────

    async def query(
        self,
        problem: str,               # 当前遇到的问题描述（自然语言）
        agent_id: str,              # 请求方 Agent（用于过滤 scope=private 的其他 Agent 经验）
        categories: list[str] | None = None,  # 限定分类，None = 全部
        top_k: int = 5,             # 返回条数上限
        min_score: float = 0.4,     # 最低相关度阈值
    ) -> list[RetrievedExperience]:
        """
        混合检索：BM25（关键词）× 0.4 + 向量相似度（语义）× 0.6 → 归一化后排序。
        MVP 阶段 embed_fn=None 时退化为纯 BM25。
        返回的每条结果包含原始 entry + 相关度 score。
        """

    # ── 反馈 ──────────────────────────────────────────────────────

    async def feedback(self, entry_id: str, helpful: bool):
        """
        Agent 使用某条经验后汇报是否有帮助。
        helpful=True  → usefulness_score += 0.1，use_count += 1
        helpful=False → usefulness_score -= 0.1
        usefulness_score < 0.2 且 use_count >= 3 → 自动标记 deprecated
        """

    # ── 维护 ──────────────────────────────────────────────────────

    async def rebuild_index(self):
        """全量重建 BM25 + 向量索引（建议在每次会话开始时增量检查）。"""

    async def prune(self, max_entries_per_category: int = 200):
        """
        清理低质量经验：
        1. 删除 status=deprecated 的条目
        2. 如超过 max_entries_per_category，删除 usefulness_score 最低的旧条目
        """
```

### 5.3 RetrievedExperience（检索结果）

```python
@dataclass
class RetrievedExperience:
    entry: ExperienceEntry
    score: float        # 综合相关度 0.0 ~ 1.0
    match_reason: str   # 人类可读的匹配原因（如 "关键词匹配: poetry, dependency"）
```

---

## 6. 跨 Agent 经验共享

### 6.1 共享的价值

环境类问题是 **最典型的跨 Agent 共享场景**：
- Tester 发现 `pytest` 找不到模块 → 记录到 `environment.jsonl`，scope=shared
- 下次 Coder 需要运行测试验证代码时 → 检索到相同经验 → 直接用，不再踩坑

```
会话 N：
  Tester ──遇到──► "ModuleNotFoundError: No module named 'src'"
          ──reflect──► 经验库写入 {trigger: "pytest ModuleNotFoundError src",
                                    solution: "pip install -e .",
                                    scope: shared}

会话 N+1：
  Coder ──遇到──► 同样问题
        ──query──► 命中 Tester 留下的经验
        ──直接执行──► pip install -e .
        ──反馈──► helpful=True → score +0.1
```

### 6.2 共享分类规则

Orchestrator 在 Agent 执行前调用 `library.query()`，过滤规则：

```python
# 允许读取的条目：
# 1. 自己写的（source_agent == current_agent_id）
# 2. scope == "shared" 的所有条目
# 不允许读取：
# 3. scope == "private" 且 source_agent != current_agent_id
```

### 6.3 工具使用经验的共享

```
示例：Tester 和 Coder 都可能需要运行 shell 命令。

Coder 记录：{
  category: "tool_usage",
  trigger: "用 subprocess 运行命令时中文路径报错",
  solution: "subprocess.run([...], env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})",
  scope: "shared"
}

Tester 后续运行测试脚本时遇到相同问题 → 直接检索到 → 直接复用
```

---

## 7. Token 控制策略

**核心矛盾**：经验越多越好，但 context window 有限（GPT-4o 约 128K tokens）。

### 7.1 三级加载策略

Agent 每次执行任务时，经验以 **三级渐进** 方式注入 context：

```
Level 1：角色基础经验（固定注入，每次都有）
  来源：经验库中本 Agent 的 usefulness_score 最高的 5 条
  Token 预算：≤ 750 tokens（5 条 × ~150 tokens）
  策略：系统按评分自动选

Level 2：任务相关经验（按需检索，task 开始前）
  来源：library.query(task.description, top_k=3, min_score=0.5)
  Token 预算：≤ 450 tokens（3 条 × ~150 tokens）
  策略：检索时已过滤低相关度，控制在 3 条以内

Level 3：遇到困难时的经验（动态检索，Agent 主动调用）
  来源：library.query(current_error, top_k=5, min_score=0.4)
  Token 预算：≤ 750 tokens（5 条 × ~150 tokens）
  策略：只在 Agent 判断遇到困难时触发，而非每步都查
```

**总经验 token 上限：≤ 2000 tokens**（约占 128K 的 1.6%）

### 7.2 经验条目的 Token 控制

单条经验写入时压缩：

```python
def compress_entry(entry: ExperienceEntry) -> str:
    """
    将经验压缩为 ≤ 150 tokens 的字符串，用于注入 context。
    格式：[{category}] {trigger} → {solution}
    示例：[environment] pytest ModuleNotFoundError src → pip install -e .
    """
    return f"[{entry.category}] {entry.trigger[:80]} → {entry.solution[:200]}"
```

> 150 tokens × 最多 13 条（Level1:5 + Level2:3 + Level3:5）= **约 1950 tokens**，
> 加少量换行和标题，控制在 2000 以内。

### 7.3 检索前的 Token 估算

```python
async def query_with_budget(self, problem: str, agent_id: str,
                             token_budget: int = 450) -> list[RetrievedExperience]:
    """
    在 token_budget 限制内尽量多返回相关经验。
    超出预算时优先保留 score 更高的条目。
    """
    results = await self.query(problem, agent_id, top_k=10)
    selected, tokens_used = [], 0
    for r in results:
        t = estimate_tokens(compress_entry(r.entry))
        if tokens_used + t > token_budget:
            break
        selected.append(r)
        tokens_used += t
    return selected
```

---

## 8. 检索设计（RAG）

### 8.1 MVP 阶段：纯 BM25

MVP 不依赖向量数据库，用 Python 纯标准库实现 BM25：

```
检索流程：
  问题描述（自然语言）
      │
      ▼
  分词（jieba 分词 for 中文 + 空格分词 for 英文）
      │
      ▼
  BM25 评分（对 trigger + solution 字段）
      │
      ▼
  按分数排序，取 top_k，过滤 min_score
      │
      ▼
  返回 RetrievedExperience 列表
```

实现依赖：`rank-bm25`（纯 Python，无需额外服务）

### 8.2 Phase 2：BM25 + 向量混合检索

```
混合评分 = BM25_score × 0.4 + cosine_similarity × 0.6

向量化方案（按轻量度排序，选其一）：
  Option A: sentence-transformers（本地模型，无需 API key，推荐）
            模型：paraphrase-multilingual-MiniLM-L12-v2（支持中英文，约 420MB）
  Option B: OpenAI text-embedding-3-small（需 API key，按量计费）
            成本：约 $0.02 / 百万 tokens，经验库不大时几乎免费
  Option C: Ollama 本地模型（完全本地，适合私有部署）
```

向量存储：`.ants/experience/index/vectors.npy`（NumPy 矩阵）+ 对应 ID 列表。
**不引入 Qdrant/Pinecone 等外部服务**，用 NumPy `np.dot()` 做余弦相似度计算，
经验库在 1000 条以内时性能完全够用（< 5ms）。

### 8.3 检索时机

| 时机 | 触发者 | 检索内容 |
|------|--------|----------|
| 任务开始前 | Orchestrator | `task.description` → 相关经验预加载（Level 2） |
| Agent 遇到错误 | Agent 自身 | `error_message + context` → 快速定位已知解法（Level 3） |
| Agent 不确定某个工具用法 | Agent 自身 | `tool_name + usage_scenario` → 工具经验（Level 3） |
| reflect() 执行时 | Agent 自身 | 去重检查（写入前检索相似条目） |

---

## 9. 经验生命周期

### 9.1 全流程

```
                       ┌─────────────────────┐
                       │   Agent 完成任务阶段  │
                       └──────────┬──────────┘
                                  │ 触发 reflect()
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 候选经验提炼（LLM 判断）                              │
│                                                              │
│  输入：任务描述 + 执行过程 + 最终结果 + 遇到的问题             │
│  输出：0~N 条候选经验，每条包含 trigger / solution / category  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 价值过滤                                             │
│                                                              │
│  判断每条候选经验是否值得存储：                                 │
│  ✅ 项目专有（其他项目不适用）                                  │
│  ✅ 可操作（有具体解决步骤）                                    │
│  ✅ 非显而易见（不是 LLM 本身已知的通用知识）                   │
│  ❌ 过滤：通用编程知识 / 任务描述 / 临时数据                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: 去重检查                                             │
│                                                              │
│  对每条候选经验执行 library.query(trigger, top_k=3)           │
│  如果相似度 > 0.85（高度相似）：                               │
│    → 合并：更新 solution（若新方案更好），增加 use_count        │
│  如果相似度 0.6~0.85（部分相似）：                             │
│    → 追加新条目，并在 meta 中标记两者的关联关系                 │
│  如果相似度 < 0.6：                                           │
│    → 直接新增                                                 │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 写入经验库                                           │
│                                                              │
│  追加到对应 category 的 JSONL 文件                             │
│  异步更新 BM25 索引                                           │
│  （向量索引每 10 条新增时批量重建，避免高频重建）                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 5: 使用与反馈                                           │
│                                                              │
│  被检索后 Agent 采用 → feedback(helpful=True) → score +0.1   │
│  被检索后 Agent 发现无效 → feedback(helpful=False) → score -0.1│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 6: 衰退与清理（定期触发）                                │
│                                                              │
│  score < 0.2 且 use_count ≥ 3 → deprecated                  │
│  每次会话开始时执行 prune()，清理 deprecated 条目              │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 去重策略详解

去重是控制经验库质量的关键：

```python
async def _check_duplicate(self, candidate: ExperienceEntry) -> DuplicateAction:
    """
    写入前检查是否存在相似条目。
    """
    # 先用 BM25 快速过滤，再用向量精确判断
    similar = await self.query(
        candidate.trigger,
        agent_id=candidate.source_agent,
        categories=[candidate.category],
        top_k=3,
        min_score=0.5,
    )

    if not similar:
        return DuplicateAction.ADD_NEW

    best = similar[0]
    if best.score >= 0.85:
        # 高度相似：选择更好的 solution
        return DuplicateAction.MERGE_INTO(best.entry.id)
    elif best.score >= 0.6:
        # 部分相似：新条目补充不同角度
        return DuplicateAction.ADD_RELATED(best.entry.id)
    else:
        return DuplicateAction.ADD_NEW
```

---

## 10. reflect() 详细设计

`reflect()` 是 Agent 进化的核心入口，在每个任务阶段完成、Supervisor 审核通过后触发。

### 10.1 reflect() 的 Prompt 设计

```
【系统提示】
你是一名工程师，刚刚完成了一项编码任务。
请回顾本次任务，提炼出值得记录到项目经验库的知识。

经验的标准：
1. 项目专有（其他项目不适用的特殊规律）
2. 可操作（有具体的操作步骤或命令）
3. 非显而易见（不是通用编程知识）
4. 下次遇到同类问题时能快速解决

不要记录：
- 任务目标和业务逻辑（那是任务文档，不是经验）
- "要写好代码"这类废话
- 本次任务的具体代码内容

【用户输入】
任务描述：{task.description}
执行过程摘要：{task_execution_log}  ← 精简版，不超过 500 tokens
遇到的问题：{errors_encountered}
最终结果：{task.output.summary}

请以 JSON 数组输出 0~3 条经验（若无值得记录的则返回空数组 []）：
[
  {
    "trigger": "触发此经验的问题/场景（≤ 80 字）",
    "solution": "解决方案（≤ 200 字，包含具体命令/步骤）",
    "category": "environment|tool_usage|project_convention|debug_pattern|domain_knowledge",
    "tags": ["tag1", "tag2"],
    "scope": "shared|private"
  }
]
```

### 10.2 执行过程摘要的生成（控制 Token）

`reflect()` 的输入不能把整个执行日志都塞进去，需要先压缩：

```python
def build_reflection_input(task: Task, execution_log: list[str]) -> str:
    """
    生成 reflect() 的输入，控制在 800 tokens 以内。
    策略：
    1. 取 execution_log 中的错误行（含 "error", "failed", "exception" 的行）
    2. 取最后 10 行（通常是最终结果）
    3. 去重后拼接，截断到 800 tokens
    """
    error_lines = [l for l in execution_log if any(
        kw in l.lower() for kw in ["error", "failed", "exception", "warning"]
    )]
    tail_lines = execution_log[-10:]
    combined = error_lines[:20] + tail_lines
    seen, deduped = set(), []
    for line in combined:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return truncate_to_tokens("\n".join(deduped), max_tokens=800)
```

### 10.3 reflect() 的执行时机与频率

| 触发条件 | 是否执行 reflect() | 原因 |
|----------|-------------------|------|
| 任务完成，Supervisor 通过 | ✅ 执行 | 最有价值：成功路径的经验 |
| 任务失败，Supervisor 打回重做 | ✅ 执行（记录失败原因） | 失败经验同样有价值 |
| 任务被人工 abort | ❌ 不执行 | 未完成，信息不完整 |
| 纯读取任务（无代码改动） | ❌ 不执行 | 通常无新经验 |
| 同一 session 内同类任务重复执行 | ⚠️ 节流（≥ 10 分钟间隔） | 避免大量重复写入 |

---

## 11. 冷启动与引导

### 11.1 全新项目：经验库为空时

经验库为空时，Agent 仍能正常工作（只是没有加速效果）。
为了让进化系统更快热身，支持以下冷启动方式：

**方式一：人工预填充**（推荐）

在 `.ants/knowledge/project_spec.md` 中写入已知的项目约定，
Orchestrator 在第一次运行时执行"知识转换"：

```python
async def bootstrap_from_knowledge(lib: ExperienceLibrary, knowledge_dir: str):
    """
    读取 knowledge/ 目录下的文档，
    用 LLM 提取可转化为经验条目的规律，批量写入经验库。
    """
```

**方式二：历史会话导入**

如果有已完成的会话（`sessions/` 目录），可以重跑所有任务的 `reflect()`：

```bash
$ ants experience rebuild --from-sessions
[ANTS] 扫描 12 个历史会话...
[ANTS] 提炼经验中...
[ANTS] 写入 47 条经验，去重合并 8 条。
[ANTS] 经验库就绪。
```

### 11.2 迁移到新项目

当同一技术栈的项目需要重用经验时：

```bash
$ ants experience export --categories environment,tool_usage --output shared_exp.jsonl
$ ants experience import shared_exp.jsonl --new-project /path/to/new_project
```

> 注：只导出 `environment` 和 `tool_usage` 类，`project_convention` 和 `domain_knowledge` 通常是项目专有的，不跨项目迁移。

---

## 12. 实现路线

### Phase 1（MVP，随 ANTS Lite 一起交付）

**目标**：最简实现，证明进化闭环能跑通。

| 功能 | 实现方式 | 估计工作量 |
|------|---------|-----------|
| 经验写入 JSONL | 直接 `json.dumps` + 文件追加 | 0.5 天 |
| BM25 检索 | `rank-bm25` 库 | 1 天 |
| reflect() Prompt + 解析 | LLM + JSON 解析 | 1 天 |
| 简单去重（BM25 相似度 > 0.7 则合并） | BM25 复用 | 0.5 天 |
| Agent 执行前加载 Level 1 + Level 2 经验 | 检索 + Token 裁剪 | 1 天 |
| **合计** | | **4 天** |

交付文件：
```
ants/
└── experience/
    ├── library.py       # ExperienceLibrary（BM25 版）
    ├── reflect.py       # reflect() + build_reflection_input()
    ├── entry.py         # ExperienceEntry dataclass
    └── retriever.py     # BM25Retriever
```

### Phase 2（向量检索增强）

**目标**：提升语义检索质量，支持中英文混合检索。

| 功能 | 实现方式 |
|------|---------|
| 向量化 + 余弦相似度 | sentence-transformers 本地模型 |
| BM25 + 向量混合打分 | 加权融合 |
| 经验质量评分反馈 | `feedback()` + 定期 `prune()` |
| 经验库迁移 CLI | `ants experience export/import` |

### Phase 3（高级进化能力）

| 功能 | 说明 |
|------|------|
| 经验蒸馏 | 定期将多条相关经验合并为更高层级的"模式经验" |
| 跨项目经验推荐 | 基于技术栈相似度，从其他项目经验库检索 |
| Agent 自我评估 | Agent 比较前后两次处理同类任务的效率，量化进化效果 |

---

## 附录：Token 估算参考

| 内容 | 估算 Token 数 |
|------|-------------|
| 单条经验（压缩后） | 约 80~150 tokens |
| Level 1 固定经验（5 条） | 约 400~750 tokens |
| Level 2 任务相关经验（3 条） | 约 240~450 tokens |
| Level 3 错误定位经验（5 条） | 约 400~750 tokens |
| **总经验注入上限** | **≤ 2000 tokens** |
| reflect() 输入（任务摘要） | 约 800 tokens |
| reflect() LLM 调用（含输出） | 约 1200 tokens（小任务） |

---

*文档版本 v1.0，与 ANTS_LITE.md v0.2 配套。如有修改建议请提交 Issue 或 PR。*
