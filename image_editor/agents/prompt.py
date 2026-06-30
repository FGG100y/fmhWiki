from __future__ import annotations

from image_editor.llm.client import DoubaoLLM
from image_editor.models import PromptResult
from image_editor.state import ImageEditState

SYSTEM_PROMPT = """你是一个图片编辑 prompt 优化助手。将用户口语化指令改写为图像模型更稳定的编辑指令。

输出 JSON 格式，包含以下字段：
- positive_prompt: str — 正向 prompt（英文），详细描述需要做出的修改，保留不应改变的部分
- negative_prompt: str — 负向 prompt（英文），描述不应出现的改变
- preservation_constraints: list[str] — 需要保持不变的关键元素列表
- edit_strength: float — 编辑强度，0.0~1.0

规则：
1. 如果用户要求保留某些区域，必须在 positive_prompt 中明确写明 "keep/remain unchanged"
2. 如果是局部编辑（有 mask），prompt 应聚焦于 mask 区域内的修改
3. 如果是背景替换，要明确 foreground/main subject remain unchanged
4. preservation_constraints 列出用户明确要保留的元素
5. edit_strength: 全局编辑 0.4~0.6，局部编辑 0.7~0.9，风格迁移 0.6~0.8"""


async def rewrite_prompt(state: ImageEditState) -> dict:
    llm = DoubaoLLM()

    constraints_str = ", ".join(state.get("constraints", [])) or "无特殊约束"

    user_prompt = f"""用户指令：{state['user_instruction']}
修改范围：{state.get('edit_scope', 'global')}
约束条件：{constraints_str}
是否有 mask：{'是' if state.get('mask_image_id') else '否'}"""

    result = await llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        session_id=state.get("session_id"),
        turn_id=state.get("turn_id"),
        purpose="prompt_rewrite",
    )

    prompt_result = PromptResult(**result)

    return {
        "rewritten_prompt": prompt_result.positive_prompt,
        "negative_prompt": prompt_result.negative_prompt,
        "constraints": prompt_result.preservation_constraints,
    }
