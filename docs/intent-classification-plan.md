# 语义意图驱动的模型路由方案

> 核心思路：workflow 中新增 `classify_intent` 节点，用 doubao 廉价模型对
> 指令做语义分类；`run_image_tool` 根据分类结果查找路由表，
> 决定使用哪个模型/哪个 variant/哪些参数。

## 问题

当前路由链只到工具级别（`moebius_inpaint` vs `doubao_inpaint`），
工具内部没有根据指令语义做细分。具体表现：

- Moebius 始终用 `pretrained` 通用权重，人脸修图效果差
- 权重目录下已有 `ft_celebahq` / `ft_ffhq` 人脸微调版，未被利用
- 未来引入 LaMa、CodeFormer 等模型后，同样缺少语义路由

## 方案概览

```
指令 → resolve_task_type() → select_tool() → classify_intent() → 路由表 → 执行
                                                                    ↓
                                                     {model, variant, params}
```

**路由表** 将语义类别映射为具体的执行配置（用哪个模型、哪个权重、哪些推理参数），
分类和路由解耦，新增模型只需改路由表。

## 1. 语义分类

### 1.1 配置

```env
# 意图分类使用的模型（默认同 DOUBAO_MODEL，即开即用；可换为廉价文本模型）
DOUBAO_CLASSIFY_MODEL=doubao-lite-32k-xxxxx
```

### 1.2 类别定义

| 类别 | 含义 | 典型指令 |
|---|---|---|
| `face_edit` | 涉及人脸的任何修改 | 面部线条、磨皮美白、瘦脸、去眼袋、修五官 |
| `object_remove` | 删除不想要的元素 | 删除广告/水印/路人、去文字 |
| `background_edit` | 修改背景 | 换背景、背景虚化、清除背景杂物 |
| `style_transfer` | 风格/滤镜/调色 | 变复古、变卡通、调冷暖色调、加滤镜 |
| `general_edit` | 其他所有修图操作 | 裁剪、加文字、拼接、变形 |

**分类原则**：
- **包含即可**：只要指令涉及人脸就判 `face_edit`，即使也包含其他修改
- 识别为 `face_edit` 只有可能提升效果，不会变差（人脸 variant 对非人脸区域同样能用）
- `confidence < 0.6` 时降级为 `general_edit`

### 1.3 新增文件

`image_editor/agents/intent_classifier.py`

单一异步函数，调用 `DoubaoLLM.chat_json()`，返回 `{"category": str, "confidence": float}`。

**Prompt 设计**：

```
你是一个图片修图指令分类器。
根据用户的修图指令，输出 JSON：{"category": "<类别>", "confidence": <0-1的小数>}

类别：
- face_edit：涉及人脸修改的任何操作
  如：面部线条/五官调整、皮肤美化、磨皮美白、瘦脸、
  去眼袋/法令纹/鱼尾纹/黑眼圈、修改眼睛/鼻子/嘴巴/眉毛/嘴唇、
  美颜、表情调整、去皱、祛痘、祛斑、提拉紧致等
- object_remove：删除画面中不需要的元素
  如：删除广告/文字/水印/logo、去掉路人/杂物、清除污渍/划痕等
- background_edit：修改/更换/清理背景
  如：换背景、背景虚化、清除背景中多余物体、背景延展等
- style_transfer：风格/滤镜/颜色调整
  如：变复古/赛博朋克/油画风格、调冷暖色调、加滤镜、黑白化等
- general_edit：以上未覆盖的其他修图操作
  如：裁剪、旋转、加文字、拼接、变形、调亮度/对比度等

注意：只要指令涉及"人脸"就是 face_edit，即使也包含其他修改。
confidence 低于 0.6 时视为 general_edit。

示例：
输入：修改面部线条，变硬朗
输出：{"category": "face_edit", "confidence": 0.95}

输入：删除球衣胸前广告
输出：{"category": "object_remove", "confidence": 0.98}

输入：把背景换成海滩
输出：{"category": "background_edit", "confidence": 0.97}

输入：调成复古胶片色调
输出：{"category": "style_transfer", "confidence": 0.96}
```

## 2. 路由表

### 2.1 位置

独立配置文件或代码模块（建议 `tools/model_routes.py`），
与分类逻辑分离，方便扩展。

### 2.2 映射结构

```python
# 每条记录定义：category → {model, variant, params}
MODEL_ROUTES: dict[str, dict] = {
    "face_edit": {
        "model": "moebius",
        "variant": "ft_ffhq",         # 人脸微调权重
        "params": {},
    },
    "object_remove": {
        "model": "moebius",
        "variant": "pretrained",      # 通用权重即可
        "params": {"guidance_scale": 3.0},  # 可调低引导尺度加强抹除
    },
    "background_edit": {
        "model": "moebius",
        "variant": "ft_places2",      # 场景微调权重
        "params": {},
    },
    "style_transfer": {
        "model": "moebius",
        "variant": "pretrained",
        "params": {"paste": False},   # 不混合原图，完全重绘
    },
    "general_edit": {
        "model": "moebius",
        "variant": "pretrained",
        "params": {},
    },
}
```

### 2.3 未来扩展示例

引入 LaMa 做轻量物体移除：

```python
"object_remove": {
    "model": "lama",          # 换模型！不经过 Moebius
    "variant": "default",
    "params": {},
}
```

引入 CodeFormer 做人脸修复后处理：

```python
"face_restore": {             # 新增类别
    "model": "codeformer",    # 独立模型
    "variant": "default",
    "params": {"strength": 0.8},
}
```

只需更新路由表，分类 prompt 加一个示例，工作流无需改动。

## 3. State 新增字段

```python
# state.py — ImageEditState
intent_category: Optional[str]      # "face_edit" | "object_remove" | ...
intent_confidence: Optional[float]  # 模型置信度
```

## 4. Workflow 变更

```
load_session → safety_check → classify_intent ──→ enhance_prompt (generate/edit)
                                               └─→ run_image_tool (inpaint)
```

- `route_after_safety` → 始终指向 `classify_intent`
- 新增 `route_after_classify` → 替代原 `route_after_safety` 的分支逻辑

## 5. run_image_tool 的变化

工具层读取 `intent_category` 查路由表：

```python
from image_editor.tools.model_routes import MODEL_ROUTES

route = MODEL_ROUTES.get(state.get("intent_category"), MODEL_ROUTES["general_edit"])

if route["model"] == "moebius":
    result = await moebius_client.inpaint(
        ..., variant=route["variant"], **route["params"]
    )
elif route["model"] == "lama":
    result = await lama_client.inpaint(...)
elif route["model"] == "codeformer":
    result = await codeformer_client.restore_face(...)
```

## 6. MoebiusClient 变更

支持 variant 动态切换：

| 改动 | 说明 |
|---|---|
| 新增 `_loaded_variant: str \| None` | 追踪当前加载的 variant |
| `_load_pipeline(variant: str)` | 接受 variant，构造对应权重路径 |
| 新增 `_cleanup()` | 卸载 pipeline + GPU 显存回收 |
| `inpaint(..., variant=None)` | 透传 variant |

**权重路径构造**：
```python
path = Path(config.moebius.weight_dir) / variant / "diffusion_pytorch_model.bin"
```

**切换行为**：
- 首次调用 → 加载 variant（~7s）
- 同一 variant 复用 → 零开销
- 切换 variant → cleanup + 重新加载（~7s）

## 7. 延迟与成本

| 步骤 | 延迟 | 备注 |
|---|---|---|
| classify_intent | ~0.5-1.5s | doubao-lite 更快 |
| variant 切换（首次/切换） | ~7s | 仅 Moebius 换权重时 |
| Moebius inpainting | ~7-13s | 不变 |
| LaMa inpainting | ~1-2s | 比 Moebius 快得多 |

分类 tokens 约 300（输入）+ 15（输出），成本可忽略。

## 架构要点

| 特性 | 说明 |
|---|---|
| 分类与路由解耦 | LLM 只输出语义类别，不感知底层模型细节 |
| 路由表可配置 | 增减模型/调参只需改 `model_routes.py` |
| 向后兼容 | `general_edit` 兜底，行为与当前一致 |
| 模型可替换 | `object_remove` 可以从 Moebius 切换到 LaMa，无需改 workflow |

## 变更文件清单

| 文件 | 操作 | 变更内容 |
|---|---|---|
| `config.py` | 修改 | DoubaoConfig 新增 `classify_model` |
| `state.py` | 修改 | ImageEditState 新增 2 个字段 |
| `agents/intent_classifier.py` | **新建** | 分类逻辑 + prompt |
| `tools/model_routes.py` | **新建** | 路由表 |
| `llm/client.py` | 修改 | `chat()` 支持 `model` 覆写参数 |
| `llm/moebius_client.py` | 修改 | 支持 variant 参数 + 动态切换 |
| `tools/moebius_image.py` | 修改 | 读取 intent_category 选 variant/params |
| `workflow.py` | 修改 | 新增 `classify_intent` 节点 + 重排路由 |
