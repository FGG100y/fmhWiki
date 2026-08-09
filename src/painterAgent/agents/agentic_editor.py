"""Agentic 多步编辑 — 由规划模型自主决定工具调用顺序与次数。

核心入口：run_agentic_edit(state) → 部分 state 更新（含 degraded 降级标记）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from painterAgent.config import config
from painterAgent.llm.aisuite_client import get_client
from painterAgent.state import ImageEditState
from painterAgent.tools.agent_tools import PlanningTools
from painterAgent.agents.demo_learning import (
    build_demonstration,
    build_preference_profile,
    render_demo_prompt,
    render_preference_prompt,
)

logger = logging.getLogger(__name__)

# ── 系统提示（规划模型契约） ──────────────────────────────────────────────────

AGENTIC_SYSTEM_PROMPT = """You are an image editing agent. Your job is to fulfill the user's editing request by calling the available tools in the right order.

## Available Tools
- `generate_image(prompt, aspect_ratio)`: Create a new image from text description.
- `edit_image(image_url, prompt, mask_url, scope)`: Edit an existing image. Provide mask_url for local inpainting.
- `inspect_image(image_url, question)`: Get a text description of an image's current state.

## Rules
1. Break complex requests into **multiple steps**, one tool call per step. Use the previous step's `image_url` as the input for the next step.
2. Before any quality-critical step, call `inspect_image` first to confirm the current state, then decide the next action.
3. When done and the **final result** is produced, summarize the result in Chinese and DO NOT call any more tools.
4. If "用户示范方法" section is provided: **imitate the tool choice, prompt phrasing, and operation order**, but plan for the current instruction — do NOT reuse images from the demo.
5. If "用户长期偏好" section is provided: treat it as the user's **persistent style constraints** (preferred tools, mask habits, prompt language). If demo and preference conflict, demo (recent specific) takes priority over preference (general tendency).

## Working Memory
You cannot "see" the images directly. You must rely on text assessments from `inspect_image` to understand the current image state. The `image_url` returned by tools is your only reference to images.
"""


async def run_agentic_edit(state: ImageEditState) -> dict:
    """agentic_edit 节点：用规划模型 + aisuite 工具循环执行多步编辑。

    Returns:
        Partial state dict。degraded=True 表示需降级到 legacy 路径。
    """
    t0 = time.monotonic()

    # ── 检查能力开关 ──────────────────────────────────────────────────────────
    if not config.agentic.enabled:
        logger.info("run_agentic_edit: disabled by AGENTIC_EDIT_ENABLED=false")
        return {"degraded": True}

    instruction = state.get("user_instruction", "")
    if not instruction.strip():
        return {"degraded": True}

    session_id = state.get("session_id", "")
    turn_id = state.get("turn_id", "")
    project_id = state.get("project_id", "")
    enabled = config.enabled_providers()

    # ── 构建系统提示（偏好在前，示范在后） ────────────────────────────────────
    system_prompt = AGENTIC_SYSTEM_PROMPT

    if config.agentic.pref_enabled:
        profile = build_preference_profile(
            project_id, min_turns=config.agentic.pref_min_turns,
        )
        if profile:
            system_prompt += render_preference_prompt(profile)

    if config.agentic.demo_enabled:
        demo = build_demonstration(
            session_id, turn_id, max_steps=config.agentic.demo_max_steps,
        )
        if demo and demo.rendered:
            system_prompt += demo.rendered

    # ── 创建规划工具 ──────────────────────────────────────────────────────────
    tools_wrapper = PlanningTools(session_id, turn_id, enabled)
    tools = [
        tools_wrapper.generate_image,
        tools_wrapper.edit_image,
        tools_wrapper.inspect_image,
    ]

    # ── 运行 agentic 循环 ─────────────────────────────────────────────────────
    client = get_client()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": instruction},
    ]

    try:
        response = client.chat.completions.create(
            model=config.agentic.planner_model,
            messages=messages,
            tools=tools,
            max_turns=config.agentic.max_turns,
            temperature=0.1,
        )
    except Exception as exc:
        logger.warning("run_agentic_edit: planner call failed: %s", exc)
        return {"degraded": True}

    # ── 提取步迹 ──────────────────────────────────────────────────────────────
    agent_steps = _extract_agent_steps(response)
    agent_reply = ""
    try:
        agent_reply = response.choices[0].message.content or ""
    except Exception:
        pass

    # 检查是否达到工具调用硬上限
    tool_call_count = sum(1 for s in agent_steps if s["tool"])
    if tool_call_count >= config.agentic.max_tool_calls:
        logger.warning(
            "run_agentic_edit: tool call limit reached (%d >= %d)",
            tool_call_count, config.agentic.max_tool_calls,
        )
        return _degrade_if_no_output(agent_steps, agent_reply)

    # 查找最终产物
    output_image_id, output_image_url = _find_final_output(agent_steps)
    if not output_image_id:
        logger.warning("run_agentic_edit: no output image produced")
        return {"degraded": True, "agent_steps": agent_steps, "agent_reply": agent_reply}

    # 检查连续失败
    fail_count = _count_consecutive_failures(agent_steps)
    if fail_count >= config.agentic.consecutive_fail_limit:
        logger.warning(
            "run_agentic_edit: %d consecutive failures >= limit %d",
            fail_count, config.agentic.consecutive_fail_limit,
        )
        return _degrade_if_no_output(agent_steps, agent_reply)

    # ── 成功 ──────────────────────────────────────────────────────────────────
    planner_provider, planner_model = config.agentic.planner_model.split(":", 1)
    total_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "run_agentic_edit: success steps=%d output=%s planner=%s latency=%dms",
        len(agent_steps), output_image_id, config.agentic.planner_model, total_ms,
    )

    return {
        "output_image_id": output_image_id,
        "output_image_url": output_image_url,
        "agent_steps": agent_steps,
        "agent_reply": agent_reply,
        "selected_tool": "agentic",
        "model_provider": planner_provider,
        "model_name": planner_model,
        "model_params": {},
        "degraded": False,
        "execution_mode": "agentic",
    }


# ── 辅助函数 ──────────────────────────────────────────────────────────────────


def _extract_agent_steps(response: Any) -> list[dict[str, Any]]:
    """从 aisuite 响应中提取 agent_steps。

    遍历 intermediate_messages，匹配 tool_calls → tool_results 成步迹。
    """
    steps: list[dict[str, Any]] = []

    try:
        intermediate = getattr(response.choices[0], "intermediate_messages", None)
        if not intermediate:
            return steps
    except Exception:
        return steps

    step_index = 0
    pending_tool_calls: dict[str, dict] = {}  # tool_call_id → partial step

    for msg in intermediate:
        # 助手消息中的 tool_calls
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_id = getattr(tc, "id", "")
                func = getattr(tc, "function", None)
                if not func:
                    continue
                func_name = getattr(func, "name", "")
                try:
                    import json
                    func_args = json.loads(getattr(func, "arguments", "{}"))
                except Exception:
                    func_args = {}

                step_index += 1
                pending_tool_calls[tc_id] = {
                    "index": step_index,
                    "tool": func_name,
                    "args": func_args,
                    "result": {},
                    "tool_impl": "",
                    "status": "succeeded",
                    "error": "",
                    "latency_ms": 0,
                    "created_at": datetime.utcnow().isoformat(),
                }

        # 工具结果
        tool_name = getattr(msg, "name", None)
        tc_id = getattr(msg, "tool_call_id", "")
        if tool_name and tc_id in pending_tool_calls:
            step = pending_tool_calls.pop(tc_id)
            content = getattr(msg, "content", "")
            # 尝试解析 JSON 结果（图片操作返回 dict）
            try:
                import json
                result = json.loads(content)
            except Exception:
                # 文本结果（inspect_image）
                result = {"assessment": content} if content else {}
            step["result"] = result
            if isinstance(result, dict):
                step["tool_impl"] = result.get("tool_impl", "")
                step["latency_ms"] = result.get("latency_ms", 0)
                if result.get("error"):
                    step["status"] = "failed"
                    step["error"] = result.get("error", "")
            steps.append(step)

    # 未匹配的 tool_calls（模型调用了但无结果）
    for step in pending_tool_calls.values():
        step["status"] = "failed"
        step["error"] = "no result"
        steps.append(step)

    return sorted(steps, key=lambda s: s["index"])


def _find_final_output(steps: list[dict[str, Any]]) -> tuple[str, str]:
    """从步迹中找到最终产物（最后一张成功产出的图片）"""
    for step in reversed(steps):
        if step["status"] != "succeeded":
            continue
        result = step["result"]
        if isinstance(result, dict) and result.get("image_id"):
            return result["image_id"], result.get("image_url", "")
    return "", ""


def _count_consecutive_failures(steps: list[dict[str, Any]]) -> int:
    """从尾部计连续失败数"""
    count = 0
    for step in reversed(steps):
        if step["status"] == "failed":
            count += 1
        else:
            break
    return count


def _degrade_if_no_output(steps: list, reply: str) -> dict:
    """如果有产物则返回成功，否则降级"""
    output_id, output_url = _find_final_output(steps)
    if output_id:
        return {
            "output_image_id": output_id,
            "output_image_url": output_url,
            "agent_steps": steps,
            "agent_reply": reply,
            "selected_tool": "agentic",
            "degraded": False,
            "execution_mode": "agentic",
        }
    return {"degraded": True, "agent_steps": steps, "agent_reply": reply}
