# Agent 协作平台洞察报告：2025–2026 最新全景

> **版本**：v1.0  
> **日期**：2026-03-04  
> **状态**：供讨论  
> **关联文档**：[完整设计报告（2024–2025 基础调研）](./DESIGN_REPORT.md)、[精简落地方案](./ANTS_LITE.md)

---

## 目录

1. [2025–2026 领域全景概览](#1-2025-2026-领域全景概览)
2. [代码优先框架（2025 新版/重大更新）](#2-代码优先框架2025-新版重大更新)
   - 2.1 OpenAI Agents SDK
   - 2.2 Google ADK（Agent Development Kit）
   - 2.3 Microsoft Agent Framework（AutoGen + Semantic Kernel 合并版）
   - 2.4 LangGraph（2025 重大更新）
   - 2.5 CrewAI Flows（2025 企业级升级）
   - 2.6 AWS Bedrock Agents + AgentCore
3. [互操作协议层：MCP 与 A2A 生态成熟](#3-互操作协议层mcp-与-a2a-生态成熟)
4. [自主编码 Agent 平台（最接近 ANTS 场景）](#4-自主编码-agent-平台最接近-ants-场景)
   - 4.1 GitHub Copilot Coding Agent
   - 4.2 Devin 2.0（Cognition）
   - 4.3 Amazon Q Developer
5. [低代码 / 无代码 Agent 平台](#5-低代码--无代码-agent-平台)
   - 5.1 Dify
   - 5.2 n8n
   - 5.3 Langflow
   - 5.4 Coze
   - 5.5 Flowise
6. [2025–2026 全框架横向对比矩阵](#6-2025-2026-全框架横向对比矩阵)
7. [行业趋势与架构范式演进](#7-行业趋势与架构范式演进)
8. [与 ANTS 需求的差距分析](#8-与-ants-需求的差距分析)
9. [结论：是否需要独立开发？](#9-结论是否需要独立开发)
10. [参考资料](#10-参考资料)

---

## 1. 2025–2026 领域全景概览

2024 年底至 2026 年初，Agent 协作领域经历了从"实验原型"到"生产落地"的关键跃迁，主要体现在以下几个维度：

| 维度 | 2024 年状态 | 2025–2026 年状态 |
|------|------------|-----------------|
| **框架成熟度** | 以原型框架为主（Swarm、早期 AutoGen） | 生产级框架普及（Agents SDK、ADK、Agent Framework） |
| **互操作标准** | 各框架各自为政，无通用协议 | MCP 广泛落地，A2A 协议由 Linux 基金会托管，50+ 企业加入 |
| **编码 Agent** | 单 Agent 辅助编写（Copilot、Cursor）| 自主多 Agent 并行开发（Devin 2.0、Copilot Coding Agent）|
| **经验积累** | 无跨会话记忆机制 | 基于 RAG 的长期记忆开始成为标准配置 |
| **低代码生态** | Flowise/Langflow 早期 | Dify、n8n 企业级成熟，支持多 Agent 编排 |
| **云托管** | 几乎无托管平台 | LangGraph Cloud、Vertex AI Agent Engine、Azure AI Foundry 全面推出 |

**核心驱动力**：大模型能力（特别是 o1/o3 系列推理模型和 Claude 3.7）使 Agent 在复杂任务上的可靠性大幅提升，
推动业界从"单 Agent 辅助"向"多 Agent 自主团队"快速演进。

---

## 2. 代码优先框架（2025 新版/重大更新）

### 2.1 OpenAI Agents SDK

- **发布时间**：2025 年 3 月（正式取代 Swarm，定位为"Swarm 的生产版"）
- **仓库**：https://github.com/openai/openai-agents-python（⭐ 快速增长）
- **核心抽象**：`Agent`、`Runner`、`Tool`、`Handoff`（移交）四个基础元语
- **核心特性**：
  - **Native Handoff**：Agent 之间通过 `transfer_to_*()` 无缝移交上下文，天然解决"万能 Agent"问题
  - **内置追踪**：每步（工具调用、Handoff、LLM 调用、Guard 检查）全程自动追踪，无需额外插桩
  - **Guardrails**：在输入/输出层做结构化验证，快速失败，防止错误向下游传播
  - **多模型支持**：通过 LiteLLM 支持 Anthropic/Mistral/Azure 等非 OpenAI 模型
  - **会话持久化**：内置 session memory，支持长流程断点续传
- **优点**：
  - 抽象层薄，入门极快，标准 Python 即可编排复杂多 Agent 流
  - 与 OpenAI 模型生态（GPT-4o、o3 等）深度集成
  - 内置 tracing 减少调试成本
- **缺点**：
  - 图状复杂工作流（如带循环的 FSM）需手工拼装，没有 LangGraph 的原生 DAG/状态机支持
  - 仍以 OpenAI 生态为中心，非 OpenAI 路径需额外适配
  - 无内置经验记忆 / 跨项目知识库能力

---

### 2.2 Google ADK（Agent Development Kit）

- **发布时间**：2025 年 4 月 Google Cloud NEXT，随即开源
- **仓库**：https://github.com/google/adk-python（Python）、https://github.com/google/adk-java（Java）
- **多语言**：Python、TypeScript、Go、Java（正式生产级支持）
- **核心特性**：
  - **原生多 Agent 层次化编排**：Root Agent → Sub-Agents，支持顺序/并行/循环/动态路由四种模式
  - **模型无关**：官方支持 Gemini 全系列，同时通过 LiteLLM 集成 Anthropic、Meta、Mistral 等
  - **全生命周期工具链**：本地 CLI + Web UI 开发调试 → Cloud Run / K8s / Vertex AI Agent Engine 部署
  - **内置评估框架**：对 Agent 的推理过程和最终结果做自动化评测
  - **多模态流式交互**：支持音视频双向流，适合语音/视频交互场景
  - **Session/Memory 管理**：原生支持跨轮次、跨 Agent 的会话记忆
  - **MCP + A2A 双协议支持**：一等公民
- **优点**：
  - 目前最完整的企业级多 Agent 框架，覆盖从开发到生产全链路
  - 跨语言支持（不绑定 Python 生态）
  - 开源且不强制绑定 Google Cloud
- **缺点**：
  - 学习曲线较陡，配置项多
  - Vertex AI Agent Engine 深度使用仍偏 Google Cloud 生态
  - 无编码场景专属能力（代码库索引、diff 管理等）

---

### 2.3 Microsoft Agent Framework（AutoGen + Semantic Kernel 合并版）

- **发布时间**：2025 年底，Microsoft 将 AutoGen 与 Semantic Kernel 统一合并
- **仓库**：https://github.com/microsoft/autogen（AutoGen 进入维护模式，新功能集中在合并框架）
- **背景**：AutoGen 侧重"对话驱动多 Agent"，Semantic Kernel 侧重"插件/技能驱动企业编排"；
  合并后统一为**插件驱动 + 对话协作**的企业级框架
- **核心特性**：
  - 企业级安全性、合规性（RBAC、审计日志、Azure AD 集成）
  - 与 Microsoft 365 Copilot Studio、Azure AI Foundry 深度打通
  - 插件（Plugin）体系：将外部 API / 数据库 / 内部工具统一封装为可复用插件
  - 支持 .NET / Python / Java 三语言
- **优点**：
  - 企业级特性最完善（合规、安全、可观测）
  - 与 Azure / M365 生态无缝集成
  - 强大的插件市场生态
- **缺点**：
  - AutoGen 的"对话驱动"灵活性在合并后有所降低
  - 仍偏向 Microsoft 生态，跨云场景需额外适配
  - 原 AutoGen 的新项目已不推荐

---

### 2.4 LangGraph（2025 重大更新）

- **仓库**：https://github.com/langchain-ai/langgraph（⭐ 25k+，同比翻倍增长）
- **生产用户**：Klarna、Rakuten、GitLab、LinkedIn
- **2025 主要更新**：
  - **Checkpointing v2**：选择性持久化，支持"时间旅行"（回放任意历史状态）和分支调试
  - **持久化长期记忆**：跨会话的 Agent 状态存储，短期（工作记忆）+ 长期（向量库）双层
  - **多流式输出模式**：token 流、消息流、状态快照流，适配不同前端 UI 需求
  - **深度 HITL（Human-in-the-Loop）**：可在任意节点暂停，不限于阶段边界，支持异步审批
  - **LangGraph Cloud**：托管版，自动弹性伸缩 + 内置 LangSmith 可观测（商业）
  - **LangGraph 1.0 Alpha**（2025 Q3）：API 稳定，进入 GA 准备阶段
- **优点**：
  - 目前开源框架中**可观测性最强、状态控制最精细**
  - 大量实战验证的生产案例
  - 与 LangChain 生态（RAG、向量库、工具调用）无缝集成
- **缺点**：
  - 图模型学习曲线仍然较陡
  - 完全分布式场景依赖 LangGraph Cloud（商业）
  - 仍以 Python 为主，非 Python 支持有限

---

### 2.5 CrewAI Flows（2025 企业级升级）

- **仓库**：https://github.com/crewAIInc/crewAI（⭐ 45k+，超越 AutoGen 成为最受欢迎的多 Agent 框架）
- **2025 核心升级**：
  - **Flows 架构**：在原有"Crew = 角色团队"基础上，新增 Flows（有向流程图）用于确定性工作流编排，
    补齐了复杂分支/条件/串行控制的短板
  - **Redis 持久化记忆**：Agent 跨会话长期记忆，内置懒加载优化性能
  - **CrewAI AMP Suite**（企业版）：统一控制台 + 追踪 + 可观测 + RBAC + 私有化部署
  - **异步并发**：任务步骤支持异步触发，提升大规模工作流吞吐量
  - **成本优化**：缓存重复 LLM 调用，智能重试失败子任务
- **优点**：
  - 社区最大，入门最快，生产成熟度快速提升
  - Flows + Crew 双模式覆盖从原型到生产
  - AMP Suite 提供完整企业级运营能力
- **缺点**：
  - 复杂图状工作流的表达能力仍弱于 LangGraph
  - 精细状态控制（时间旅行、精确回溯）不如 LangGraph
  - AMP Suite 为商业付费产品

---

### 2.6 AWS Bedrock Agents + AgentCore

- **背景**：2025 年 AWS 在 Bedrock 基础上发布 AgentCore，增加企业级治理层
- **核心特性**：
  - **Supervisor 多 Agent 模型**：一个 Supervisor Agent 协调多个子 Agent，结构清晰
  - **与 AWS 服务深度集成**：Lambda、S3、DynamoDB、Step Functions 等
  - **AgentCore 治理层**：细粒度 RBAC、VPC 隔离、合规审计、自动扩缩容
  - **Amazon Q Developer**：面向开发者的编码 Agent，集成于 AWS IDE 插件和 GitHub
- **优点**：
  - 企业级安全和合规能力最完善（适合金融、医疗等监管行业）
  - 与 AWS 生态零摩擦集成
- **缺点**：
  - 强 AWS 锁定，跨云困难
  - 开放性和自定义灵活性低于开源框架

---

## 3. 互操作协议层：MCP 与 A2A 生态成熟

### 3.1 MCP（Model Context Protocol）—— "AI 的 USB 接口"

- **维护方**：Anthropic（开源，社区驱动）
- **定位**：统一 AI Agent 与外部工具/数据库/API 之间的接口标准，解决 M×N 集成爆炸问题
- **2025 采纳现状**：
  - Anthropic Claude 原生支持
  - GitHub Copilot Coding Agent 通过 MCP 扩展工具能力
  - Microsoft Azure Agent Factory 内置 MCP 支持
  - VS Code、Cursor、Windsurf 均内置 MCP 客户端
  - 独立 MCP Server 生态超过 2000+ 个（GitHub、Slack、Figma、数据库连接器等）
- **核心价值**：任何符合 MCP 规范的工具，可被任何支持 MCP 的 Agent 无缝调用

### 3.2 A2A（Agent2Agent Protocol）—— "Agent 之间的通用语言"

- **发布时间**：2025 年 4 月 Google 发布，随后移交 Linux 基金会
- **定位**：解决跨框架、跨厂商、跨组织的 Agent 互发现、互通信、互协作问题
- **2025–2026 采纳现状**：
  - 50+ 主要企业合作伙伴（Salesforce、SAP、IBM、Microsoft、Accenture、ServiceNow 等）
  - Google ADK 原生支持 A2A
  - OpenAI Agents SDK、LangGraph、CrewAI 均在适配 A2A
  - Linux 基金会托管，类似 HTTP/OpenTelemetry 的开放标准路径
- **核心价值**：
  - Agent 通过 A2A 广播自身能力（AgentCard），其他 Agent 可动态发现并委派任务
  - 跨组织 Agent 协作：公司 A 的客服 Agent 可无缝调用公司 B 的数据分析 Agent

### 3.3 MCP + A2A 的互补关系

```
┌─────────────────────────────────────────────────────────────────┐
│                       Agent 协作系统                              │
│                                                                   │
│  Agent A ──[A2A]──► Agent B ──[A2A]──► Agent C                  │
│     │                   │                   │                    │
│   [MCP]              [MCP]              [MCP]                    │
│     │                   │                   │                    │
│  工具/数据库          工具/API           工具/文件系统             │
└─────────────────────────────────────────────────────────────────┘

MCP = Agent ↔ 外部工具的标准接口（纵向打通工具层）
A2A = Agent ↔ Agent 的标准通信协议（横向打通协作层）
```

**结论**：MCP + A2A 正在成为 Agent 生态的"基础设施层"，**类似 HTTP + REST 之于 Web 服务的地位**。
2026 年不支持这两个协议的框架将面临严重的互操作性劣势。

---

## 4. 自主编码 Agent 平台（最接近 ANTS 场景）

### 4.1 GitHub Copilot Coding Agent

- **发布时间**：2025 年 Microsoft Build（5 月）
- **核心能力**：
  - 通过 GitHub Issue 分配任务，Agent 自动分析代码、生成 PR、更新文档
  - 运行在沙盒 GitHub Actions 环境中，所有操作可审计
  - 基于 MCP 扩展工具能力（连接企业内部数据源）
  - 严格的人工审批：PR 在人工审核前不能合并，CI/CD 不执行
- **已支持场景**：Bug 修复、代码重构、新增测试、文档更新、依赖升级
- **限制**：
  - **单 Agent 模型**：目前不支持 Planner + Coder + Reviewer 多角色并行
  - **无项目级经验积累**：每次任务从零开始，无法学习项目特有知识
  - **需要 GitHub Copilot Enterprise 订阅**（付费，且绑定 GitHub 平台）
  - 自定义编排逻辑（如"先规划再并行编码再审查"流程）支持有限

---

### 4.2 Devin 2.0（Cognition）

- **发布时间**：2025 年，Cognition Labs
- **定价**：$20/月（个人入门）至企业协议（Goldman Sachs、Nubank 等大客户）
- **核心能力**：
  - 自主创建隔离开发环境（Shell + 编辑器 + 浏览器），独立完成从分析到 PR 提交的全流程
  - **Devin 2.0 关键新特性：Agent 并行"舰队"**（Fleets of Devins）：
    同时启动多个 Devin 实例，并行处理跨多个仓库的大规模迁移/漏洞修复任务
  - 与 GitHub、Jira、CI/CD 深度集成，通过 Slack 接受任务指令
  - SWE-bench 基准：约 14% 端到端自主解决真实 GitHub Issue（行业领先）
  - 实际企业案例：10–20× 加速代码迁移，80% 减少安全漏洞修复时间
- **限制**：
  - **闭源 SaaS，无法私有化部署**
  - **无项目级记忆/经验积累**：知道"行业最佳实践"，但不知道"这个项目用了什么自定义约定"
  - 对模糊需求和开放性任务表现不稳定（最佳任务类型：明确、有边界的技术任务）
  - 不支持自定义 Agent 角色（Planner/Reviewer 等专业化分工）

---

### 4.3 Amazon Q Developer

- **背景**：AWS 面向开发者的 AI 编码 Agent，深度集成于 AWS 生态
- **核心能力**：
  - IDE 插件（VS Code、JetBrains）内置 Agent 模式
  - 与 GitHub Actions、AWS CodePipeline 集成
  - 支持代码生成、测试生成、安全扫描、依赖升级
- **限制**：
  - 强 AWS 生态依赖
  - 无多 Agent 并行架构（单 Agent 辅助模式）

---

## 5. 低代码 / 无代码 Agent 平台

### 5.1 Dify

- **定位**：企业级 AI 应用和 Agent 开发平台（全栈）
- **核心特性**：
  - 可视化工作流构建器 + 知识库管理 + Prompt 工程一体化
  - SOC2 合规、审计日志、团队协作功能
  - 支持多 Agent 编排（含并行节点）
  - 后端即服务（BaaS）：直接暴露 API，无需额外开发
  - 开源自托管版本 + 云托管版本
- **最适合**：需要快速上线 AI 应用的企业，特别是非纯技术团队

### 5.2 n8n

- **定位**：开源自动化工作流平台，深度集成 AI Agent 能力
- **核心特性**：
  - 300+ 服务连接器（Slack、GitHub、CRM、数据库等）
  - 支持 JavaScript/TypeScript 自定义逻辑
  - AI Agent 节点：可在工作流中插入 LLM 调用和 Agent 步骤
  - 开源自托管，支持企业级部署
- **最适合**：需要将 AI 能力融入现有业务自动化流程的团队

### 5.3 Langflow

- **定位**：面向 AI 工程师的可视化 LangChain Agent 构建 IDE
- **核心特性**：
  - 节点拖拽构建多 Agent 流，底层是 LangChain/LangGraph
  - 流定义为 JSON，可导入导出共享
  - 支持 MCP 部署（将 Flow 暴露为 MCP Server）
  - REST API 集成，支持 Python 自定义扩展
- **最适合**：需要快速迭代 Agent 原型、同时又希望保留代码级控制的 AI 工程师

### 5.4 Coze

- **定位**：无代码对话 Bot 构建平台（字节跳动）
- **核心特性**：NLP 驱动、多渠道部署（微信、飞书、Web 等）
- **限制**：主要面向聊天 Bot 场景，不适合复杂多 Agent 编程任务

### 5.5 Flowise

- **定位**：LangChain 可视化 Builder，专注 RAG 和知识库 Chatbot
- **核心特性**：最快的 RAG Chatbot 部署路径，一键嵌入 Web 组件
- **限制**：多 Agent 编排能力弱，主要面向知识库问答场景

---

## 6. 2025–2026 全框架横向对比矩阵

| 框架/平台 | 类型 | 上手难度 | 多 Agent 编排 | 状态持久化 | 经验积累 | HITL | MCP | A2A | 编码专用 | 自托管 | GitHub ⭐ |
|-----------|------|---------|-------------|-----------|---------|------|-----|-----|---------|-------|---------|
| **OpenAI Agents SDK** | 代码框架 | ⭐⭐⭐⭐ | 中（Handoff） | 基础 | ❌ | 部分 | ✅ | 适配中 | ❌ | ✅ | 快速增长 |
| **Google ADK** | 代码框架 | ⭐⭐⭐ | 强（层次化） | 强 | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | 快速增长 |
| **Microsoft Agent Framework** | 代码框架 | ⭐⭐⭐ | 强 | 强 | ❌ | ✅ | ✅ | ✅ | ❌ | ✅（.NET/PY）| ~33k |
| **LangGraph** | 代码框架 | ⭐⭐ | 强（图模型） | 最强 | ❌ | 深度✅ | ✅ | 适配中 | ❌ | ✅ | 25k+ |
| **CrewAI Flows** | 代码框架 | ⭐⭐⭐⭐ | 强 | 强（Redis）| ❌ | ✅ | ✅ | 适配中 | ❌ | ✅ | 45k+ |
| **AWS Bedrock AgentCore** | 云平台 | ⭐⭐⭐ | 中（Supervisor）| 强 | ❌ | ✅ | ✅ | ✅ | ✅（Q Dev）| ❌（AWS） | — |
| **GitHub Copilot Coding Agent** | SaaS 编码 | ⭐⭐⭐⭐⭐ | ❌（单 Agent）| ❌ | ❌ | ✅（PR 审批）| ✅ | ❌ | ✅✅ | ❌（GitHub）| — |
| **Devin 2.0** | SaaS 编码 | ⭐⭐⭐⭐⭐ | 部分（Fleets）| ❌（跨项目）| ❌ | 部分 | ❌ | ❌ | ✅✅ | ❌（SaaS）| — |
| **Amazon Q Developer** | SaaS 编码 | ⭐⭐⭐⭐⭐ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌（AWS）| — |
| **Dify** | 低代码平台 | ⭐⭐⭐⭐ | 中 | 中 | ❌ | 部分 | ✅ | 适配中 | ❌ | ✅ | 75k+ |
| **n8n** | 低代码自动化 | ⭐⭐⭐⭐ | 中 | 中 | ❌ | 部分 | ✅ | ❌ | ❌ | ✅ | 45k+ |
| **Langflow** | 低代码框架 | ⭐⭐⭐ | 中（LangChain） | 中 | ❌ | 部分 | ✅（MCP Server）| ❌ | ❌ | ✅ | 40k+ |

> 注：⭐ 数量越多 = 入门越容易；❌ = 不支持或支持极弱；✅ = 原生支持。Stars 数据截止 2026-03。

**关键发现：所有现有框架都缺乏"项目级经验积累（Experience Library）"能力。**

---

## 7. 行业趋势与架构范式演进

### 趋势一：从"单 Agent 辅助"到"Agent 团队自主执行"

2024 年主流是"人写代码，AI 给建议"；2025–2026 年向"人定目标，Agent 团队执行"快速演进。
Devin 的 Fleets 模式、Copilot Coding Agent 的 Issue→PR 全流程、ADK 的层次化多 Agent 编排，
都是这一趋势的体现。

### 趋势二：MCP + A2A 成为基础设施，互操作性成为标配

不支持 MCP/A2A 的 Agent 系统将逐渐被生态孤立。
类比：2010 年代不支持 REST API 的企业系统会被整合浪潮淘汰。

### 趋势三：Human-in-the-Loop 从"附加功能"变为"一等公民"

所有主流框架（LangGraph、CrewAI Flows、OpenAI Agents SDK、ADK）都在 2025 年显著加强了 HITL 能力。
业界共识：**生产级 Agent 系统必须在关键节点允许人工介入**，不能是"黑盒全自动"。

### 趋势四：Agent 记忆与知识积累开始商业化

- LangGraph 持久化长期记忆（向量库 + 状态检查点）
- CrewAI Redis 持久化记忆
- Mem0、Zep 等第三方 Agent 记忆即服务（MaaS）兴起
- **但这些主要是"通用知识记忆"，不是"项目专属经验积累"**

### 趋势五：推理模型（Reasoning Models）重塑 Agent 能力上限

- OpenAI o3、Anthropic Claude 3.7 的深度推理能力使 Agent 在复杂任务上的可靠性大幅提升
- SWE-bench 满分接近，预示编码 Agent 在受限任务上即将突破人类平均水平
- 这为 ANTS 类系统的"经验积累"提供了更好的底层推理基础

### 趋势六：低代码平台与代码框架边界模糊

Dify 支持 MCP；Langflow 底层是 LangGraph；n8n 支持 JavaScript 自定义逻辑。
技术边界在模糊，选择框架更多取决于团队技术栈和运营需求，而非能力上限。

---

## 8. 与 ANTS 需求的差距分析

ANTS 的核心需求（来自 [ANTS_LITE.md](./ANTS_LITE.md) 和 [AGENT_EVOLUTION.md](./AGENT_EVOLUTION.md)）：

| ANTS 需求 | 需求来源 | 现有最佳替代 | 差距程度 |
|---------|---------|------------|---------|
| 多 Agent 并行执行（Planner/Coder×N/Reviewer/Tester）| ANTS_LITE §3 | LangGraph、Google ADK、CrewAI Flows | 🟡 中（需定制编码 Agent 角色） |
| Human-in-the-Loop 阶段边界审批 | ANTS_LITE §6 | LangGraph（深度 HITL）、OpenAI Agents SDK | 🟡 中（现有 HITL 通常是"任意节点暂停"而非"阶段边界"范式） |
| 共享资料库（.ants/ 结构化知识）| ANTS_LITE §4 | 无直接对应 | 🔴 高（需自建） |
| **Agent 自我进化（项目级经验积累）** | AGENT_EVOLUTION.md | **无对应功能** | 🔴 **最高（ANTS 最核心差异化，无任何现有平台覆盖）** |
| 代码库索引（Tree-sitter / Python AST）| ANTS_LITE §4.4 | GitHub Copilot（私有）、部分 IDE 工具 | 🟡 中（有工具但无开放 API 集成） |
| MCP 工具集成 | DESIGN_REPORT §5.4 | 所有主流框架均支持 | 🟢 低（直接复用） |
| A2A 跨 Agent 协议 | DESIGN_REPORT §5.4 | Google ADK 原生，其他在适配 | 🟢 低（可用 ADK 或等待标准落地） |
| 自托管（非云锁定）| ANTS_LITE §1 | LangGraph、CrewAI、OpenAI Agents SDK、ADK | 🟢 低（开源框架均可自托管） |
| 轻量依赖（SQLite/文件 vs Redis/Kafka）| ANTS_LITE §1 | 需裁剪，但 LangGraph + SQLite Checkpointer 可行 | 🟡 中（需选型配置） |

### 关键差距：项目级经验积累

这是 ANTS 与所有现有框架最本质的区别：

```
现有框架的"记忆"：
  通用知识 + 对话历史 + 跨会话状态
  → 知道"Python 的最佳实践"
  → 不知道"这个项目用 Poetry 而不是 pip"

ANTS 经验库（Experience Library）：
  项目专属经验条目（trigger + solution + scope）
  → 知道"在这个项目里，pytest 失败通常是 PYTHONPATH 问题"
  → 知道"这个项目的数据库密码在 .env.local，不在 .env"
  → 知道"Reviewer 发现的 #47 类问题有成熟解法"
```

**没有任何现有平台（包括 Devin 2.0、GitHub Copilot、Google ADK）提供这种项目级经验积累能力。**
这也是为什么 Devin 在真实项目中仍然需要大量上下文注入的根本原因。

---

## 9. 结论：是否需要独立开发？

### 结论：**需要独立开发，但可以大量复用现有组件，减少 60–70% 的基础设施工作量**

#### 不需要从头开发的部分（直接复用）

| 模块 | 推荐复用方案 | 理由 |
|------|------------|------|
| **工作流编排引擎** | LangGraph（首选）或 Google ADK | 成熟、生产验证、原生 HITL、状态持久化 |
| **工具集成层** | MCP（标准协议 + 现有 MCP Server 生态） | 2000+ 工具已有现成 MCP Server |
| **跨 Agent 通信** | A2A 协议（跟随 Google ADK） | 开放标准，生态快速成熟 |
| **基础 Agent 抽象** | OpenAI Agents SDK（轻量）或 ADK | 成熟的 Agent/Tool/Handoff 原语 |
| **LLM 多提供商路由** | LiteLLM（已被 ADK/Agents SDK 集成）| 统一接口，模型无关 |
| **可观测性** | OpenTelemetry（LangSmith/Langfuse 等）| 标准化追踪，成熟生态 |

#### 必须独立开发的部分（ANTS 核心差异化）

| 模块 | 为什么必须自建 | 优先级 |
|------|-------------|-------|
| **经验库（Experience Library）** | 项目专属知识积累，无现成平台支持 | 🔴 最高（最核心竞争力） |
| **共享资料层（.ants/ 结构）** | 多 Agent 共享知识的标准化目录结构 | 🔴 高 |
| **代码库索引（codebase_index）** | 项目专属符号索引 + 增量更新 | 🟡 中（可复用 tree-sitter 工具） |
| **阶段边界 HITL 模型** | 现有 HITL 是"任意节点暂停"，不是"阶段完成后审批"的精确范式 | 🟡 中（在 LangGraph 基础上封装） |
| **Planner/Coder/Reviewer/Tester 角色定义** | 编码场景专属，现有框架无直接对应 | 🟡 中（在 Agent 抽象上层新增） |

#### 推荐技术栈组合

```
ANTS = LangGraph（编排）
     + OpenAI Agents SDK 或 ADK Agent 原语
     + MCP（工具集成）
     + A2A（跨 Agent 协议）
     + ANTS 自研经验库（核心差异化）
     + ANTS 自研代码库索引
     + ANTS 自研阶段边界 HITL Gateway
```

这个组合预计能将 ANTS 的开发工作量从"从零构建完整框架"降低到"在成熟基础上叠加差异化能力"，
**核心开发量集中在经验库、代码库索引和编码 Agent 角色定义三个模块**，
而编排/通信/可观测等基础设施可直接复用开源框架。

---

## 10. 参考资料

| # | 来源 | 链接 |
|---|------|------|
| [ref-1] | OpenAI Agents SDK 官方文档 | https://openai.github.io/openai-agents-python/ |
| [ref-2] | OpenAI Agents SDK GitHub | https://github.com/openai/openai-agents-python |
| [ref-3] | Google ADK 官方博客（Cloud NEXT 2025） | https://developers.googleblog.com/en/agent-development-kit-easy-to-build-multi-agent-applications/ |
| [ref-4] | Google ADK 多 Agent 文档 | https://google.github.io/adk-docs/agents/multi-agents/ |
| [ref-5] | LangGraph GitHub | https://github.com/langchain-ai/langgraph |
| [ref-6] | CrewAI GitHub | https://github.com/crewAIInc/crewAI |
| [ref-7] | A2A 协议官方发布博客 | https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/ |
| [ref-8] | A2A 协议规范 | https://a2a-protocol.org/latest/ |
| [ref-9] | Microsoft Azure Agent Factory（MCP + A2A） | https://azure.microsoft.com/en-us/blog/agent-factory-connecting-agents-apps-and-data-with-new-open-standards-like-mcp-and-a2a/ |
| [ref-10] | GitHub Copilot Coding Agent 发布 | https://github.com/newsroom/press-releases/coding-agent-for-github-copilot |
| [ref-11] | Devin 2025 年度绩效报告 | https://cognition.ai/blog/devin-annual-performance-review-2025 |
| [ref-12] | Devin AI 官网 | https://devin.ai/ |
| [ref-13] | AI Agent 框架 2026 全景（AI Makers Blog） | https://www.aimakers.co/blog/ai-agents-landscape-2026/ |
| [ref-14] | Top 12 AI Agent 框架 2026 | https://moltbook-ai.com/posts/agent-frameworks-2026 |
| [ref-15] | Langfuse：开源 AI Agent 框架对比 | https://langfuse.com/blog/2025-03-19-ai-agent-comparison |
| [ref-16] | LangGraph 生产功能详解 | https://byteiota.com/langgraph-for-ai-agents-build-production-ready-workflows/ |
| [ref-17] | MCP vs A2A 企业实践 | https://dzone.com/articles/model-context-protocol-agent2agent-practical |
| [ref-18] | Dify vs n8n vs Flowise 对比 | https://blog.api2o.com/en/blog/2025/03-05-lowcode-platform-compare-dify-n8n-flowise |
| [ref-19] | Developer Guide: OpenAI Agents SDK vs Google ADK | https://iamulya.one/posts/a-developer-guide-to-ai-agents-openai-agents-sdk-vs-google-adk/ |
| [ref-20] | A2A, MCP, ADK 角色澄清 | https://discuss.google.dev/t/a2a-mcp-and-adk-clarifying-their-roles-in-the-ai-ecosystem/190226 |
