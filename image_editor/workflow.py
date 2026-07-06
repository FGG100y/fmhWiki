from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from image_editor.agents.prompt_enhancer import enhance_prompt
from image_editor.agents.visual_qa import (
    route_by_qa,
    visual_qa,
)
from image_editor.config import config
from image_editor.models import EditRequest, GenerateRequest, Intent
from image_editor.state import ImageEditState, create_initial_state
from image_editor.storage import store
from image_editor.tools.base import registry
from image_editor.tools.router import resolve_task_type, select_tool

logger = logging.getLogger(__name__)


async def load_session(state: ImageEditState) -> dict:
    session = store.get_session(state["session_id"])
    if not session:
        raise ValueError(f"Session {state['session_id']} not found")
    current_turn_id = state.get("current_turn_id") or session.get("current_turn_id")
    current_image_id = state.get("current_image_id")
    current_image_url = state.get("current_image_url")
    if current_turn_id and not current_image_id:
        current_turn = store.get_turn(current_turn_id)
        if current_turn:
            current_image_id = current_turn.output_image_id
            image = (
                store.get_image(current_turn.output_image_id or "")
                if current_turn.output_image_id
                else None
            )
            current_image_url = image.get("url") if image else None
    return {
        "current_turn_id": current_turn_id,
        "current_image_id": current_image_id,
        "current_image_url": current_image_url,
    }


async def safety_check(state: ImageEditState) -> dict:
    instruction = state.get("user_instruction", "")
    logger.info("safety_check: instruction=%s", instruction[:80])
    blocked_keywords = [
        "naked",
        "nude",
        "nsfw",
        "sex",
        "porn",
        "暴力",
        "色情",
        "裸露",
    ]
    for kw in blocked_keywords:
        if kw in instruction.lower():
            return {"error": f"instruction blocked by safety check: {kw}"}
    return {}


async def run_image_tool(state: ImageEditState) -> dict:
    """通过 ToolRouter 选择最优工具执行图像生成/编辑。
    支持执行级 fallback：首选工具失败时自动尝试下一个候选。

    路由策略：
    - 文生图 → doubao（本地模型不支持）
    - inpaint + 有 mask → 按 priority 选本地模型（moebius > lama），fallback doubao
    - edit → doubao
    """
    image_url = state.get("current_image_url") or ""
    mask_url = state.get("mask_image_url")
    prompt = state.get("rewritten_prompt") or state.get("user_instruction", "")
    negative_prompt = state.get("negative_prompt") or ""
    metadata = {
        "session_id": state.get("session_id"),
        "turn_id": state.get("turn_id"),
    }

    task_type = resolve_task_type(
        has_image=bool(image_url),
        has_mask=bool(mask_url),
    )

    # 获取所有候选工具（按 priority 降序排列）
    tool_names = select_tool(
        task_type=task_type,
        has_mask=bool(mask_url),
        enabled_providers=config.enabled_providers(),
        all_candidates=True,
    )

    last_error = None
    for tool_name in tool_names:
        tool = registry.get(tool_name)
        logger.info(
            "run_image_tool: task=%s tool=%s image=%s mask=%s prompt=%s",
            task_type, tool_name, bool(image_url), bool(mask_url), prompt[:80],
        )
        try:
            if task_type == "generate":
                req = GenerateRequest(
                    prompt=prompt,
                    aspect_ratio="2K",
                    metadata={**metadata, "purpose": "image_generate"},
                )
                result = await tool.generate(req)
                intent = Intent.generate_image.value
            elif task_type == "inpaint":
                req = EditRequest(
                    input_image_url=image_url,
                    prompt=prompt,
                    mask_image_url=mask_url,
                    metadata={**metadata, "purpose": "image_inpaint"},
                )
                result = await tool.edit(req)
                intent = Intent.local_edit.value
            else:
                req = EditRequest(
                    input_image_url=image_url,
                    prompt=prompt,
                    metadata={**metadata, "purpose": "image_edit"},
                )
                result = await tool.edit(req)
                intent = Intent.edit_image.value

            logger.info(
                "run_image_tool: done image_id=%s tool=%s size=%sx%s metadata=%s",
                result.image_id, tool_name, result.width, result.height, result.metadata,
            )
            return {
                "output_image_id": result.image_id,
                "output_image_url": result.image_url,
                "intent": intent,
                "selected_tool": tool_name,
                "model_provider": tool_name.split("_")[0],
                "model_name": tool_name,
                "model_params": result.metadata,
            }
        except Exception as e:
            logger.warning(
                "run_image_tool: tool=%s failed, fallback to next candidate: %s",
                tool_name, e,
            )
            last_error = e

    # 所有工具均失败
    error_msg = str(last_error) if last_error else "no candidate tool available"
    raise RuntimeError(f"all tools failed: {error_msg}")


async def persist_turn(state: ImageEditState) -> dict:
    qa = state.get("qa_result") or {}
    turn_id = state.get("turn_id", "")
    logger.info(
        "persist_turn: turn_id=%s intent=%s status=%s",
        turn_id,
        state.get("intent"),
        "succeeded" if not state.get("error") else "failed",
    )
    turn = store.update_turn(
        turn_id,
        intent=state.get("intent"),
        edit_scope=state.get("edit_scope"),
        rewritten_prompt=state.get("rewritten_prompt"),
        negative_prompt=state.get("negative_prompt"),
        preservation_constraints=state.get("constraints", []),
        input_image_id=state.get("current_image_id"),
        output_image_id=state.get("output_image_id"),
        mask_image_id=state.get("mask_image_id"),
        reference_image_ids=state.get("reference_image_ids", []),
        selected_tool=state.get("selected_tool"),
        model_provider=state.get("model_provider"),
        model_name=state.get("model_name"),
        model_params=state.get("model_params", {}),
        status="succeeded" if not state.get("error") else "failed",
        qa_score=qa.get("score"),
        qa_passed=qa.get("passed"),
        qa_result=qa,
        error_message=state.get("error"),
    )
    if turn and turn.output_image_id:
        store.save_image(
            turn.output_image_id,
            state.get("output_image_url", ""),
            metadata={
                "asset_type": "result",
                "turn_id": turn_id,
            },
        )
    if turn and turn.status == "succeeded":
        store.switch_current_turn(state["session_id"], turn_id)
    return {}


async def fail(state: ImageEditState) -> dict:
    logger.error("Workflow failed: %s", state.get("error"))
    store.update_turn(
        state.get("turn_id", ""),
        status="failed",
        error_message=state.get("error"),
    )
    return {}


def route_after_safety(state: ImageEditState) -> Literal["enhance_prompt", "run_image_tool", "fail"]:
    if state.get("error"):
        return "fail"

    image_url = state.get("current_image_url") or ""
    mask_url = state.get("mask_image_url")
    task_type = resolve_task_type(
        has_image=bool(image_url),
        has_mask=bool(mask_url),
    )

    # 文生图和纯编辑始终增强 prompt
    if task_type in ("generate", "edit"):
        return "enhance_prompt"

    # inpaint: 本地模型（moebius/lama）不使用 text prompt，增强无意义
    enabled = config.enabled_providers()
    if "moebius" in enabled or "lama" in enabled:
        return "run_image_tool"

    return "enhance_prompt"


def build_workflow() -> StateGraph:
    workflow = StateGraph(ImageEditState)

    workflow.add_node("load_session", load_session)
    workflow.add_node("safety_check", safety_check)
    workflow.add_node("enhance_prompt", enhance_prompt)
    workflow.add_node("run_image_tool", run_image_tool)
    workflow.add_node("visual_qa", visual_qa)
    workflow.add_node("persist_turn", persist_turn)
    workflow.add_node("fail", fail)

    workflow.set_entry_point("load_session")
    workflow.add_edge("load_session", "safety_check")

    workflow.add_conditional_edges(
        "safety_check",
        route_after_safety,
        {
            "enhance_prompt": "enhance_prompt",
            "run_image_tool": "run_image_tool",
            "fail": "fail",
        },
    )

    workflow.add_edge("enhance_prompt", "run_image_tool")
    workflow.add_edge("run_image_tool", "visual_qa")

    workflow.add_conditional_edges(
        "visual_qa",
        route_by_qa,
        {
            "pass": "persist_turn",
            "retry": "run_image_tool",
            "fail": "persist_turn",
        },
    )

    workflow.add_edge("persist_turn", END)
    workflow.add_edge("fail", END)

    return workflow.compile()


async def run_workflow(
    user_id: str,
    project_id: str,
    session_id: str,
    instruction: str,
    current_turn_id: str | None = None,
    current_image_id: str | None = None,
    current_image_url: str | None = None,
    reference_image_ids: list[str] | None = None,
    mask_image_id: str | None = None,
    mask_image_url: str | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    if not turn_id:
        raise ValueError("turn_id is required")

    graph = build_workflow()

    initial = create_initial_state(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        instruction=instruction,
        current_turn_id=current_turn_id,
        current_image_id=current_image_id,
        current_image_url=current_image_url,
        reference_image_ids=reference_image_ids,
        mask_image_id=mask_image_id,
        mask_image_url=mask_image_url,
    )

    initial["turn_id"] = turn_id

    async for event in graph.astream(initial):
        for node_name, node_output in event.items():
            if node_output:
                initial.update(node_output)

    return {
        "turn_id": initial.get("turn_id"),
        "output_image_id": initial.get("output_image_id"),
        "output_image_url": initial.get("output_image_url"),
        "intent": initial.get("intent"),
        "rewritten_prompt": initial.get("rewritten_prompt"),
        "qa_result": initial.get("qa_result"),
        "error": initial.get("error"),
    }
