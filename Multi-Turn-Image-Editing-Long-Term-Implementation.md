# 多轮修图产品实现参考

> 面向"输入一句话生成图片，并支持后续多轮自然语言修图"的产品方案。
>
> **2026.07 更新**：当前实现采用**豆包 Seedream 5.0 单模型模式** — 多模态模型直接接收 `prompt + image` 并输出结果，内生处理意图理解。客户端工作流只负责 undo/redo 判断和透传用户指令。

### 架构原则

多轮修图产品的正确架构是**确定性工作流 + 显式状态管理**。Agent 步骤只在必要时介入，不要让 LLM 自由决策流程走向。

---

#### 产业级证据：业界共识的形成（2024.12 — 2026.07）

> **2026.07 更新**：随着豆包 Seedream 5.0 等原生多模态大模型的成熟，产业共识进一步向"简化"方向演进。多模态模型能够内生处理意图理解和编辑决策，使得 Agent 步骤可大幅精简。这与 Anthropic 提出的"start static, add dynamism incrementally"原则一致——先用最简单的单模型工作流承载业务，仅在单模型无法覆盖的场景下才引入多模型路由和独立 Agent 节点。

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

#### 当前实现：`image_editor/workflow.py` 9 节点 DAG

`image_editor/workflow.py` 的 LangGraph StateGraph 是一个**固定 DAG 拓扑**，不是 Agent Loop：

```
load_session → safety_check → classify_intent
                                   ├─ version_op → handle_version_op → END
                                   └─ image_op → rewrite_prompt → select_tool
                                                  → run_image_tool → visual_qa
                                                      ├─ pass  → persist_turn → END
                                                      ├─ retry → rewrite_prompt (max 2)
                                                      └─ fail  → persist_turn → END
```

各节点在 seedream 单模型模式下的实际行为：
- `classify_intent` — 区分 undo/redo 和图片操作；有当前图 → `edit_image`，无 → `generate_image`（纯规则，无 LLM）
- `rewrite_prompt` — 透传 `user_instruction`（seedream 直接理解自然语言）
- `select_tool` — 全部走 `doubao_generate`（单模型，无需路由）
- `run_image_tool` — 有 `current_image_url` → 图生图（`tool.edit`）；无 → 文生图（`tool.generate`）
- `visual_qa` — 透传 always pass（seedream 自行保证质量）

`DoubaoLLM` 类存在于 `llm/client.py` 但未被任何 agent 使用。版本树通过 `parent_turn_id` + `undo()` / `redo()` / `switch_current_turn()` 实现。

条件分支由纯函数 `route_by_intent()` 和 `route_by_qa()` 控制，不存在 LLM 自主决策下一步。唯一的"循环"是 `retry_count < 2` 的受控重试，不是开放式的 Agent 循环。

**多模型模式**：需要额外的 Agent 步骤来桥接自然语言与多模型调用：
- **意图分类**：理解用户要做什么
- **Prompt 改写**：将口语化指令转为结构化编辑指令
- **质量评估**：检查输出是否满足用户要求

#### 本方案的架构原则

两种部署模式的共同原则保持不变：

```text
确定性工作流引擎（LangGraph StateGraph）
  ↓ 控制流程
  ├── 单模型模式：多模态大模型内生处理意图 + 编辑 + 生成
  │      节点：load → safety → multimodal_model → visual_qa → persist
  └── 多模型模式：受控 Agent 步骤（LLM 在特定节点做推理）
         节点：load → safety → intent → rewrite → route → run → visual_qa → persist
  ↓ + 版本树管理（parent_turn_id）
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
# 基础设施
LangGraph
+
Postgres
+
S3 / R2 / OSS
+
Redis Queue / Celery / Dramatiq

# 单模型模式（推荐起步方案）
豆包 Seedream 5.0（主模型，原生多轮编辑 + 文生图，text+image in, image out）

# 多模型模式（高级扩展方案）
Gemini 3.1 Flash Image（主模型，多轮编辑 + 文生图）
+
GPT Image 2 / GPT Image 1.5（备选图像生成/编辑）
+
ComfyUI / Flux / SD（高级编辑：局部 inpainting、ControlNet 条件控制）
```

### 3.4 与 Deep Agents 的关系

Deep Agents 底层是 LangGraph，理论上可以实现相同功能。但多轮修图的核心需求——版本树（`parent_turn_id`）、显式状态管理、可预测的成本——在 Deep Agents 的 Agent Loop 范式下需要大量定制才能实现，不如直接用 LangGraph 构建专用工作流。详见 [3.4.1 版本树为什么重要](#521-什么是版本树)。

---

---

## 四、核心工作流

当前实现采用 seedream 单模型模式。seedream 作为多模态模型，直接接收 `prompt + image` 并输出结果。客户端工作流不负责意图理解和 prompt 改写——仅处理 undo/redo 判断和透传用户指令。

```text
Start → Load Session → Safety Check
                           ├─ Version Op? → Undo/Redo → End
                           └─ Edit Prompt → Route → Run Image Tool
                                              (via seedream images/generations)
                                                   ├─ 有当前图 → 图生图
                                                   └─ 无 → 文生图
                                      ↓
                                  Visual QA → Persist Turn → End
```

> `classify_intent`、`rewrite_prompt`、`select_tool` 节点保留在代码中但行为已简化：intent 仅区分 undo/redo；prompt 透传；router 全部走 doubao_generate。seedream 内生处理意图理解和编辑决策。

### 4.1 典型用户链路

> **单模型模式**：用户所有指令（生成、编辑、风格变换、局部修改）直接发给多模态模型。模型根据收到的图片+指令自主处理。无需区分"这是生成还是编辑"。

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

> **单模型 vs 多模型字段使用**：`intent`、`edit_scope`、`rewritten_prompt`、`negative_prompt`、`preservation_constraints`、`model_provider`、`selected_tool` 等字段在多模型模式下有值，在单模型模式下为 null。单模型模式下 `model_name` 固定为多模态模型名（如 `doubao-seedream-5.0`），`user_instruction` 为原始用户输入。

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
    # 通用字段（两种模式共用）
    user_id: str
    project_id: str
    session_id: str
    turn_id: str
    user_instruction: str
    current_turn_id: str | None
    current_image_id: str | None
    current_image_url: str | None       # 单模型模式新增：当前图片 URL（传递给多模态模型）
    reference_image_ids: list[str]
    mask_image_id: str | None
    mask_image_url: str | None          # 单模型模式新增：mask 图片 URL

    # 多模型模式专用（单模型模式 unused）
    intent: str | None                  # single-model unused
    edit_scope: str | None              # single-model unused
    operation: str | None               # single-model unused
    constraints: list[str]              # single-model unused
    rewritten_prompt: str | None        # single-model unused
    negative_prompt: str | None         # single-model unused
    selected_tool: str | None           # single-model unused
    model_provider: str | None          # single-model unused
    model_name: str | None
    model_params: dict

    # 输出字段
    output_image_id: str | None
    output_image_url: str | None        # 单模型模式新增：输出图片 URL
    qa_result: dict | None
    retry_count: int
    error: str | None
    job_id: str | None                  # 新增：异步任务 ID
```

### 6.1 节点设计（当前实现）

| 节点 | 输入 | 输出 | 行为 |
|---|---|---|---|
| load_session | session_id | current_image_url, current_image_id | 从 MemoryStore 加载 |
| safety_check | user_instruction | error (if blocked) | 关键词过滤 |
| classify_intent | user_instruction, current_image_url | intent, operation | 纯规则：undo/redo → version_op，其余 → image_op |
| handle_version_op | intent, session_id | current_turn_id | store.undo()/redo() |
| rewrite_prompt | user_instruction | rewritten_prompt | 透传 |
| select_tool | intent | selected_tool, model_name | 全部 → doubao_generate + seedream |
| run_image_tool | selected_tool, current_image_url, rewritten_prompt | output_image_id, output_image_url | 有图 → tool.edit()，无图 → tool.generate() |
| visual_qa | — | qa_result (passed=True) | 透传 |
| persist_turn | 全状态 | — | 写入 MemoryStore |

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
    "classify_intent", route_by_intent,
    {"version_op": "handle_version_op", "image_op": "rewrite_prompt", "fail": "fail"},
)

workflow.add_edge("rewrite_prompt", "select_tool")
workflow.add_edge("select_tool", "run_image_tool")
workflow.add_edge("run_image_tool", "visual_qa")

workflow.add_conditional_edges(
    "visual_qa", route_by_qa,
    {"pass": "persist_turn", "retry": "rewrite_prompt", "fail": "persist_turn"},
)

---

## 七、Agent 节点设计

> 当前 seedream 单模型模式下，所有节点均不使用 LLM。`DoubaoLLM` 类保留但未被调用。如需多模型扩展，可恢复各节点的 LLM 调用逻辑。

### 7.1 classify_intent
当前行为：纯规则判断。输入精确匹配 undo/redo → version_op；其余 → image_op。有当前图时 intent 记为 `edit_image`，无时为 `generate_image`。seedream 多模态输入自行判断具体编辑类型。

### 7.2 rewrite_prompt
当前行为：透传。`rewritten_prompt = user_instruction`。seedream 直接理解自然语言。

### 7.3 select_tool
当前行为：全部走 `doubao_generate`，模型为 `DOUBAO_MODEL`（seedream）。无需路由。

### 7.4 visual_qa
当前行为：透传 always pass。seedream 自行保证输出质量。retry 机制保留框架但从未触发。

### 7.3 模型路由规则

> **单模型模式**：本节点在多模态大模型场景下被移除。使用单一多模态模型时无需路由，所有请求直接发给该模型。

职责：根据意图、编辑类型和约束选择最合适的模型和工具。路由逻辑应作为确定性规则实现，而非独立 Agent。

#### 7.3.1 模型能力矩阵

> 注：下表中"模型"指基础生成模型。ControlNet、IP-Adapter、LoRA 是**附加在基础模型上的条件控制/微调技术**，不是独立的基础模型。

| 模型 | 文生图 | 多轮编辑 | 局部 inpainting | 人物一致性 | 文字渲染 | 分辨率 | 多模态 |
|---|---|---|---|---|---|---|---|---|
| 豆包 Seedream 5.0 | ✅ | ✅（原生多轮） | ✅（文本描述） | ✅（原生） | ✅ | 1K ~ 4K | ✅（text+image in, image out） |
| Gemini 3.1 Flash Image | ✅ | ✅（Thought Signatures） | ✅ | ✅（reference image） | ✅ | 512px ~ 4K | ❌（需单独 prompt/routing） |
| Gemini 3 Pro Image | ✅ | ✅（Thinking 模式） | ✅ | ✅ | ✅ | 1K ~ 4K | ❌（需单独 prompt/routing） |
| GPT Image 2 | ✅ | ✅（Responses API） | ✅（mask 支持） | ✅（input_fidelity） | ✅ | 自定义分辨率 | ❌（需单独 prompt/routing） |
| GPT Image 1.5 | ✅ | ✅ | ✅ | ✅ | 一般 | 1024x1024 等 | ❌（需单独 prompt/routing） |
| Flux + ComfyUI | ✅ | 有限 | ✅（Flux inpainting） | ✅（通过 IP-Adapter） | 有限 | 可配置 | ❌ |
| SDXL + ControlNet | ✅ | 有限 | ✅（通过 ControlNet） | ✅（通过 IP-Adapter） | 有限 | 可配置 | ❌ |

> **多模态 vs 非多模态**：多模态模型（如豆包 Seedream 5.0）同时接受文本和图片输入并输出图片，模型内生处理意图理解、编辑方式选择和参数决策。非多模态模型需要外部 pipeline 将用户指令拆解为 prompt、mask、参数等结构化输入。

#### 7.2.1 模型能力矩阵

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

> 注：下表区分了**多模态模型**（同时处理文本+图片输入输出）、**基础模型**（生成/编辑图像）、**条件控制技术**（附加在基础模型上）、**工具/工作流引擎**（编排和后处理）。

```text
# 多模态模型（text + image in, image out — 单模型模式首选）
DoubaoSeedreamTool       # 豆包 Seedream 5.0：原生多轮编辑、文本+图片输入、图片输出

# 基础模型（API 或本地部署 — 多模型模式）
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

### 8.4 模型路由

当前单模型模式：所有请求统一走 `doubao_seedream`，无需路由。多模型模式需根据意图和约束选择最佳模型（工具层预留扩展）。
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

**单模型模式同步响应**（精简，无 analysis 字段）：
```json
{
  "job_id": "job_456",
  "turn_id": "turn_789",
  "status": "processing",
  "model": "doubao-seedream-5.0",
  "estimated_time": "5-20s"
}
```

**多模型模式同步响应**（含结构化 analysis）：
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

#### 单模型模式

```text
【同步阶段 — 用户等待，<1s】
  API 接收请求
    ↓
  load_session（加载状态）
    ↓
  safety_check（安全检查 — 失败则立即返回 rejected）
    ↓
  返回 job_id + turn_id，状态为 "processing"
    ↓
【异步阶段 — 后台执行，5-60s】
  call_multimodal_model（多模态模型 text+image -> 结果图）
    ↓
  visual_qa（质量检查）
    ↓
  persist_turn（持久化）
    ↓
  通过 WebSocket/SSE 推送结果
```

#### 多模型模式

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
| call_multimodal_model / run_image_tool | 60s | 降级到备选模型（单模型：降级到备选多模态模型；多模型：降级到备选图像模型） |
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
- 接入一个多模态大模型（如豆包 Seedream 5.0），实现单模型模式闭环。
- 支持异步 job。
- 支持历史版本、撤销、重做。
- 实现基础安全检查 + Visual QA。
- 保存每轮输入、输出、模型参数。
- **不需要** Prompt Rewrite / 意图分类 / 模型路由（单模型模式下这些由模型内生处理）。

### 14.2 第二阶段：可控编辑与多模型扩展

- 支持局部 mask。
- 支持参考图。
- 可选接入多模型 router（当单模型不能满足特定编辑需求时）。
- 完善 Visual QA（自动重试策略优化）。
- 支持版本对比。
- 实现 Prompt Rewrite + 意图分类（多模型模式）。

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
# 单模型模式起步（推荐）
豆包 Seedream 5.0（主模型，原生多轮编辑 + 文生图，text+image in, image out）
+
# 多模型模式扩展（按需）
Gemini 3.1 Flash Image（备选模型，多轮编辑 + 文生图）
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
