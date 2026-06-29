from __future__ import annotations

from image_editor.llm.client import DoubaoLLM
from image_editor.models import Intent, ToolSelection
from image_editor.state import ImageEditState

SYSTEM_PROMPT = """你是一个图片编辑工具路由助手。根据任务需求选择合适的工具和模型。

输出 JSON 格式，包含以下字段：
- tool: str — 推荐工具名称
- reason: str — 选择理由
- fallback_tool: str — 备用工具
- params: dict — 参数字典

路由规则（内置规则优先，LLM 补充判断）：
- generate_image → doubao_generate
- edit_image / background_replace / style_transfer → doubao_edit
- local_edit + 有 mask → doubao_inpaint
- local_edit + 无 mask → 提示需要 mask
- upscale → upscale_tool
- variation → doubao_edit"""


async def select_tool(state: ImageEditState) -> dict:
    intent_str = state.get("intent") or ""
    has_mask = state.get("mask_image_id") is not None

    if intent_str == Intent.generate_image.value:
        return {
            "selected_tool": "doubao_generate",
            "model_provider": "doubao",
            "model_name": "seed-xx-large",
            "model_params": {"size": "1024x1024", "n": 1},
        }

    if intent_str == Intent.local_edit.value:
        if has_mask:
            return {
                "selected_tool": "doubao_inpaint",
                "model_provider": "doubao",
                "model_name": "seed-xx-large-inpaint",
                "model_params": {"strength": 0.85},
            }
        else:
            return {
                "selected_tool": "mask_generation",
                "model_provider": "doubao",
                "model_name": "",
                "model_params": {},
            }

    if intent_str == Intent.upscale.value:
        return {
            "selected_tool": "upscale",
            "model_provider": "doubao",
            "model_name": "",
            "model_params": {"scale": 2},
        }

    if intent_str in (
        Intent.edit_image.value,
        Intent.background_replace.value,
        Intent.style_transfer.value,
        Intent.variation.value,
    ):
        llm = DoubaoLLM()
        user_prompt = f"""用户指令：{state['user_instruction']}
意图：{intent_str}
修改范围：{state.get('edit_scope', 'global')}
是否有参考图：{'是' if state.get('reference_image_ids') else '否'}"""

        result = await llm.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        selection = ToolSelection(**result)
        return {
            "selected_tool": selection.tool,
            "model_provider": "doubao",
            "model_name": "seed-xx-large-edit",
            "model_params": selection.params,
        }

    return {
        "selected_tool": "doubao_edit",
        "model_provider": "doubao",
        "model_name": "seed-xx-large-edit",
        "model_params": {},
    }
