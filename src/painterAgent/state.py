from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import StateGraph
from typing_extensions import TypedDict


class ImageEditState(TypedDict):
    user_id: str
    project_id: str
    session_id: str

    user_instruction: str
    current_turn_id: Optional[str]
    current_image_id: Optional[str]
    current_image_url: Optional[str]
    reference_image_ids: list[str]
    mask_image_id: Optional[str]
    mask_image_url: Optional[str]

    intent: Optional[str]
    operation: Optional[str]
    edit_scope: Optional[str]
    constraints: list[str]
    rewritten_prompt: Optional[str]
    negative_prompt: Optional[str]

    selected_tool: Optional[str]
    model_provider: Optional[str]
    model_name: Optional[str]
    model_params: dict[str, Any]

    output_image_id: Optional[str]
    output_image_url: Optional[str]
    qa_result: Optional[dict[str, Any]]
    retry_count: int
    error: Optional[str]
    job_id: Optional[str]
    turn_id: Optional[str]

    # agentic 模式相关
    execution_mode: Optional[str]  # auto / agentic / deterministic
    degraded: bool  # agentic 降级标记
    agent_steps: list[dict[str, Any]]  # AgentStep 序列化
    agent_reply: Optional[str]  # 规划模型最终文本回复


def create_initial_state(
    user_id: str,
    project_id: str,
    session_id: str,
    instruction: str,
    current_turn_id: Optional[str] = None,
    current_image_id: Optional[str] = None,
    current_image_url: Optional[str] = None,
    reference_image_ids: Optional[list[str]] = None,
    mask_image_id: Optional[str] = None,
    mask_image_url: Optional[str] = None,
) -> ImageEditState:
    return {
        "user_id": user_id,
        "project_id": project_id,
        "session_id": session_id,
        "user_instruction": instruction,
        "current_turn_id": current_turn_id,
        "current_image_id": current_image_id,
        "current_image_url": current_image_url,
        "reference_image_ids": reference_image_ids or [],
        "mask_image_id": mask_image_id,
        "mask_image_url": mask_image_url,
        "intent": None,
        "operation": None,
        "edit_scope": None,
        "constraints": [],
        "rewritten_prompt": None,
        "negative_prompt": None,
        "selected_tool": None,
        "model_provider": None,
        "model_name": None,
        "model_params": {},
        "output_image_id": None,
        "output_image_url": None,
        "qa_result": None,
        "retry_count": 0,
        "error": None,
        "job_id": None,
        "turn_id": None,
        "execution_mode": None,
        "degraded": False,
        "agent_steps": [],
        "agent_reply": None,
    }
