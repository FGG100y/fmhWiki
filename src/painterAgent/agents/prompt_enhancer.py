from __future__ import annotations

import logging

from painterAgent.config import config
from painterAgent.state import ImageEditState
from painterAgent.tools.router import Capability, invoke_with_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a prompt engineer specialized in text-to-image generation. Your job is to convert a user's natural language description into a high-quality image generation prompt.

## Rules
1. If the input is in Chinese, translate it to English first.
2. Expand vague descriptions into detailed, concrete visual descriptions including: subject, setting, lighting, composition, mood, color palette, art style.
3. Append quality keywords at the end: "high quality, detailed, professional, 8K".
4. Do NOT invent content the user didn't ask for. Do NOT add people, objects, or scenes the user didn't mention.
5. Keep the rewritten prompt under 300 characters.

## Negative Prompt
Generate a concise negative prompt listing common image artifacts to avoid: blurry, low quality, watermark, text, signature, distorted, deformed, ugly, bad anatomy, extra limbs, mutated, oversaturated.

## Output Format
Return a JSON object with exactly these two fields:
- "rewritten_prompt": the enhanced English prompt string
- "negative_prompt": the negative prompt string

## Examples

User: 秋天的咖啡馆
Output: {"rewritten_prompt": "A cozy coffee shop interior in autumn afternoon, golden sunlight streaming through window, fallen leaves visible outside, warm amber color palette, steaming latte on wooden table, soft bokeh, photorealistic, high quality, detailed, professional, 8K", "negative_prompt": "blurry, low quality, watermark, text, signature, distorted, deformed, people, oversaturated"}

User: 一只猫在赛博朋克城市里
Output: {"rewritten_prompt": "A cat walking through a cyberpunk city street at night, neon lights reflecting on wet pavement, flying cars in distant sky, blue and pink neon glow, cinematic composition, detailed fur texture, high quality, detailed, professional, 8K", "negative_prompt": "blurry, low quality, watermark, text, signature, distorted, deformed, ugly, bad anatomy, oversaturated"}

User: minimalist logo for a coffee brand, flat design, vector style
Output: {"rewritten_prompt": "Minimalist logo design for a coffee brand, flat vector illustration style, clean geometric shapes, monoline, simple elegant icon, coffee bean or cup silhouette, on white background, high quality, professional, 8K", "negative_prompt": "blurry, low quality, watermark, text, signature, photorealistic, 3D, gradients, shadows, complex background"}
"""


async def enhance_prompt(state: ImageEditState) -> dict:
    """使用统一路由（invoke_with_fallback）增强用户输入的 prompt。

    按 TEXT_LLM_ORDER 配置的优先级依次尝试候选文本 LLM（如 ollama+qwen3 →
    doubao LLM），失败自动切换。全部失败时回退到原始指令。
    """
    instruction = state.get("user_instruction", "")
    if not instruction.strip():
        return {"rewritten_prompt": instruction, "negative_prompt": ""}

    session_id = state.get("session_id")
    turn_id = state.get("turn_id")

    async def _invoke(client) -> dict:
        return await client.chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=instruction,
            session_id=session_id,
            turn_id=turn_id,
            purpose="prompt_enhance",
        )

    try:
        result = await invoke_with_fallback(
            capability=Capability.prompt_enhance,
            invoke=_invoke,
            enabled_providers=config.enabled_providers(),
        )
        rewritten = result.get("rewritten_prompt", instruction)
        negative = result.get("negative_prompt", "")
        logger.info(
            "enhance_prompt: original=%s rewritten=%s",
            instruction[:80],
            rewritten[:80],
        )
        return {"rewritten_prompt": rewritten, "negative_prompt": negative}
    except Exception as e:
        logger.warning("enhance_prompt: all candidates failed, falling back to original: %s", e)
        return {"rewritten_prompt": instruction, "negative_prompt": ""}
