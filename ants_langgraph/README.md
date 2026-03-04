# ANTS — LangGraph 实现

基于 [LangGraph](https://github.com/langchain-ai/langgraph) 的 ANTS 多 Agent 编码助手 MVP。

## 目录结构

```
ants_langgraph/
├── graph/
│   ├── state.py          # ANTSState TypedDict
│   ├── builder.py        # build_ants_graph()
│   └── nodes/
│       ├── setup.py      # setup_session
│       ├── planner.py    # planner_node（含 Level 1 经验注入）
│       ├── execution.py  # execution_phase_node + run_coder_task
│       ├── verification.py
│       ├── checkpoint.py # phase_checkpoint_node（HITL interrupt）
│       └── finalize.py
├── agents/
│   ├── base.py           # BaseAgent 接口
│   ├── planner.py
│   ├── coder.py
│   ├── reviewer.py
│   └── tester.py
├── experience/
│   ├── entry.py          # ExperienceEntry dataclass
│   ├── library.py        # ExperienceLibrary（BM25 + 写入 + 反馈）
│   ├── retriever.py      # BM25Retriever + RetrievedExperience
│   ├── reflect.py        # reflect_and_save()
│   └── budget.py         # ExperienceBudgetManager（Token 预算管理）
├── shared_context/
│   └── context.py        # SharedContext（会话记忆持久化）
├── cli.py                # CLI 入口
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

每个阶段完成后，CLI 会暂停并等待人工输入：
- **[Enter]** — 批准，继续下一阶段
- **[r]** — 重做本阶段
- **[q]** — 终止会话

## 经验库

会话结束后，`.ants/experience/` 目录下会保存本次积累的经验（JSONL 格式）。
下次运行时，相关经验会自动注入到 Agent 的 prompt 中（渐进式披露策略）。

## MVP 验证

参见 `../tests/mvp_validation.py`，验证三个核心指标：
1. **经验能被积累** — 第一次会话后 `.ants/experience/` 有新条目
2. **经验能被复用** — 第二次同类任务的 prompt 中包含历史经验
3. **注意力不被稀释** — 注入的经验总 token 数 ≤ 2000

## 设计文档

详见根目录的 [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)。
