from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from image_editor.agents.intent import classify_intent
from image_editor.agents.prompt import rewrite_prompt
from image_editor.agents.router import select_tool
from image_editor.agents.visual_qa import (
    route_by_qa,
    visual_qa,
)
from image_editor.state import ImageEditState, create_initial_state
from image_editor.storage import store
from image_editor.tools.base import registry
from image_editor.tools.mask import MaskGenerationTool

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
            image = store.get_image(current_turn.output_image_id or "") if current_turn.output_image_id else None
            current_image_url = image.get("url") if image else None
    return {
        "current_turn_id": current_turn_id,
        "current_image_id": current_image_id,
        "current_image_url": current_image_url,
    }


async def safety_check(state: ImageEditState) -> dict:
    instruction = state.get("user_instruction", "")
    blocked_keywords = [
        "naked", "nude", "nsfw", "sex", "porn",
        "暴力", "色情", "裸露",
    ]
    for kw in blocked_keywords:
        if kw in instruction.lower():
            return {"error": f"instruction blocked by safety check: {kw}"}
    return {}


async def handle_version_op(state: ImageEditState) -> dict:
    intent = state.get("intent", "")
    session = store.get_session(state["session_id"])
    if not session:
        return {"error": "session not found"}

    if intent in ("undo", "撤销"):
        parent = store.undo(state["session_id"])
        return {"current_turn_id": parent, "current_image_id": None}

    if intent in ("redo", "重做"):
        redone = store.redo(state["session_id"])
        return {"current_turn_id": redone}

    return {}


async def run_image_tool(state: ImageEditState) -> dict:
    tool_name = state.get("selected_tool")
    if not tool_name:
        return {"error": "no tool selected"}

    if tool_name == "mask_generation":
        tool = MaskGenerationTool()
        mask_url = await tool.create_blank_mask(
            image_url=state.get("current_image_url", ""),
        )
        mask_image_id = f"img_{uuid.uuid4().hex[:12]}"
        store.save_image(mask_image_id, mask_url, metadata={"asset_type": "mask"})
        return {
            "mask_image_id": mask_image_id,
            "mask_image_url": mask_url,
            "selected_tool": "doubao_inpaint",
        }

    if tool_name not in ("doubao_generate", "doubao_edit", "doubao_inpaint"):
        return {"error": f"unsupported tool: {tool_name}"}

    tool = registry.get(tool_name)
    image_url = state.get("current_image_url", "")

    from image_editor.models import EditRequest, GenerateRequest

    if tool_name == "doubao_generate":
        req = GenerateRequest(
            prompt=state.get("rewritten_prompt", state["user_instruction"]),
            negative_prompt=state.get("negative_prompt", ""),
            aspect_ratio=state.get("model_params", {}).get("size", "1:1"),
            seed=state.get("model_params", {}).get("seed"),
            metadata={
                "session_id": state.get("session_id"),
                "turn_id": state.get("turn_id"),
                "purpose": "image_generate",
            },
        )
        result = await tool.generate(req)
    else:
        req = EditRequest(
            input_image_url=image_url,
            prompt=state.get("rewritten_prompt", state["user_instruction"]),
            negative_prompt=state.get("negative_prompt", ""),
            mask_image_url=state.get("mask_image_url"),
            reference_image_urls=[],
            strength=state.get("model_params", {}).get("strength"),
            metadata={
                "session_id": state.get("session_id"),
                "turn_id": state.get("turn_id"),
                "purpose": "image_edit",
            },
        )
        if tool_name == "doubao_inpaint" and hasattr(tool, "inpaint"):
            result = await tool.inpaint(
                image_url=image_url,
                mask_url=state.get("mask_image_url", ""),
                prompt=req.prompt,
                negative_prompt=req.negative_prompt or "",
                metadata={
                    "session_id": state.get("session_id"),
                    "turn_id": state.get("turn_id"),
                    "purpose": "image_inpaint",
                },
            )
        else:
            result = await tool.edit(req)

    return {
        "output_image_id": result.image_id,
        "output_image_url": result.image_url,
    }


async def persist_turn(state: ImageEditState) -> dict:
    qa = state.get("qa_result") or {}
    turn_id = state.get("turn_id", "")
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


def route_by_intent(
    state: ImageEditState,
) -> Literal["version_op", "image_op", "fail"]:
    op = state.get("operation")
    if state.get("error"):
        return "fail"
    if op == "version_op":
        return "version_op"
    return "image_op"


def build_workflow() -> StateGraph:
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
            "fail": "fail",
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
