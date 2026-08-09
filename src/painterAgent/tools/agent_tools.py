"""规划工具 — 供 agentic 规划模型调用的 3 个语义化工具。

薄封装：语义化参数 → 内部委托现有 router/registry（保持优先级选择与 fallback）。
规划模型只接触这 3 个工具，不直接操作底层 ImageToolRegistry。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from painterAgent.config import config
from painterAgent.models import EditRequest, GenerateRequest
from painterAgent.llm.aisuite_client import vision_answer
from painterAgent.tools.base import registry
from painterAgent.tools.router import Capability, resolve_task_type, select

logger = logging.getLogger(__name__)


class PlanningTools:
    """规划工具集：封装状态上下文，暴露 3 个语义化工具方法。

    每个方法都是 async def，有完整的 docstring（aisuite 据此生成 tool schema）。
    """

    def __init__(self, session_id: str, turn_id: str, enabled_providers: set[str]):
        self._session_id = session_id
        self._turn_id = turn_id
        self._enabled = enabled_providers

    async def generate_image(self, prompt: str, aspect_ratio: str = "2K") -> dict:
        """文生图：仅依据文本描述新生成一张图片。

        Args:
            prompt: 图片内容描述（英文优先）。
            aspect_ratio: 尺寸，默认 "2K"。

        Returns:
            dict with image_id, image_url, width, height.
        """
        return await self._run_image_op(
            has_image=False, has_mask=False,
            prompt=prompt, aspect_ratio=aspect_ratio,
        )

    async def edit_image(
        self, image_url: str, prompt: str, mask_url: str = "", scope: str = "full"
    ) -> dict:
        """编辑既有图片：可按用户指令整体重绘，或传入 mask_url 仅重绘遮罩区域。

        Args:
            image_url: 上一步产出的图片 URL（即工作记忆中的当前图）。
            prompt: 编辑指令描述。
            mask_url: 局部重绘遮罩 URL；提供则按 inpaint 处理（本地优先）。
            scope: 编辑范围，仅用于语义提示，默认 "full"。

        Returns:
            dict with image_id, image_url, width, height.
        """
        has_mask = bool(mask_url)
        return await self._run_image_op(
            has_image=True, has_mask=has_mask,
            image_url=image_url, prompt=prompt,
            mask_url=mask_url if has_mask else "",
        )

    async def inspect_image(self, image_url: str, question: str) -> str:
        """查看图片并返回文字化描述，用于评估上一步编辑是否达标。

        Args:
            image_url: 要检查的图片 URL。
            question: 针对该图的检查问题。

        Returns:
            文字评价（如"人物衣服仍是蓝色，背景未改变"）。
        """
        t0 = time.monotonic()
        try:
            answer = await vision_answer(
                model=config.agentic.vision_model,
                image_url=image_url,
                question=question,
            )
            logger.info(
                "inspect_image: question=%s answer=%s latency=%dms",
                question[:80], answer[:120], int((time.monotonic() - t0) * 1000),
            )
            return answer
        except Exception as exc:
            logger.warning("inspect_image failed: %s", exc)
            return f"[inspect_failed] {exc}"

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    async def _run_image_op(
        self,
        has_image: bool,
        has_mask: bool,
        prompt: str,
        image_url: str = "",
        mask_url: str = "",
        aspect_ratio: str = "2K",
    ) -> dict:
        """统一的图片操作执行器：推断能力 → 选择工具 → 执行（含 fallback）"""
        capability = resolve_task_type(has_image=has_image, has_mask=has_mask)
        tool_names = select(
            capability,
            has_mask=has_mask,
            enabled_providers=self._enabled,
            all_candidates=True,
        )
        if isinstance(tool_names, str):
            tool_names = [tool_names]

        metadata = {
            "session_id": self._session_id,
            "turn_id": self._turn_id,
        }

        last_error = None
        for tool_name in tool_names:
            tool = registry.get(tool_name)
            t0 = time.monotonic()
            try:
                if capability == Capability.generate:
                    req = GenerateRequest(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        metadata={**metadata, "purpose": "image_generate"},
                    )
                    result = await tool.generate(req)
                elif capability == Capability.inpaint:
                    req = EditRequest(
                        input_image_url=image_url,
                        prompt=prompt,
                        mask_image_url=mask_url,
                        metadata={**metadata, "purpose": "image_inpaint"},
                    )
                    result = await tool.edit(req)
                else:
                    req = EditRequest(
                        input_image_url=image_url,
                        prompt=prompt,
                        metadata={**metadata, "purpose": "image_edit"},
                    )
                    result = await tool.edit(req)

                latency_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    "_run_image_op: tool=%s image_id=%s latency=%dms",
                    tool_name, result.image_id, latency_ms,
                )
                return {
                    "image_id": result.image_id,
                    "image_url": result.image_url,
                    "width": result.width,
                    "height": result.height,
                    "tool_impl": tool_name,
                    "latency_ms": latency_ms,
                }
            except Exception as exc:
                logger.warning(
                    "_run_image_op: tool=%s failed, fallback: %s", tool_name, exc,
                )
                last_error = exc

        raise RuntimeError(
            f"_run_image_op: all {len(tool_names)} candidates failed "
            f"for capability={capability.value}: {last_error}"
        )
