from __future__ import annotations

from image_editor.llm.client import DoubaoLLM
from image_editor.models import QAResult
from image_editor.state import ImageEditState

SYSTEM_PROMPT = """你是一个图片编辑质量检查助手。判断输出图片是否满足用户要求。

输出 JSON 格式，包含以下字段：
- passed: bool — 是否通过质检
- score: float — 质量评分 0.0~1.0
- issues: list[str] — 发现的问题列表
- retry_suggestion: str — 如果未通过，建议如何改进

检查维度：
1. 是否完成了目标修改
2. 是否破坏了用户要求保持不变的内容
3. 是否有明显畸形、伪影
4. 构图是否稳定

注意：你无法直接看到图片，只能基于文本描述推断。如果没有明显风险，应判为通过。"""


async def visual_qa(state: ImageEditState) -> dict:
    llm = DoubaoLLM()

    user_prompt = f"""用户指令：{state['user_instruction']}
正向 prompt：{state.get('rewritten_prompt', '无')}
负向 prompt：{state.get('negative_prompt', '无')}
约束条件：{', '.join(state.get('constraints', [])) or '无'}
意图：{state.get('intent', '未知')}
编辑范围：{state.get('edit_scope', '未知')}
重试次数：{state.get('retry_count', 0)}"""

    result = await llm.chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        session_id=state.get("session_id"),
        turn_id=state.get("turn_id"),
        purpose="visual_qa",
    )

    qa = QAResult(**result)
    return {"qa_result": qa.model_dump()}


def route_by_qa(state: ImageEditState) -> str:
    qa_data = state.get("qa_result")
    if not qa_data:
        return "pass"
    qa = QAResult(**qa_data)
    if qa.passed:
        return "pass"
    retry_count = state.get("retry_count", 0)
    if retry_count < 2:
        return "retry"
    return "fail"
