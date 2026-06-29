# 多轮修图长期产品实现参考

> 面向“输入一句话生成图片，并支持后续多轮自然语言修图”的长期产品方案。核心结论：不要把系统做成自由聊天式多 Agent，而应做成“有状态的图片版本系统 + 可控工作流编排 + 多模型工具层 + 质量评估闭环”。

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
Gemini / OpenAI / Flux / Stable Diffusion / ComfyUI / Upscaler
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
| LangGraph | 生产级有状态工作流、版本管理、复杂路由 | 推荐 |
| OpenAI Agents SDK | OpenAI 生态内快速 MVP，简单 handoff | 可用于早期 MVP |
| Gemini Interactions API | Gemini 图像模型、多轮图像生成和编辑 | 可作为图像能力核心 |
| CrewAI | Demo、角色化任务编排 | 不建议作为长期主干 |
| AutoGen / AG2 | 研究型多 Agent 对话 | 不建议作为产品主干 |
| ComfyUI | 可控图像工作流、Flux/SD/ControlNet/LoRA | 作为工具层接入 |

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
Gemini 或 OpenAI 图像编辑
+
ComfyUI / Flux / SD 作为高级编辑后端
```

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

`turns.parent_turn_id` 是多轮修图长期产品的关键字段。

它支持：

- 撤销到上一版。
- 从任意历史版本继续编辑。
- 一个版本生成多个分支。
- 对比不同版本。
- 追踪每张图的生成来源。

示例：

```text
turn_0
  └── turn_1
        ├── turn_2a
        │     └── turn_3a
        └── turn_2b
```

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

### 7.3 Router Agent

职责：根据任务选择模型和工具。

| 用户需求 | 推荐工具 |
|---|---|
| 首次文生图 | Gemini / OpenAI / Flux |
| 自然语言多轮编辑 | Gemini / OpenAI |
| 局部替换 | Flux inpainting / SD inpainting / ComfyUI |
| 保持人物一致 | Reference image / IP-Adapter / LoRA / Gemini |
| 精准姿态控制 | ControlNet / OpenPose |
| 风格化 | Flux / SDXL / LoRA |
| 高清放大 | Upscaler / ESRGAN / Topaz 类工具 |

示例输出：

```json
{
  "tool": "gemini_image_edit",
  "reason": "natural language global image editing with identity preservation",
  "fallback_tool": "comfyui_inpaint",
  "params": {
    "aspect_ratio": "1:1",
    "preserve_subject": true,
    "quality": "high"
  }
}
```

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

```text
GeminiImageTool
OpenAIImageTool
FluxImageTool
ComfyUIImageTool
StableDiffusionTool
UpscaleTool
SafetyModerationTool
MaskGenerationTool
```

### 8.4 模型路由初版规则

```python
if intent == "generate_image":
    tool = "gemini_generate"
elif intent in ["edit_image", "background_replace", "style_transfer"]:
    tool = "gemini_edit"
elif intent == "local_edit" and mask_image_id:
    tool = "flux_inpaint"
elif intent == "upscale":
    tool = "upscale"
else:
    tool = "gemini_edit"
```

后期路由可加入：

- 成本。
- 延迟。
- 历史成功率。
- 用户会员等级。
- 分辨率。
- 地区可用性。
- 供应商故障降级。

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

响应：

```json
{
  "job_id": "job_456",
  "turn_id": "turn_789",
  "status": "queued"
}
```

任务完成：

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

### 10.1 任务状态

```text
queued
running
waiting_for_model
qa_checking
retrying
succeeded
failed
cancelled
```

### 10.2 Worker 流程

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

### 10.3 重试策略

- 模型超时：可重试。
- 安全拒绝：不可重试。
- QA 失败：最多自动重试 1 到 2 次。
- 供应商错误：切换 fallback tool。
- 用户取消：停止后续节点，保留 failed/cancelled 状态。

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

- 角色一致性。
- 品牌风格一致性。
- ComfyUI 工作流市场。
- LoRA / reference identity。
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
Gemini 或 OpenAI 图像编辑
+
turn version tree
```

先把四件事做扎实：

- 每轮图片可追踪。
- 每轮修改可回放。
- 每个版本可回退。
- 每个模型调用可观测。

这是多轮修图长期产品的地基。
