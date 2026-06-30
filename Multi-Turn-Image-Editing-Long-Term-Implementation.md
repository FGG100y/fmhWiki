# 多轮修图长期产品实现参考

> 面向“输入一句话生成图片，并支持后续多轮自然语言修图”的长期产品方案。

### 核心结论

多轮修图产品的正确架构不是“自由聊天式多 Agent”，也不是“完全确定性流水线”，而是**确定性工作流 + 受控 Agent 步骤 + 显式状态管理**的混合架构。

#### 三种架构范式对比

| 范式 | 特点 | 适合场景 | 多轮修图适用性 |
|---|---|---|---|
| 自由聊天式多 Agent | LLM 控制所有流程，自主决定每一步 | 开放式探索、创意发散 | ❌ 不适合：无法保证安全检查、模型路由、质量评估必定执行 |
| 完全确定性流水线 | 无 LLM，纯规则/模板 | 固定格式的批量处理 | ❌ 不适合：无法理解自然语言意图 |
| **确定性工作流 + 受控 Agent 步骤** | 工作流引擎控制流程，LLM 仅在特定节点做推理 | 有状态的、需要理解自然语言的生产系统 | ✅ 推荐：可预测、可审计、可回退 |

#### 为什么“自由聊天式多 Agent”不适合多轮修图

1. **无法保证执行顺序**：安全检查可能被 LLM 跳过，模型路由可能被 LLM “创造性”地绕过。
2. **无法保证成本可控**：每步都有规划开销，token 消耗约为确定性工作流的 20 倍。
3. **无法保证可审计**：Agent 轨迹难以结构化，无法满足合规和审计需求。
4. **无法保证版本管理**：自由聊天没有版本树概念，无法支持撤销/重做/分支。

---

#### 产业级证据：业界共识的形成（2024.12 — 2026.06）

**Anthropic（2024.12）— 最权威的架构指导**
来源：https://www.anthropic.com/engineering/building-effective-agents

> “Consistently, the most successful implementations were using simple, composable patterns. They weren’t using complex frameworks or specialized libraries.”

Anthropic 明确区分 Workflows 与 Agents：

> “**Workflows** are systems where LLMs and tools are orchestrated through predefined code paths. **Agents** are systems where LLMs dynamically direct their own processes and tool usage.”

核心建议：

> “When more complexity is warranted, **workflows offer predictability and consistency for well-defined tasks**, whereas agents are the better option when flexibility and model-driven decision-making are needed at scale.”

**Metacto（2026.06）— 生产故障案例：state machine 取代 prompt-loop**
来源：https://www.metacto.com/blogs/ai-agent-state-machine-design

一家 SaaS 公司用 prompt-loop（LLM + system prompt + tool list + while-loop）做 onboarding agent，生产环境表现：

> “Sometimes the agent skipped sending the welcome email. Sometimes it invited teammates twice... One out of every twenty runs ended in a state the team could not explain.”

根因诊断：

> “**The bug was not the prompt. The bug was that there was no defined workflow at all.** The agent was a stateless loop being asked to remember what it had done by re-reading its own conversation history.”

> “Conversation history is not state. It is a transcript.”

> “**The fix was to delete the loop and model the workflow as an explicit state machine**... Three weeks of incidents stopped overnight.”

**Zylos Research（2026.04）— 编排模式的演进轨迹**
来源：https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/

> “In 2024 the answer was often ‘just chain together some LLM calls.’ By 2025 that approach had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs.”

产业共识结论：

> “**Hybrid approaches — deterministic outer structure, dynamic inner loops — dominate production deployments.**”

> “Start static, add dynamism incrementally — dynamic topology is powerful but expensive to debug. Begin with a fixed workflow, identify where flexibility is genuinely needed, and introduce dynamic planning only there.”

**Towards Data Science（2025.06）— 生产不奖励聪明，奖励韧性**
来源：https://towardsdatascience.com/a-developers-guide-to-building-scalable-ai-workflows-vs-agents/

> “**Most real-world AI systems are a mix** — and many of them lean heavily on workflows because **production doesn’t reward cleverness. It rewards resilience.**”

> “**Workflows are deterministic. That means they’re traceable.** Which means if something goes wrong, you can show exactly what happened — step-by-step — with logs, fallbacks, and structured output.”

---

#### 架构性缺陷：为什么不能靠 prompt engineering 补救

Metacto 指出 prompt-loop 系统的**三种必然失败模式**（不是 prompt 问题，是架构问题）：

| 失败模式 | 表现 | 根因 |
|---------|------|------|
| **重复已完成工作** | LLM 读自己的对话历史，搞混了什么已做，再做一次 | 对话历史不是状态，对话是一份“笔录”，不是可查询的事实来源 |
| **跳过必做步骤** | 20 轮前的成功 tool call 让模型认为“整个事情做完了” | 模型无法区分“某个步骤曾被执行过”和“本次任务的步骤已完成” |
| **丢失执行计划** | 模型开始时规划了 7 步，执行 3 步后突然跳到第 7 步 | 规划信息存在对话上下文窗口中，被后续 token 覆盖或遗忘 |

核心诊断：

> “**You cannot prompt your way around statelessness.**”

> “These are not prompt-engineering problems. **They require structural solutions.**”

这就是为什么多轮修图产品需要**显式状态管理**：`turn_id`、`parent_turn_id`、`input_image_id`、`output_image_id` 必须作为一等公民存储在结构化数据库中，而非依赖于对话上下文中模糊的 token 记忆。

---

#### 学术论文验证：所有多轮修图论文均使用受控 Agent 架构

无一例外，2025-2026 年发表的 multi-turn image editing 论文都是**规划-执行-反思**的受控架构，而非自由聊天式多 Agent：

| 论文 | 架构范式 | 核心机制 |
|------|---------|---------|
| **IMAGAgent**（2026.03） | Plan-Execute-Reflect | 约束感知规划 + 多专家协作反思 — **结构化 pipeline，非自由式** |
| **Agent Banana**（2026.02） | Hierarchical Planner-Executor | Context Folding + Image Layer Decomposition — **层级规划，非自由式** |
| **RefineEdit-Agent**（2025.08） | Parser → Planner → Tool Scheduler | **确定性规划管线包裹工具执行** |
| **CAMEO**（2026.04） | Orchestration → Utility → Regulation 三层 | Quality Critic + Refinement Editor — **层级受控** |
| **Banana100**（CVPR 2026 Workshop） | — | 特别指出“多轮编辑中的迭代质量退化” — **需要确定性 checkpoint 和验证** |

学术界自称 “Agent” 的系统，实质结构都是 Planner + Executor + Reflector 的受控管线，没有一个让多个 LLM “自由讨论”来决定每一步。

---

#### 反例：自由式 Agent 在哪些场景有效（及与修图的本质差异）

| 场景 | 为什么适合自由式 Agent | 与多轮修图的差异 |
|------|---------------------|----------------|
| **编程 Agent**（SWE-bench） | 需要的文件修改不可预测，路径无法预定 | 修图的操作空间可枚举：生成、编辑、局部 inpainting、风格迁移、超分 |
| **客服对话** | 对话路径天然开放，无法预知用户下一句话 | 修图的每轮是独立的“编辑任务”，有明确的输入（图片）和输出（修改后图片） |
| **研究探索** | 无法预知搜索路径，需要自主规划 | 修图不需要 agent 自行探索“未知路径” |

多轮修图是一个**有版本的状态转换序列**：每次操作的结果必须是可追溯的（哪个版本、用了什么模型、什么参数）。安全检查必须执行。模型路由应该可审计。这是确定性工作流天然胜任的领域——Anthropic 也明确建议**对 well-defined tasks 使用 workflows**。

---

#### 当前实现验证：`image_editor/` 架构对齐

`image_editor/workflow.py` 的 LangGraph StateGraph 是一个**固定 DAG 拓扑**，不是 Agent Loop：

```
load_session → safety_check → classify_intent
                                  ├─ version_op → handle_version_op → END
                                  ├─ image_op → rewrite_prompt → select_tool
                                  │              → run_image_tool → visual_qa
                                  │                  ├─ pass  → persist_turn → END
                                  │                  ├─ retry → rewrite_prompt (max 2次)
                                  │                  └─ fail  → persist_turn → END
                                  └─ fail → fail → END
```

- 唯一的“循环”是 `retry_count < 2` 的受控重试，不是开放式的 Agent 循环
- 条件分支由纯函数 `route_by_intent()` 和 `route_by_qa()` 控制，不存在 LLM 自主决策下一步
- 每个 LLM 调用被限定在单一节点内，输出固定 JSON schema，由 Pydantic 强校验
- State 是 25 个命名字段的 `TypedDict`，通过 graph 单向流动
- 版本树通过 `parent_turn_id` 实现（`storage.py` 中的 `undo()` / `redo()` / `switch_current_turn()`）

#### 为什么需要 Agent 步骤

图像编辑需要理解自然语言意图（“把背景换成雪山，人物不要变”），这需要 LLM 的推理能力。但 LLM 只应在特定节点被调用：
- **意图分类**：理解用户要做什么
- **Prompt 改写**：将口语化指令转为结构化编辑指令
- **质量评估**：检查输出是否满足用户要求

#### 本方案的架构原则

```text
确定性工作流引擎（LangGraph StateGraph）
  ↓ 控制流程
受控 Agent 步骤（LLM 在特定节点做推理）
  ↓ + 版本树管理（parent_turn_id）
  ↓ + 多模型工具层（Gemini / GPT Image / ComfyUI）
  ↓ + 质量评估闭环（Visual QA + 自动重试）
```

---

## 一、产品目标

### 1.1 核心体验

- 用户输入一句话生成初始图片。
- 用户继续用自然语言修改当前图片。
- 支持撤销、重做、回到任意历史版本继续编辑。
- 支持局部修改、参考图、风格迁移、背景替换、生成变体、高清导出。
- 系统尽量保持主体一致性、构图稳定性和用户明确要求不变的区域。

### 1.2 关键判断

多轮修图的核心不是“多 Agent 互相讨论”，而是可靠管理以下状态：

- 当前图片是哪一张。
- 本轮基于哪个历史版本生成。
- 用户到底要改哪里、保留哪里。
- 使用了哪个模型、参数、mask、参考图。
- 结果是否满足用户要求。
- 用户能否回退、分支、对比和继续编辑。

---

## 二、总体架构

```text
Frontend
  ↓
API Gateway / Backend API
  ↓
Session / Project Service
  ↓
Job Queue
  ↓
LangGraph Orchestrator
  ↓
Agent Nodes
  ↓
Image Tool Layer
  ↓
Gemini / OpenAI / Flux / Stable Diffusion + ControlNet/IP-Adapter/LoRA（条件控制技术） / ComfyUI（工作流编排）/ Upscaler
  ↓
Postgres + Object Storage + Observability
```

### 2.1 模块职责

| 模块 | 职责 |
|---|---|
| Frontend | 聊天输入、画布、版本树、局部圈选、参考图上传、结果对比 |
| API Gateway | 鉴权、限流、请求校验、创建任务 |
| Session Service | 管理项目、会话、当前版本、历史版本 |
| Job Queue | 承载长耗时图片生成任务，支持重试和取消 |
| LangGraph Orchestrator | 以状态机方式编排意图识别、prompt 改写、模型路由、生成、质检 |
| Agent Nodes | 负责结构化决策，而不是自由对话 |
| Image Tool Layer | 统一封装不同图像模型和 ComfyUI 工作流 |
| Asset Store | 保存原图、结果图、mask、参考图、缩略图 |
| Observability | 记录成本、耗时、失败率、模型效果和用户反馈 |

---

## 三、框架选型

### 3.1 推荐选择

长期产品优先选择 `LangGraph` 作为编排层。

原因：

- 多轮修图天然是有状态流程。
- 需要 checkpoint、重试、回放、分支、人工介入。
- 需要明确控制每个节点，而不是让 Agent 自由循环。
- 后续可接入多模型、多工具和复杂质量评估。

### 3.2 框架对比

| 框架 | 适合场景 | 是否推荐作为主编排 |
|---|---|---|
| LangGraph | 生产级有状态工作流、版本管理、复杂路由、持久化执行 | 推荐 |
| Deep Agents | 复杂长周期任务、需要内置规划/子 agent/文件系统 | 可用于子任务委托 |
| OpenAI Agents SDK | OpenAI 生态内快速 MVP，简单 handoff | 可用于早期 MVP |
| CrewAI | 角色化多 agent 编排、结构化业务流程、快速原型 | 可用于特定子场景 |
| Microsoft Agent Framework | Microsoft 生态、AutoGen + Semantic Kernel 统一继承者 | Microsoft 技术栈时考虑 |
| ComfyUI | 可控图像工作流编排，支持 Flux/SD + ControlNet（条件控制）/ IP-Adapter（图像提示）/ LoRA（轻量微调） | 作为工具层接入 |

### 3.3 推荐组合

```text
LangGraph
+
Postgres
+
S3 / R2 / OSS
+
Redis Queue / Celery / Dramatiq
+
Gemini 3.1 Flash Image / Gemini 3 Pro Image（多轮编辑、文生图）
+
GPT Image 2 / GPT Image 1.5（备选图像生成/编辑）
+
ComfyUI / Flux / SD 作为高级编辑后端（局部 inpainting、ControlNet 条件控制）
```

### 3.4 与 Deep Agents 的关系与选择

> 注：Deep Agents（`deepagents`）是 LangChain 官方的 agent harness，构建在 LangGraph 之上。它本身就是一个 `CompiledStateGraph`，可以调用所有 LangGraph 接口（checkpointer、interrupt、streaming 等）。三者是分层关系：LangGraph → LangChain → Deep Agents，而非竞争关系。

核心问题不是"用 Deep Agents 还是用 LangGraph"，而是**选择哪种架构范式**：

- **Agent Loop（Deep Agents 默认范式）**：LLM 在循环中自主决定每一步做什么
- **State Machine（本文方案）**：预定义节点按固定顺序执行，LLM 仅在特定节点内做决策

两者都基于 LangGraph，但使用方式不同。

#### 3.4.1 核心范式对比：Agent Loop vs State Machine

**Deep Agents 的默认范式：Agent Loop**

```text
用户输入："把背景换成雪山，人物不要变"
  ↓
Deep Agent 收到用户消息
  ↓
LLM 自主决定下一步做什么（规划）
  ↓
LLM 决定调用哪个工具（可能调用 search、write_file、task 等）
  ↓
LLM 根据工具返回结果再决定下一步
  ↓
... 循环直到 LLM 认为任务完成 ...
  ↓
返回结果
```

虽然 Deep Agents 底层是 LangGraph，但它的**默认行为**是让 LLM 在每个步骤自主决策。你可以通过自定义工具和 prompt 来约束 LLM 的行为，但这等于在 Deep Agents 之上重新定义工作流。

**本文方案的范式：State Machine**

```text
用户输入："把背景换成雪山，人物不要变"
  ↓
load_session（加载当前图片和历史状态）
  ↓
safety_check（安全检查 — 必定执行）
  ↓
classify_intent（意图分类 — 必定执行）
  ↓
rewrite_prompt（prompt 改写 — 必定执行）
  ↓
select_tool（模型路由 — 必定执行，使用确定性规则）
  ↓
run_image_tool（调用图像模型 — 必定执行）
  ↓
visual_qa（质量检查 — 必定执行）
  ↓
persist_turn（持久化 — 必定执行）
  ↓
返回结果
```

**关键区别**：虽然两者都能用 LangGraph 的 checkpointer、interrupt 等功能，但**流程控制权**不同：
- Deep Agents：LLM 决定何时检查安全、何时选择模型、何时做 QA
- 本文方案：工作流引擎决定这些，LLM 只在需要时被调用

#### 3.4.1.1 执行模式与时延设计

上述流程图展示的是逻辑执行顺序，实际部署时需要考虑用户等待时长。各步骤耗时差异很大：

| 步骤 | 预估耗时 | 类型 | 说明 |
|---|---|---|---|
| load_session | <100ms | 快速 | 从数据库读取状态 |
| safety_check | 100-500ms | 快速 | LLM 调用或规则匹配 |
| classify_intent | 200-1000ms | 快速 | LLM 调用 |
| rewrite_prompt | 500-2000ms | 快速 | LLM 调用 |
| select_tool | <100ms | 快速 | 确定性规则，无需 LLM |
| run_image_tool | **5-60s** | **慢速** | 图像模型调用，主要瓶颈 |
| visual_qa | 1-3s | 中等 | LLM 调用（多模态） |
| persist_turn | <100ms | 快速 | 数据库写入 |

**两阶段执行模型**：

```text
【同步阶段 — 用户等待，<3s】
  load_session → safety_check → classify_intent → rewrite_prompt → select_tool
      ↓
  返回 job_id + turn_id，状态为 "processing"
      ↓
【异步阶段 — 后台执行，5-60s】
  run_image_tool → visual_qa → persist_turn
      ↓
  通过 WebSocket/SSE 推送结果
```

**设计要点**：

1. **早期终止**：`safety_check` 失败时直接返回错误，不进入异步队列，避免浪费图像生成资源。
2. **流式反馈**：异步阶段每步完成后推送状态更新（`queued → running → qa_checking → succeeded`），前端展示进度条。
3. **超时控制**：`run_image_tool` 设置超时（如 60s），超时自动降级到备选模型（如从 Gemini 3 Pro 降级到 Gemini 3.1 Flash）。
4. **重试隔离**：重试时只重新执行 `run_image_tool → visual_qa`，不需要重新执行同步阶段的步骤。

**前端用户体验**：

```text
用户发送请求
  ↓
立即显示："正在分析您的请求..."（同步阶段 <3s）
  ↓
显示："正在生成图片..." + 进度条（异步阶段）
  ↓
每 5s 推送进度："模型调用中..." → "质量检查中..." → "完成"
  ↓
显示结果图
```

#### 3.4.2 具体场景对比

**场景 1：用户说"把背景换成雪山，人物不要变"**

| 环节 | Deep Agents 默认行为 | 本文方案行为 |
|---|---|---|
| 意图理解 | LLM 自行理解，可能误解为"生成一张雪山图片" | `classify_intent` 节点明确输出 `intent=background_replace, edit_scope=background` |
| Prompt 改写 | LLM 可能直接用用户原始 prompt | `rewrite_prompt` 节点输出结构化的 positive/negative prompt 和 preservation constraints |
| 模型选择 | LLM 自行决定用哪个模型（可能选错） | `select_tool` 节点用确定性规则选择 `gemini-3.1-flash-image` |
| 安全检查 | LLM 可能跳过或忘记执行 | `safety_check` 节点**必定执行**，在工作流最前面 |
| 质量检查 | LLM 可能直接返回结果 | `visual_qa` 节点**必定执行**，检查主体是否被修改 |
| 结果持久化 | 保存在消息历史中，无结构化版本信息 | 保存到 `turns` 表，包含 `parent_turn_id`、`input_image_id`、`output_image_id`、`model_params` |

> 注：Deep Agents 可以通过自定义工具和 prompt 来强制执行这些步骤，但这等于重新定义了工作流——你本质上是在 Deep Agents 之上构建了一个状态机。

**场景 2：用户说"回到第 2 版，改成横版"**

| 环节 | Deep Agents 默认行为 | 本文方案行为 |
|---|---|---|
| 版本回退 | 无内置版本树概念，需要自己实现 | `handle_version_op` 节点原生支持 undo/redo/switch |
| 版本切换 | 需要从消息历史中"找到"之前的图片 | 直接从 `turns` 表查询 `parent_turn_id` 链 |
| 参数继承 | 无结构化参数，需要从历史消息中提取 | 直接从 `turns` 表读取上一版的 `model_params` |

**场景 3：生成失败需要重试**

| 环节 | Deep Agents 默认行为 | 本文方案行为 |
|---|---|---|
| 重试策略 | LLM 自行决定是否重试、如何重试 | `route_by_qa` 条件边控制：`pass → persist_turn`，`retry → rewrite_prompt` |
| 重试次数 | 无限制，LLM 可能无限重试 | `retry_count` 字段控制，最多重试 1-2 次 |
| 降级策略 | LLM 可能尝试完全不同的方法 | 从 `rewrite_prompt` 重新开始，调整 prompt 和参数 |

#### 3.4.3 详细对比表

| 维度 | Deep Agents（Agent Loop 范式） | 本文方案（State Machine 范式） |
|---|---|---|
| 底层框架 | LangGraph（`CompiledStateGraph`） | LangGraph（`StateGraph`） |
| 流程控制 | LLM 在循环中自主决定每一步 | 预定义节点按固定顺序执行，LLM 仅在特定节点内做决策 |
| 安全检查 | 依赖 LLM 记忆，可能被跳过 | 工作流节点，必定执行 |
| 模型路由 | LLM 自行选择模型，可能选错 | 确定性规则，按意图/编辑类型/约束选择 |
| Token 消耗 | 高（约 20x）：每步都需要 LLM 规划 | 低：只有 rewrite_prompt 和 visual_qa 需要 LLM |
| 历史管理 | 消息上下文 + 虚拟文件系统，无版本概念 | 一等公民版本树（`parent_turn_id`），支持任意版本切换 |
| 回退/分支 | 可用 LangGraph interrupt 实现，但无内置版本树 | 架构原生支持 undo/redo/switch/branch |
| 可观测性 | 偏 Agent 执行日志（tool calls, planning steps） | 面向产品指标：turn、job、model call 全链路，结构化日志 |
| 质量闭环 | 常见做法是"失败再让 Agent 试"，无结构化 QA | 显式 Visual QA 节点 + 可控重试策略（最多 N 次） |
| 适配多轮修图 | 能做，但 `DeepAgentState` 默认只有 `todos` 和 `files`，缺少图像专用字段 | 天然匹配：`input_image_id`、`output_image_id`、`mask_image_id`、`model_params`、`qa_score` |
| 降级策略 | LLM 自行决定降级路径 | 确定性 fallback：主模型不可用 → 备选模型 → ComfyUI |
| 成本控制 | 难以预测：LLM 可能做大量无关规划 | 可预测：每个 turn 的 LLM 调用次数固定（rewrite + QA） |
| 审计合规 | Agent 轨迹难以结构化 | turn / job / model call 三层记录，满足审计需求 |

#### 3.4.4 用 Deep Agents 实现多轮修图的代价

Deep Agents 底层是 LangGraph，理论上可以实现相同功能。但需要：

1. **重新定义工作流**：通过自定义工具和 prompt 约束 LLM 的行为，让它按固定顺序执行。但这等于在 Deep Agents 之上重新构建了一个状态机，增加了复杂度。

2. **扩展状态结构**：通过 middleware 扩展 `DeepAgentState`，添加 `input_image_id`、`output_image_id`、`mask_image_id`、`model_params`、`qa_score` 等字段。Deep Agents 的论坛有用户反馈 `context_schema` 的自定义字段无法直接在 `runtime.state` 中访问，需要额外 workaround。

3. **构建版本树**（详见 [5.2 版本树设计](#52-版本树设计)）：Deep Agents 的数据模型是 `messages`（线状消息历史）+ `files`（平铺文件系统），没有 `parent_turn_id` 概念。要实现撤销/重做/分支/版本切换，需要自己构建完整的版本树系统——这个工作量远超 Deep Agents 提供的现成能力。

4. **结构化日志**：Deep Agents 的事件流是面向 agent 执行的（tool-call, tool-result, todos-changed），不是面向产品指标的。需要额外的 observability 层来聚合 turn/job/model call 级别的指标。

5. **成本控制**：Deep Agents 的 token 消耗约为直接使用 LangGraph 的 20 倍（因为每步都有规划开销）。对于高频修图场景，成本差异显著。

**核心问题**：如果需要做以上所有定制，那 Deep Agents 提供的内置能力（规划、文件系统、子 agent）反而成了需要绕过的障碍。不如直接用 LangGraph 构建专用工作流。

#### 3.4.5 更合理的用法：分层组合

Deep Agents 并非无用，而是应该用在它擅长的地方：

- **在线主流程**：使用本文的确定性工作流承接生产流量（可预测、低成本、可审计）。
- **离线任务**：把 Deep Agents 用在"复杂 prompt/工具策略搜索"、"离线策略优化"或"需要自主规划的子任务"（如：分析用户历史偏好、生成个性化模板）。
- **混合架构**：用 Deep Agents 作为子 agent 处理特定子任务（如：分析用户意图、生成创意方案），主流程仍用确定性工作流编排。

---

## 四、核心工作流

```text
Start
  ↓
Load Session State
  ↓
Safety Check
  ↓
Classify Intent
  ↓
Version Operation? ── yes → Undo / Redo / Switch Version → End
  ↓ no
Analyze Edit Request
  ↓
Rewrite Prompt
  ↓
Select Image Tool
  ↓
Run Image Tool
  ↓
Visual QA
  ↓
Retryable Failure? ── yes → Rewrite Prompt / Adjust Params → Run Image Tool
  ↓ no
Persist Turn
  ↓
Return Result
```

### 4.1 典型用户链路

```text
Turn 0: 生成一张赛博朋克风格的猫咪海报
Turn 1: 把背景换成雨夜街道，猫不要变
Turn 2: 加一点霓虹灯反光
Turn 3: 生成三个不同构图版本
Turn 4: 回到 Turn 2，改成横版 16:9
```

系统需要把这条链路存成版本树，而不是只存聊天记录。

---

## 五、数据模型

### 5.1 核心表

```sql
users
- id
- email
- created_at

projects
- id
- user_id
- title
- created_at
- updated_at

sessions
- id
- project_id
- current_turn_id
- created_at
- updated_at

turns
- id
- session_id
- parent_turn_id
- user_instruction
- normalized_intent
- edit_scope
- rewritten_prompt
- negative_prompt
- preservation_constraints
- input_image_id
- output_image_id
- mask_image_id
- reference_image_ids
- model_provider
- model_name
- model_params
- status
- qa_score
- qa_result
- error_message
- created_at

images
- id
- user_id
- storage_url
- thumbnail_url
- width
- height
- mime_type
- file_size
- perceptual_hash
- metadata
- created_at

jobs
- id
- session_id
- turn_id
- status
- progress
- error_message
- started_at
- finished_at
```

### 5.2 版本树设计

#### 5.2.1 什么是版本树

版本树是记录用户编辑操作之间派生关系的数据结构。在多轮修图中，每次用户说"改一下背景"或"回到上一版"，系统都生成一个新的 turn。这个新 turn 从哪个版本派生而来，就记录为 `parent_turn_id`。

```text
# 最小示例：线性编辑
turn_0（初始生成）
  └── turn_1（改背景）
        └── turn_2（加滤镜）

# 实际示例：分支编辑
turn_0（初始生成：一只猫）
  └── turn_1（背景换成雪山）
        ├── turn_2a（加落日色调）
        │     └── turn_3a（裁成横版）
        └── turn_2b（改成 16:9）
              └── turn_3b（加文字标题）
```

每个 turn 记录一条记录：

| turn_id | parent_turn_id | input_image_id | output_image_id | user_instruction |
|---|---|---|---|---|
| turn_0 | null | null | img_0 | 生成一只猫 |
| turn_1 | turn_0 | img_0 | img_1 | 背景换成雪山 |
| turn_2a | turn_1 | img_1 | img_2a | 加落日色调 |
| turn_2b | turn_1 | img_1 | img_2b | 改成 16:9 |
| turn_3a | turn_2a | img_2a | img_3a | 裁成横版 |
| turn_3b | turn_2b | img_2b | img_3b | 加文字标题 |

#### 5.2.2 版本树支持的操作

版本树的五个核心操作：

| 操作 | 含义 | 实现方式 |
|---|---|---|
| **撤销（Undo）** | 回到上一版 | 将 `session.current_turn_id` 设置为当前 turn 的 `parent_turn_id` |
| **重做（Redo）** | 取消撤销 | 将 `session.current_turn_id` 设置为最近一次 undo 前的 turn |
| **切换到任意版本** | 从某个历史版本继续编辑 | 将 `session.current_turn_id` 设置为目标 turn_id |
| **分支（Branch）** | 从一个版本生成多个不同变体 | 创建新 turn，设置 `parent_turn_id = 当前 turn_id` |
| **对比** | 并排查看两个版本 | 查询两个 turn 的 `output_image_id`，返回两张图片 URL |

#### 5.2.3 版本树 vs 消息历史

多轮修图产品中，版本树和聊天消息历史是两种不同的数据结构：

| 维度 | 版本树（`turns` 表） | 消息历史（`messages`） |
|---|---|---|
| 数据结构 | 树状（有 parent_turn_id） | 线状（按时间排列） |
| 核心字段 | input_image_id, output_image_id, mask_image_id, parent_turn_id, model_name, model_params | role, content, timestamp |
| 撤销实现 | 设置 `current_turn_id` 回到父版本 | 需要找到"上一张图片在哪条消息里"，不可靠 |
| 分支支持 | 多个 turn 指向同一个 parent | 消息历史不支持分支 |
| 对比 | 查询两个 turn 的 output | 需要在消息中搜索图片 URL |
| 参数追踪 | 每个 turn 记录 model_name, model_params | 参数散落在消息内容中 |

#### 5.2.4 为什么 Deep Agents 没有版本树

Deep Agents 的数据模型是基于**对话历史 + 虚拟文件系统**的：

```python
# DeepAgentsState 的核心结构
DeepAgentState = {
    "messages": [...],          # 对话历史（线状）
    "todos": [...],             # 任务列表
    "files": {                  # 虚拟文件系统（平铺，非树状）
        "/output/image_1.png": FileData(...),
        "/output/image_2.png": FileData(...),
    }
}
```

Deep Agents 的三个设计局限导致无法原生支持版本树：

1. **消息历史是线状的**：没有 `parent_turn_id` 概念，无法表示"turn_2a 和 turn_2b 都从 turn_1 派生"的分支关系。消息历史只能记录"用户说了什么"→"AI 回复了什么"，无法记录"这个回复基于哪个版本的图片"。

2. **文件系统是平铺的**：Deep Agents 的虚拟文件系统是一个扁平的文件名→文件内容的映射。没有层级关系，没有派生链路。你可以在文件名里编码版本关系（如 `turn_0/turn_1/turn_2a.png`），但这需要自己实现路径解析和派生链追踪。

3. **状态中没有图像元数据**：`DeepAgentState` 只有 `todos` 和 `files`，没有 `input_image_id`、`output_image_id`、`model_name`、`model_params` 等字段。要添加这些需要通过 middleware 扩展 state schema（已有用户反馈 `context_schema` 的自定义字段无法在 `runtime.state` 中直接访问）。

#### 5.2.5 为什么本方案可以有

本方案在 LangGraph 之上设计了一个**显式的版本树数据模型**，不依赖任何框架的内置结构：

```python
# 本方案的 state：包含版本树所需的所有字段
class ImageEditState(TypedDict):
    # ... 其他字段 ...
    current_turn_id: str | None    # 当前激活的版本
    current_image_id: str | None   # 当前图片
    parent_turn_id: str | None     # 本轮基于哪个版本
```

```sql
-- turns 表：版本树的数据库层面实现
CREATE TABLE turns (
    id PRIMARY KEY,
    session_id,
    parent_turn_id,          -- 版本树核心：指向父版本
    input_image_id,           -- 输入图片（从哪里开始编辑）
    output_image_id,          -- 输出图片（编辑后的结果）
    mask_image_id,            -- mask（局部编辑区域）
    model_name,               -- 使用了哪个模型
    model_params,             -- 模型参数
    qa_score,                 -- 质量评分
    user_instruction,         -- 用户原始指令
    rewritten_prompt,         -- 改写后的 prompt
    ...
);
```

实现关键不在于框架级别支持，而在于：

1. **在数据模型中显式包含 `parent_turn_id`**：每个 turn 都知道自己从谁派生而来。
2. **`session.current_turn_id` 作为工作指针**：始终指向用户当前正在看/编辑的版本。
3. **数据库层面即可实现版本树操作**：撤销 = `UPDATE session SET current_turn_id = turns.parent_turn_id`，切换 = `UPDATE session SET current_turn_id = target_id`。

因为这是基于LangGraph的**自定义state**和**自定义数据模型**，而不是 Deep Agents 的框架内置结构。Deep Agents 并非做不到，而是如果要实现版本树，所有的派生关系、切换逻辑、分支管理都需要在 Deep Agents 的框架之上从头构建——最终得到的仍然是一套自定义的版本管理系统。

---

## 六、LangGraph 状态设计

```python
class ImageEditState(TypedDict):
    user_id: str
    project_id: str
    session_id: str
    turn_id: str

    user_instruction: str
    current_turn_id: str | None
    current_image_id: str | None
    reference_image_ids: list[str]
    mask_image_id: str | None

    intent: str | None
    edit_scope: str | None
    operation: str | None
    constraints: list[str]
    rewritten_prompt: str | None
    negative_prompt: str | None

    selected_tool: str | None
    model_provider: str | None
    model_name: str | None
    model_params: dict

    output_image_id: str | None
    qa_result: dict | None
    retry_count: int
    error: str | None
```

### 6.1 节点设计

| 节点 | 输入 | 输出 |
|---|---|---|
| load_session | session_id, current_turn_id | 当前图片、历史摘要、用户偏好 |
| safety_check | 用户指令、图片元数据 | allow / reject / needs_review |
| classify_intent | 用户指令、当前状态 | intent、operation、edit_scope |
| handle_version_op | undo / redo / switch 指令 | 新 current_turn_id |
| rewrite_prompt | 用户指令、约束、当前图片描述 | positive_prompt、negative_prompt、preserve constraints |
| select_tool | intent、mask、参考图、质量档位 | tool、model、params、fallback |
| run_image_tool | 图片、prompt、参数 | output_image_id |
| visual_qa | 原图、结果图、用户要求 | pass、score、issues、retry_suggestion |
| persist_turn | 状态、结果、QA | turn 记录、session current_turn_id |

### 6.2 工作流伪代码

```python
workflow = StateGraph(ImageEditState)

workflow.add_node("load_session", load_session)
workflow.add_node("safety_check", safety_check)
workflow.add_node("classify_intent", classify_intent)
workflow.add_node("handle_version_op", handle_version_op)
workflow.add_node("rewrite_prompt", rewrite_prompt)
workflow.add_node("select_tool", select_tool)
workflow.add_node("run_image_tool", run_image_tool)
workflow.add_node("visual_qa", visual_qa)
workflow.add_node("persist_turn", persist_turn)
workflow.add_node("fail", fail)

workflow.set_entry_point("load_session")
workflow.add_edge("load_session", "safety_check")
workflow.add_edge("safety_check", "classify_intent")

workflow.add_conditional_edges(
    "classify_intent",
    route_by_intent,
    {
        "version_op": "handle_version_op",
        "image_op": "rewrite_prompt",
        "reject": "fail",
    },
)

workflow.add_edge("rewrite_prompt", "select_tool")
workflow.add_edge("select_tool", "run_image_tool")
workflow.add_edge("run_image_tool", "visual_qa")

workflow.add_conditional_edges(
    "visual_qa",
    route_by_qa,
    {
        "pass": "persist_turn",
        "retry": "rewrite_prompt",
        "fail": "persist_turn",
    },
)

workflow.add_edge("handle_version_op", END)
workflow.add_edge("persist_turn", END)
workflow.add_edge("fail", END)
```

---

## 七、Agent 节点设计

### 7.1 Intent Agent

职责：把用户自然语言转成结构化意图。

示例输入：

```text
用户：把背景换成雪山，人物不要变
当前是否有图：true
是否有 mask：false
是否有参考图：false
```

示例输出：

```json
{
  "intent": "edit_image",
  "operation": "background_replacement",
  "edit_scope": "background",
  "requires_mask": false,
  "preserve": ["main subject identity", "pose", "composition"],
  "risk": "subject_identity_drift"
}
```

常见 intent：

| intent | 含义 |
|---|---|
| generate_image | 首次文生图 |
| edit_image | 基于当前图片编辑 |
| local_edit | 局部编辑 |
| style_transfer | 风格迁移 |
| background_replace | 背景替换 |
| object_add | 添加对象 |
| object_remove | 删除对象 |
| text_edit | 图片中文字编辑 |
| variation | 生成变体 |
| upscale | 高清放大 |
| undo | 撤销 |
| redo | 重做 |
| compare | 对比版本 |
| export | 导出 |

### 7.2 Prompt Agent

职责：把口语化指令改写为图像模型更稳定的编辑指令。

用户输入：

```text
换成日落，人物别动
```

改写输出：

```json
{
  "positive_prompt": "Edit the current image by changing the background lighting and atmosphere to a warm sunset scene. Keep the main subject's identity, face, body, pose, clothing, camera angle, and composition unchanged. Only modify the background lighting, sky color, and ambient tone.",
  "negative_prompt": "Do not change the face, pose, clothing, body shape, camera angle, or composition.",
  "preservation_constraints": ["face identity", "pose", "composition", "clothing"],
  "edit_strength": 0.45
}
```

### 7.3 模型路由规则

职责：根据意图、编辑类型和约束选择最合适的模型和工具。路由逻辑应作为确定性规则实现，而非独立 Agent。

#### 7.3.1 模型能力矩阵

> 注：下表中"模型"指基础生成模型。ControlNet、IP-Adapter、LoRA 是**附加在基础模型上的条件控制/微调技术**，不是独立的基础模型。

| 模型 | 文生图 | 多轮编辑 | 局部 inpainting | 人物一致性 | 文字渲染 | 分辨率 |
|---|---|---|---|---|---|---|
| Gemini 3.1 Flash Image | ✅ | ✅（Thought Signatures） | ✅ | ✅（reference image） | ✅ | 512px ~ 4K |
| Gemini 3 Pro Image | ✅ | ✅（Thinking 模式） | ✅ | ✅ | ✅ | 1K ~ 4K |
| GPT Image 2 | ✅ | ✅（Responses API） | ✅（mask 支持） | ✅（input_fidelity） | ✅ | 自定义分辨率 |
| GPT Image 1.5 | ✅ | ✅ | ✅ | ✅ | 一般 | 1024x1024 等 |
| Flux + ComfyUI | ✅ | 有限 | ✅（Flux inpainting） | ✅（通过 IP-Adapter） | 有限 | 可配置 |
| SDXL + ControlNet | ✅ | 有限 | ✅（通过 ControlNet） | ✅（通过 IP-Adapter） | 有限 | 可配置 |

#### 7.3.2 路由规则示例

```python
# 基础路由规则 — 生产环境应使用配置化规则而非硬编码
def select_model(intent: str, edit_scope: str, has_mask: bool, has_reference: bool) -> dict:
    if intent == "generate_image":
        return {"tool": "gemini_generate", "model": "gemini-3.1-flash-image"}
    
    if intent in ["edit_image", "background_replace", "style_transfer"]:
        if edit_scope == "global":
            return {"tool": "gemini_edit", "model": "gemini-3.1-flash-image"}
    
    if intent == "local_edit" and has_mask:
        return {"tool": "comfyui_inpaint", "model": "flux-dev"}
    
    if intent == "variation":
        return {"tool": "gemini_edit", "model": "gemini-3-pro-image"}
    
    if intent == "upscale":
        return {"tool": "upscale", "model": "esrgan"}
    
    # 默认：全局自然语言编辑
    return {"tool": "gemini_edit", "model": "gemini-3.1-flash-image"}
```

#### 7.3.3 路由决策因子

| 因子 | 优先级 | 说明 |
|---|---|---|
| 编辑类型 | 高 | 全局编辑 → Gemini/GPT Image；局部 inpainting → ComfyUI/Flux |
| 人物一致性要求 | 高 | 有参考图 → Gemini reference image 或 IP-Adapter（图像提示适配器） |
| 文字渲染需求 | 中 | 需要文字 → Gemini 3 / GPT Image 2 |
| 成本约束 | 中 | 高频低成本 → Gemini 3.1 Flash Image |
| 延迟要求 | 低 | 实时 → Gemini 3.1 Flash Image（速度快） |
| 供应商可用性 | 高 | 主模型不可用 → fallback 到备选模型 |

### 7.4 Visual QA Agent

职责：检查输出是否满足用户要求。

检查项：

- 是否完成目标修改。
- 是否破坏主体身份。
- 是否改变不该改变的区域。
- 是否有明显畸形、错字、伪影。
- 是否违反安全策略。

示例输出：

```json
{
  "pass": false,
  "score": 0.62,
  "issues": [
    "background changed correctly",
    "main subject face changed slightly"
  ],
  "retry_suggestion": "Reduce edit strength and explicitly preserve facial identity."
}
```

---

## 八、Image Tool Layer

### 8.1 统一接口

不要让 LangGraph 节点直接调用不同厂商 API。应做统一工具层。

```python
class ImageTool(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        ...

    async def edit(self, request: EditRequest) -> EditResult:
        ...

    async def upscale(self, request: UpscaleRequest) -> UpscaleResult:
        ...
```

### 8.2 编辑请求结构

```python
@dataclass
class EditRequest:
    input_image_url: str
    prompt: str
    negative_prompt: str | None
    mask_image_url: str | None
    reference_image_urls: list[str]
    aspect_ratio: str | None
    seed: int | None
    strength: float | None
    metadata: dict
```

### 8.3 可接入工具

> 注：下表区分了**基础模型**（生成/编辑图像）、**条件控制技术**（附加在基础模型上）、**工具/工作流引擎**（编排和后处理）。

```text
# 基础模型（API 或本地部署）
GeminiImageTool          # Gemini 3.1 Flash Image / Gemini 3 Pro Image
OpenAIImageTool          # GPT Image 2 / GPT Image 1.5 / GPT Image 1
FluxImageTool            # Flux dev/schnell（本地或 API）
StableDiffusionTool      # SDXL / SD 1.5（本地部署）

# 条件控制技术（附加在基础模型上，非独立模型）
ControlNetTool           # 条件控制架构：边缘/深度/姿态/分割图引导生成
IPAdapterTool            # 图像提示适配器：用参考图引导风格和内容
LoRATool                 # 低秩微调：轻量级风格/人物/概念微调

# 工具/工作流引擎
ComfyUIImageTool         # ComfyUI 工作流编排（整合上述模型和技术）
UpscaleTool              # ESRGAN / Real-ESRGAN / Topaz 类超分辨率
SafetyModerationTool     # 内容安全审核
MaskGenerationTool       # 自动生成 mask（SAM / GroundingDINO）
```

### 8.4 模型路由初版规则

```python
# 基础路由规则 — 生产环境建议使用配置中心管理
if intent == "generate_image":
    tool = "gemini_generate"
    model = "gemini-3.1-flash-image"
elif intent in ["edit_image", "background_replace", "style_transfer"]:
    tool = "gemini_edit"
    model = "gemini-3.1-flash-image"
elif intent == "local_edit" and mask_image_id:
    tool = "comfyui_inpaint"
    model = "flux-dev"
elif intent == "upscale":
    tool = "upscale"
    model = "esrgan"
else:
    tool = "gemini_edit"
    model = "gemini-3.1-flash-image"
```

后期路由可加入：

- 成本（Gemini 3.1 Flash 价格低于 Gemini 3 Pro）。
- 延迟（Flash 模型响应更快）。
- 历史成功率。
- 用户会员等级。
- 分辨率（Gemini 支持 512px ~ 4K）。
- 地区可用性。
- 供应商故障降级（Gemini 不可用 → GPT Image 2 → ComfyUI/Flux）。

---

## 九、API 设计

### 9.1 核心接口

```http
POST /projects
POST /sessions

POST /sessions/{session_id}/turns
GET /sessions/{session_id}
GET /sessions/{session_id}/turns
GET /turns/{turn_id}

POST /sessions/{session_id}/undo
POST /sessions/{session_id}/redo
POST /sessions/{session_id}/switch-current-turn

POST /images/upload
GET /images/{image_id}

GET /jobs/{job_id}
POST /jobs/{job_id}/cancel
```

### 9.2 创建编辑任务

请求：

```json
{
  "instruction": "把背景换成雪山，人物不要变",
  "current_turn_id": "turn_123",
  "reference_image_ids": [],
  "mask_image_id": null,
  "options": {
    "aspect_ratio": "1:1",
    "quality": "high"
  }
}
```

**同步响应**（<3s，安全检查 + 意图分析完成后）：

```json
{
  "job_id": "job_456",
  "turn_id": "turn_789",
  "status": "processing",
  "analysis": {
    "intent": "background_replace",
    "edit_scope": "background",
    "selected_model": "gemini-3.1-flash-image",
    "estimated_time": "10-30s"
  }
}
```

**安全检查失败时的同步响应**（立即返回，不进入异步队列）：

```json
{
  "job_id": null,
  "turn_id": null,
  "status": "rejected",
  "error": {
    "code": "safety_check_failed",
    "message": "请求涉及敏感内容，无法执行"
  }
}
```

**异步完成响应**（通过 WebSocket/SSE 推送或轮询获取）：

```json
{
  "turn_id": "turn_789",
  "parent_turn_id": "turn_123",
  "output_image_id": "img_999",
  "output_image_url": "https://cdn.example.com/img_999.png",
  "qa_result": {
    "pass": true,
    "score": 0.88
  }
}
```

---

## 十、异步任务与状态

图片生成和编辑必须异步处理。

### 10.1 两阶段执行模型

```text
【同步阶段 — 用户等待，<3s】
  API 接收请求
    ↓
  load_session（加载状态）
    ↓
  safety_check（安全检查 — 失败则立即返回 rejected）
    ↓
  classify_intent（意图分类）
    ↓
  rewrite_prompt（prompt 改写）
    ↓
  select_tool（模型路由）
    ↓
  返回 job_id + turn_id + analysis，状态为 "processing"
    ↓
【异步阶段 — 后台执行，5-60s】
  run_image_tool（图像生成/编辑）
    ↓
  visual_qa（质量检查）
    ↓
  persist_turn（持久化）
    ↓
  通过 WebSocket/SSE 推送结果
```

### 10.2 任务状态

```text
processing       # 同步阶段完成，进入异步队列
queued           # 在队列中等待
running          # 正在执行
waiting_for_model  # 等待模型响应
qa_checking      # 质量检查中
retrying         # 重试中
succeeded        # 成功
failed           # 失败
cancelled        # 用户取消
rejected         # 安全检查拒绝（同步返回，不进入队列）
```

### 10.3 Worker 流程

```text
API 创建 job 和 pending turn
  ↓
Queue 投递任务
  ↓
Worker 加载 turn 和 session
  ↓
执行 LangGraph workflow
  ↓
上传结果图到对象存储
  ↓
更新 turn、job、session.current_turn_id
  ↓
通知前端或等待轮询
```

### 10.4 重试策略

- 模型超时（>60s）：可重试，自动降级到备选模型（Gemini 3 Pro → Gemini 3.1 Flash → ComfyUI/Flux）。
- 安全拒绝：不可重试，直接返回 rejected。
- QA 失败：最多自动重试 1 到 2 次，每次调整 prompt 和参数。
- 供应商错误：切换 fallback tool。
- 用户取消：停止后续节点，保留 cancelled 状态。

### 10.5 超时控制

| 步骤 | 超时时间 | 超时处理 |
|---|---|---|
| run_image_tool | 60s | 降级到备选模型 |
| visual_qa | 10s | 跳过 QA，标记为 qa_passed |
| 整体 job | 120s | 标记为 failed，通知用户 |
| 用户取消 | 立即 | 停止后续节点 |

---

## 十一、前端产品形态

长期产品不应只有聊天框。推荐布局：

```text
左侧：项目与版本树
中间：当前画布
右侧：参数、参考图、mask、模型选择
底部：自然语言输入框
```

必备能力：

- 实时进度反馈：通过 WebSocket/SSE 展示生成进度（分析中 → 生成中 → 质量检查中 → 完成）。
- 版本缩略图。
- 撤销和重做。
- 从某一版继续编辑。
- 两版对比。
- 局部圈选生成 mask。
- 上传参考图。
- 生成多个变体。
- 重新生成当前轮。
- 下载导出。
- 查看本轮使用的 prompt 和参数。

用户常见需求示例：

```text
还是上一版好
这个背景保留，但人物换回第二版
给我三个不同风格
只改衣服，脸别动
回到刚才那张，改成横版
```

这些需求都依赖版本树和图片资产管理。

---

## 十二、安全与合规

需要在输入、执行和输出三个阶段都做安全检查。

### 12.1 高风险请求

- 换脸和身份冒充。
- 裸露和性化内容。
- 未成年人相关敏感内容。
- 伪造证件、票据、官方文件。
- 去水印和版权规避。
- 政治人物或公众人物误导性合成。
- 暴力、仇恨、违法活动。

### 12.2 工程措施

- 上传图片 moderation。
- 用户 prompt moderation。
- 输出图片 moderation。
- 敏感 intent 拦截。
- 图片 EXIF 清理。
- 私有图片访问鉴权。
- 临时 URL 过期。
- 审计日志。

---

## 十三、观测与评估

长期产品必须记录每轮执行质量。

### 13.1 指标

| 指标 | 用途 |
|---|---|
| turn_success_rate | 每轮生成成功率 |
| qa_pass_rate | 自动质检通过率 |
| retry_rate | 重试率 |
| user_regenerate_rate | 用户主动重生成率 |
| undo_rate | 用户撤销率 |
| average_latency | 平均耗时 |
| p95_latency | 长尾耗时 |
| cost_per_turn | 单轮成本 |
| model_failure_rate | 模型失败率 |
| provider_fallback_rate | 供应商降级率 |

### 13.2 日志字段

```text
session_id
turn_id
intent
tool
model_provider
model_name
latency_ms
input_tokens
output_tokens
image_cost
qa_score
retry_count
error_code
user_feedback
```

---

## 十四、分阶段落地

### 14.1 第一阶段：可靠 MVP

- 实现 project、session、turn、image、job 数据模型。
- 接入一个图像生成/编辑模型。
- 支持异步 job。
- 支持历史版本、撤销、重做。
- 实现基础 Prompt Rewrite。
- 保存每轮输入、输出、prompt、模型参数。

### 14.2 第二阶段：可控编辑

- 支持局部 mask。
- 支持参考图。
- 接入多模型 router。
- 实现 Visual QA。
- 自动重试一次。
- 支持版本对比。

### 14.3 第三阶段：产品化

- 成本和质量路由。
- 会员分层。
- 模板工作流。
- 批量生成。
- 团队协作。
- 素材库。
- 用户反馈闭环。

### 14.4 第四阶段：高级能力

- 角色一致性（IP-Adapter + LoRA 微调）。
- 品牌风格一致性（LoRA 风格微调）。
- ComfyUI 工作流市场。
- ControlNet 高级控制（姿态、深度、分割）。
- 自动图层分解。
- 可编辑对象识别。
- 多图合成和局部重排。

---

## 十五、实现优先级

### 15.1 先做

- 版本树。
- 图片资产存储。
- 异步 job。
- 单模型闭环。
- Prompt Rewrite。
- 基础安全检查。

### 15.2 后做

- 多 Agent 角色协作。
- 复杂自动规划。
- 大量模型接入。
- 自研视觉编辑模型。
- 高级工作流市场。

### 15.3 不建议早期投入

- 让多个 Agent 长时间自由讨论。
- 一开始就接 5 个以上模型。
- 没有版本树只依赖聊天上下文。
- 没有异步任务直接同步等待图片生成。
- 不保存模型参数和 prompt，导致结果不可追踪。

---

## 十六、最小正确架构

如果现在开始实现，建议最小但长期方向正确的架构是：

```text
FastAPI
+
LangGraph
+
Postgres
+
S3 / R2 / OSS
+
Redis Queue / Celery / Dramatiq
+
Gemini 3.1 Flash Image（主模型，多轮编辑 + 文生图）
+
ComfyUI / Flux（局部 inpainting、ControlNet 条件控制高级编辑）
+
turn version tree
```

先把四件事做扎实：

- 每轮图片可追踪。
- 每轮修改可回放。
- 每个版本可回退。
- 每个模型调用可观测。

这是多轮修图长期产品的地基。
