# 多轮修图系统架构设计

> 基于 LLM Agent 编排 + 工具链的多轮对话式图片编辑系统

---

## 一、需求定义

- 用户输入一句话 → 生成/修改图片
- 支持多轮修改（每轮基于上一轮结果）
- 精确局部编辑（inpainting，指定区域修改）
- 模型无关（适配多种图像生成/编辑模型）
- Python 后端 API 服务

---

## 二、整体架构

```
用户请求 → FastAPI → Agent Orchestrator (LLM) → 路由到具体工具
                                                    ↓
                                        ┌───────────┼───────────┐
                                        ↓           ↓           ↓
                                   文生图工具   Mask生成工具   编辑工具
                                   (SD/Flux   (SAM2/Ground   (Inpainting/
                                    DALL-E)    edSAM/GDino)   img2img)
                                        ↓           ↓           ↓
                                        └───────────┼───────────┘
                                                    ↓
                                              状态存储 (图像+历史)
                                                    ↓
                                              返回结果
```

### 核心模块

| 模块 | 职责 | 关键技术 |
|------|------|---------|
| Agent Orchestrator | 意图理解、任务分解、工具调度 | LLM + Function Calling |
| Mask Generation | 从自然语言生成精确编辑区域 | SAM2 + GroundingDINO |
| Image Generation | 文生图 | SD/Flux/DALL-E/通义万相 |
| Image Editing | 局部编辑（inpainting）/ 全局修改（img2img） | 各模型 inpaint 接口 |
| State Management | 会话状态、编辑历史、图片快照 | SQLite/Redis + 文件系统 |
| Context Builder | 构建 LLM 上下文，控制 token 消耗 | 分层压缩策略 |
| Model Provider | 统一接口适配不同模型 | 策略模式 |

---

## 三、Agent Orchestrator 设计

LLM 驱动的意图路由，决定走哪条工具路径：

```python
class ImageAgent:
    tools = {
        "text_to_image": TextToImageTool,      # 首次生成
        "generate_mask": MaskGenerationTool,    # 从自然语言生成精确 mask
        "inpaint": InpaintingTool,              # 局部编辑
        "img2img": Img2ImgTool,                 # 全局风格/内容修改
        "get_history": HistoryTool,             # 查看编辑历史
    }

    def handle(self, user_input: str, session_id: str) -> ImageResult:
        # 1. 加载会话状态（当前图像 + 编辑历史）
        state = self.state_manager.load(session_id)

        # 2. LLM 分析意图，决定调用哪些工具
        plan = self.llm.plan(
            user_input,
            current_image=state.current_image,
            history=state.edit_history
        )

        # 3. 按计划执行工具链
        for step in plan.steps:
            result = self.execute_tool(step)
            state.update(result)

        # 4. 可选：反思机制，检查结果是否符合预期
        if not self.reflector.check(state.current_image, user_input):
            return self.retry_with_reflection(state)

        return state.current_image
```

---

## 四、Mask Generation — 精确局部编辑的核心

用户说"把左边的猫换成狗"，系统需自动定位猫的位置并生成精确 mask。

### 方案对比

| 方案 | 适用场景 | 精度 | 复杂度 |
|------|---------|------|--------|
| **SAM2 + GroundingDINO** | 通用目标分割，文本→mask | ⭐⭐⭐⭐⭐ | 中 |
| **Florence-2** | 文本引导分割 | ⭐⭐⭐⭐ | 低 |
| **CLIP + GrabCut** | 轻量级，无 GPU 可用 | ⭐⭐⭐ | 低 |
| **VLM 自己画 mask** | 多模态模型直接输出 | ⭐⭐⭐ | 低 |

### 推荐组合

SAM2 + GroundingDINO 为主，CLIP+GrabCut 为降级方案：

```python
class MaskGenerationTool:
    def generate(self, image: Image, instruction: str) -> Mask:
        # 1. 用 GroundingDINO 从文本检测目标区域
        boxes = self.grounding_dino.detect(image, instruction)

        # 2. 用 SAM2 生成精确 mask
        mask = self.sam2.segment(image, boxes)

        # 3. 可选：用 VLM 验证 mask 是否正确
        if self.config.enable_validation:
            is_correct = self.vlm.validate(image, mask, instruction)
            if not is_correct:
                mask = self.clip_grabcut.fallback(image, instruction)

        return mask
```

---

## 五、状态管理

### 数据模型

```python
@dataclass
class EditTurn:
    turn: int
    instruction: str                    # 用户指令
    intent: str                         # LLM 解析的意图（generate/edit/undo）
    tool_used: Optional[str]            # 调用的工具
    tool_params: Optional[dict]         # 工具参数（含 mask 描述）
    result_summary: str                 # 结果描述（"成功将背景替换为海边日落"）
    image_path: str                     # 结果图片路径
    token_cost: int                     # 本步消耗的 token
    timestamp: datetime

@dataclass
class EditSession:
    session_id: str
    original_image_path: str
    current_image_path: str
    turns: list[EditTurn]
    user_preferences: dict              # 用户偏好（画风、分辨率等）
    created_at: datetime
    last_active: datetime
```

### 状态存储策略

| 存储内容 | 方案 | 理由 |
|---------|------|------|
| 会话元数据 | SQLite | 轻量、无需额外服务 |
| 图片文件 | 文件系统 | 避免数据库存大对象 |
| 热数据缓存 | Redis | 高频读写会话状态 |
| 用户偏好 | SQLite | 跨会话持久化 |

---

## 六、上下文与记忆管理

多轮修图的核心挑战：**编辑轮次越多，历史越长，但 LLM 上下文窗口有限，Token 成本线性增长。**

### 6.1 上下文三层结构

```
┌─────────────────────────────────────────┐
│  Layer 1: System Prompt（固定，每次必带）  │
│  - 角色定义 + 可用工具                     │
│  - 当前图片的 metadata（尺寸/格式等）       │
│  - 修图规则（不要过度编辑等）               │
├─────────────────────────────────────────┤
│  Layer 2: Compressed History（压缩历史）  │
│  - 最近 N 轮完整记录                       │
│  - 更早的轮次压缩成摘要                     │
├─────────────────────────────────────────┤
│  Layer 3: Current Turn（当前轮）           │
│  - 用户最新指令                            │
│  - 当前图片（缩略图或描述）                  │
│  - 上一步的工具执行结果                      │
└─────────────────────────────────────────┘
```

### 6.2 ContextBuilder 实现

```python
class ContextBuilder:
    MAX_HISTORY_TURNS = 5       # 最近 5 轮保留完整记录
    SUMMARY_THRESHOLD = 5       # 超过 5 轮开始压缩早期历史

    def build_context(
        self,
        session: EditSession,
        current_instruction: str,
        current_image: Image
    ) -> list[Message]:
        messages = []
        messages.append(self._system_prompt(session))
        messages.extend(self._build_compressed_history(session))
        messages.append(self._current_turn(current_instruction, current_image, session))
        return messages

    def _build_compressed_history(self, session: EditSession) -> list[dict]:
        messages = []
        turns = session.turns

        if len(turns) <= self.MAX_HISTORY_TURNS:
            for turn in turns:
                messages.append(self._turn_to_messages(turn))
        else:
            # 早期轮次 → 压缩成摘要（~200 tokens）
            early_turns = turns[:-self.MAX_HISTORY_TURNS]
            summary = self._summarize_turns(early_turns)
            messages.append({
                "role": "assistant",
                "content": f"[编辑历史摘要] {summary}"
            })
            # 最近 N 轮 → 完整保留
            recent_turns = turns[-self.MAX_HISTORY_TURNS:]
            for turn in recent_turns:
                messages.append(self._turn_to_messages(turn))

        return messages

    def _summarize_turns(self, turns: list[EditTurn]) -> str:
        # 方式 A: 规则压缩（快、便宜）
        summary_parts = []
        for t in turns:
            summary_parts.append(f"第{t.turn}轮: {t.instruction} → {t.result_summary}")
        return "；".join(summary_parts)

        # 方式 B: LLM 摘要（更智能，但有额外成本）
        # return self.llm.summarize([t.instruction for t in turns])
```

### 6.3 Token 预算控制

```python
class TokenBudget:
    MAX_INPUT_TOKENS = 8000    # 单次请求最大输入 token

    def _estimate_tokens(self, session: EditSession) -> int:
        system = 500
        history = len(session.turns) * 150   # 每轮 ~150 tokens
        current = 800                         # 缩略图 ~800 tokens
        return system + history + current

    def auto_compress(self, session: EditSession) -> EditSession:
        if not self.check_budget(session):
            session = self._merge_older_turns(session)
        return session
```

### 6.4 图片上下文策略

图片在 LLM 上下文中极其昂贵（一张 1024x1024 图 ≈ 1000+ tokens）：

| 策略 | Token 消耗 | 适用场景 |
|------|-----------|---------|
| **缩略图**（512px, JPEG 85%） | ~800 | 精确局部编辑 |
| **VLM 描述**（纯文字） | ~200 | 简单指令（换颜色等） |
| **完整原图** | ~1500+ | 需要高精度时 |

```python
class ImageContextManager:
    def decide_strategy(self, session: EditSession, instruction: str) -> str:
        if self._is_simple_edit(instruction):
            return "description"      # 简单编辑 → 纯文字描述
        if self._needs_visual_context(instruction):
            return "thumbnail"        # 复杂编辑 → 缩略图
        if not session.turns:
            return "none"             # 首轮 → 无需图片
        return "thumbnail"
```

### 6.5 长期记忆

```python
class LongTermMemory:
    def save_user_preference(self, user_id: str, session: EditSession):
        preferences = {
            "preferred_style": self._extract_style(session),
            "common_edits": self._extract_common_edits(session),
            "preferred_model": self._extract_model_preference(session),
        }
        self.db.upsert_user_prefs(user_id, preferences)

    def get_context_for_new_session(self, user_id: str) -> str:
        prefs = self.db.get_user_prefs(user_id)
        if not prefs:
            return ""
        return f"用户历史偏好：风格={prefs.get('style')}，常用编辑={prefs.get('common_edits')}"
```

---

## 七、模型适配层

统一接口，模型无关：

```python
class ImageModelProvider(ABC):
    @abstractmethod
    def text_to_image(self, prompt: str, **kwargs) -> Image: ...

    @abstractmethod
    def inpaint(self, image: Image, mask: Mask, prompt: str, **kwargs) -> Image: ...

    @abstractmethod
    def img2img(self, image: Image, prompt: str, strength: float, **kwargs) -> Image: ...

# 实现示例
class ComfyUIProvider(ImageModelProvider):   # 本地 SD/Flux
class DallEProvider(ImageModelProvider):      # OpenAI
class QwenImageProvider(ImageModelProvider):  # 通义万相
class GeminiProvider(ImageModelProvider):     # Google Gemini
```

---

## 八、API 设计

```python
# FastAPI 路由
POST /api/session/create          # 创建修图会话
POST /api/session/{id}/edit       # 发送编辑指令
GET  /api/session/{id}/history    # 获取编辑历史
POST /api/session/{id}/undo       # 撤销上一步
DELETE /api/session/{id}          # 删除会话
```

请求示例：

```json
// POST /api/session/{id}/edit
{
  "instruction": "把背景换成海边日落",
  "model_preference": "auto"
}

// 响应
{
  "image_url": "/images/xxx.png",
  "edit_record": {
    "turn": 3,
    "tool": "inpaint",
    "mask_area": "background"
  },
  "session_version": 3
}
```

---

## 九、技术选型总结

| 组件 | 推荐方案 | 理由 |
|------|---------|------|
| Agent 编排 | 自研轻量编排 / PydanticAI | 场景是"多轮对话+工具调用"，LLM 做路由够了 |
| LLM（意图理解） | GPT-4o-mini / Qwen-Turbo | 便宜、快、够用 |
| Mask 生成 | SAM2 + GroundingDINO | 精度最高，社区成熟 |
| 图像生成 | ComfyUI API（本地）+ DALL-E（云端） | 本地跑 SD/Flux，云端兜底 |
| 状态存储 | SQLite/Redis + 文件系统 | 轻量级 |
| API 框架 | FastAPI | Python 标准选择 |

---

## 十、关键设计原则

| 原则 | 做法 |
|------|------|
| **图片不原样传** | 缩略图（512px）+ JPEG 压缩，token 降 70% |
| **历史分层** | 最近 5 轮完整，更早的压缩成摘要 |
| **预算硬控** | 超 8K tokens 自动压缩，防止成本爆炸 |
| **意图而非原文** | 存储 `intent: edit background` 而非完整 LLM 对话 |
| **摘要可 LLM 可规则** | 规则压缩免费，LLM 摘要更智能但有成本 |
| **Mask 是核心竞争力** | 精确局部编辑的质量取决于 mask 的质量 |
| **不用重量级 Agent 框架** | LangGraph/CrewAI 对此场景过于复杂 |

---

## 十一、相关研究参考

- **IMAGAgent**（2026.03）：Plan-Execute-Reflect 机制，constraint-aware planning + multi-expert reflection
- **Talk2Image**（2025.08）：多 Agent 系统，intention parsing + DAG task decomposition + feedback-driven refinement
- **Agent Banana**（2026.02）：Context Folding 压缩长交互历史 + Image Layer Decomposition 局部编辑
- **CAMEO**（2026.04）：三层 Agent 架构（Orchestration → Utility → Regulation），Quality Critic + Refinement Editor
