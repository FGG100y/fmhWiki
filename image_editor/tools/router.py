"""模型路由层

职责：
1. 注册工具元数据（支持的任务类型、是否需要 mask、优先级等）
2. 根据任务类型 + 可用 provider 选择最优工具
3. 接入新模型只需：新建工具文件 → register_tool_meta() → import 即可
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── 工具元数据 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolMeta:
    """工具的静态描述，用于路由决策"""

    name: str
    task_types: frozenset[str]
    requires_mask: bool = False
    is_local: bool = False
    priority: int = 0


# ── 元数据注册表 ──────────────────────────────────────────────────────────────

_tool_metas: dict[str, ToolMeta] = {}


def register_tool_meta(meta: ToolMeta) -> None:
    """注册工具元数据，由各工具模块在末尾调用"""
    _tool_metas[meta.name] = meta
    logger.debug("registered tool meta: %s tasks=%s", meta.name, meta.task_types)


def get_tool_meta(name: str) -> ToolMeta | None:
    return _tool_metas.get(name)


def all_tool_metas() -> dict[str, ToolMeta]:
    return dict(_tool_metas)


# ── 任务类型推断 ──────────────────────────────────────────────────────────────


def resolve_task_type(
    has_image: bool,
    has_mask: bool,
) -> str:
    """根据输入特征推断任务类型

    返回值: "generate" | "edit" | "inpaint"
    """
    if not has_image:
        return "generate"

    if has_mask:
        return "inpaint"

    return "edit"


# ── 工具选择 ──────────────────────────────────────────────────────────────────

_FALLBACK_MAP: dict[str, str] = {
    "generate": "doubao_generate",
    "edit": "doubao_edit",
    "inpaint": "doubao_inpaint",
}


def select_tool(
    task_type: str,
    has_mask: bool,
    enabled_providers: set[str] | None = None,
    all_candidates: bool = False,
) -> str | list[str]:
    """路由策略

    1. 文生图 → doubao（本地模型不支持）
    2. inpaint + 有 mask → 按 priority 选本地模型（moebius > lama），fallback doubao
    3. edit → doubao
    """
    enabled = enabled_providers or set()

    candidates: list[tuple[int, str]] = []
    for name, meta in _tool_metas.items():
        if task_type not in meta.task_types:
            continue
        if meta.requires_mask and not has_mask:
            continue
        if meta.is_local:
            provider_key = name.split("_")[0]
            if provider_key not in enabled:
                continue
        candidates.append((meta.priority, name))

    if not candidates:
        fallback = _FALLBACK_MAP.get(task_type, "doubao_edit")
        logger.info("select_tool: no candidate for task=%s, fallback=%s", task_type, fallback)
        return [fallback] if all_candidates else fallback

    candidates.sort(reverse=True)

    if all_candidates:
        result = [name for _, name in candidates]
        logger.info("select_tool: task=%s candidates=%s", task_type, result)
        return result

    chosen = candidates[0][1]
    logger.info("select_tool: task=%s chosen=%s", task_type, chosen)
    return chosen
