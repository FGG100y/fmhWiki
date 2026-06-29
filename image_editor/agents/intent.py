from __future__ import annotations

from image_editor.llm.client import DoubaoLLM
from image_editor.models import Intent, IntentResult
from image_editor.state import ImageEditState

SYSTEM_PROMPT = """你是一个图片编辑意图识别助手。根据用户输入和当前状态，判断用户的编辑意图。

输出 JSON 格式，包含以下字段：
- intent: str — 意图类型，可选值: generate_image, edit_image, local_edit, style_transfer, background_replace, object_add, object_remove, text_edit, variation, upscale, undo, redo, compare, export
- operation: str — 具体操作描述
- edit_scope: str | null — 修改范围: global, background, foreground, object, region
- requires_mask: bool — 是否需要局部 mask
- preserve: list[str] — 需要保持不变的内容列表
- risk: str — 潜在风险描述

判断规则：
1. 如果用户没有当前图片 → generate_image
2. 如果用户明确说"局部"/"只改某个区域"/"圈选"/"选中" → local_edit
3. 如果用户说"换背景" → background_replace
4. 如果用户说"换风格"/"变成xx风格" → style_transfer
5. 如果用户说"添加xx" → object_add
6. 如果用户说"删除xx"/"去掉xx" → object_remove
7. 如果用户说"撤回"/"撤销" → undo
8. 如果用户说"重做" → redo
9. 如果用户说"对比"/"比较" → compare
10. 其他修改 → edit_image"""


async def classify_intent(state: ImageEditState) -> dict:
    llm = DoubaoLLM()

    has_image = state.get("current_image_url") is not None
    has_mask = state.get("mask_image_id") is not None

    user_prompt = f"""用户指令：{state['user_instruction']}
当前是否有图：{'true' if has_image else 'false'}
是否有 mask：{'true' if has_mask else 'false'}
是否有参考图：{'true' if state.get('reference_image_ids') else 'false'}"""

    result = await llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    intent_result = IntentResult(**result)

    if intent_result.intent in (Intent.undo, Intent.redo, Intent.compare):
        operation = "version_op"
    else:
        operation = "image_op"

    return {
        "intent": intent_result.intent.value,
        "operation": operation,
        "edit_scope": intent_result.edit_scope.value if intent_result.edit_scope else None,
        "constraints": intent_result.preserve,
    }
