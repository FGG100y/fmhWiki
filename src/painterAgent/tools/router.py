"""统一模型路由层

职责：
1. 注册路由元数据（能力、provider、优先级等）
2. 根据能力类型 + 可用 provider 选择最优路由
3. 执行级 fallback：按优先级依序尝试，失败切换

覆盖图片能力（generate/edit/inpaint）与文本能力（prompt_enhance，预留 visual_qa）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Awaitable

from painterAgent.config import config

logger = logging.getLogger(__name__)


# ── 能力枚举 ──────────────────────────────────────────────────────────────────


class Capability(str, Enum):
    """模型能力维度，取代图片专用的 task_type 字符串"""

    generate = "generate"
    edit = "edit"
    inpaint = "inpaint"
    prompt_enhance = "prompt_enhance"
    visual_qa = "visual_qa"  # 预留：需视觉模型


# ── 路由元数据 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelRoute:
    """路由的静态描述，用于选路决策（原 ToolMeta 泛化）"""

    name: str
    provider: str
    capabilities: frozenset[Capability]
    requires_mask: bool = False
    is_local: bool = False
    priority: int = 0


# 向后兼容别名
ToolMeta = ModelRoute


# ── 路由注册表 ────────────────────────────────────────────────────────────────

_route_metas: dict[str, ModelRoute] = {}


def register_route(route: ModelRoute) -> None:
    """注册路由元数据，由各工具/客户端模块在末尾调用"""
    _route_metas[route.name] = route
    caps = ",".join(c.value for c in route.capabilities)
    logger.debug(
        "registered route: %s provider=%s caps=%s priority=%d",
        route.name, route.provider, caps, route.priority,
    )


# 向后兼容别名
register_tool_meta = register_route


def get_route(name: str) -> ModelRoute | None:
    return _route_metas.get(name)


# 向后兼容别名
get_tool_meta = get_route


def all_routes() -> dict[str, ModelRoute]:
    return dict(_route_metas)


# 向后兼容别名
all_tool_metas = all_routes


# ── 任务类型推断 ──────────────────────────────────────────────────────────────


def resolve_task_type(
    has_image: bool,
    has_mask: bool,
) -> Capability:
    """根据输入特征推断图片能力

    返回值: Capability.generate | Capability.edit | Capability.inpaint
    """
    if not has_image:
        return Capability.generate

    if has_mask:
        return Capability.inpaint

    return Capability.edit


# ── 路由选择 ──────────────────────────────────────────────────────────────────

_FALLBACK_MAP: dict[Capability, str] = {
    Capability.generate: "doubao_generate",
    Capability.edit: "doubao_edit",
    Capability.inpaint: "doubao_inpaint",
    Capability.prompt_enhance: "doubao_llm",
}


def _effective_priority(meta: ModelRoute, capability: Capability) -> int:
    """计算有效优先级。

    图片能力直接用 meta.priority；文本 prompt_enhance 按 TEXT_LLM_ORDER
    折算（列表首位 provider = 10，其次 = 9，以此类推）。
    """
    if capability == Capability.prompt_enhance:
        order = config.text_llm_order
        try:
            idx = order.index(meta.provider)
            return 10 - idx  # 首位 10，其余逐次递减
        except ValueError:
            pass
    return meta.priority


def select(
    capability: Capability,
    has_mask: bool = False,
    enabled_providers: set[str] | None = None,
    all_candidates: bool = False,
) -> str | list[str]:
    """按能力选择路由。

    过滤规则：capability 匹配 + requires_mask 满足 + provider 已启用（不再仅限本地）。
    按 effective_priority 降序；无候选时返回 _FALLBACK_MAP[capability]。
    """
    enabled = enabled_providers or set()

    candidates: list[tuple[int, str]] = []
    for name, meta in _route_metas.items():
        if capability not in meta.capabilities:
            continue
        if meta.requires_mask and not has_mask:
            continue
        if meta.provider not in enabled:
            continue
        priority = _effective_priority(meta, capability)
        candidates.append((priority, name))

    if not candidates:
        fallback = _FALLBACK_MAP.get(capability, "doubao_edit")
        logger.info(
            "select: no candidate for capability=%s, fallback=%s",
            capability.value, fallback,
        )
        return [fallback] if all_candidates else fallback

    candidates.sort(reverse=True)

    if all_candidates:
        result = [name for _, name in candidates]
        logger.info(
            "select: capability=%s has_mask=%s enabled=%s candidates=%s",
            capability.value, has_mask, enabled, result,
        )
        return result

    chosen = candidates[0][1]
    logger.info("select: capability=%s chosen=%s", capability.value, chosen)
    return chosen


# 向后兼容包装：接受 str 类型的 task_type
def select_tool(
    task_type: str,
    has_mask: bool,
    enabled_providers: set[str] | None = None,
    all_candidates: bool = False,
) -> str | list[str]:
    """兼容旧调用方（task_type 为 str），内部转为 Capability"""
    cap = Capability(task_type)
    return select(cap, has_mask=has_mask, enabled_providers=enabled_providers,
                  all_candidates=all_candidates)


# ── 执行级兜底 ────────────────────────────────────────────────────────────────


async def invoke_with_fallback(
    capability: Capability,
    invoke: Callable[[Any], Awaitable[Any]],
    enabled_providers: set[str],
    has_mask: bool = False,
) -> Any:
    """按候选顺序依次调用 invoke(client)，失败切换，全败抛错。

    Args:
        capability: 路由能力维度。
        invoke: 异步回调，签名为 async def invoke(client) -> Any；
                client 来自 ModelRegistry.get(route_name)。
        enabled_providers: 当前可用的 provider 集合。
        has_mask: 是否涉及 mask（影响 requires_mask 过滤）。

    Returns:
        首次成功的 invoke(client) 返回值。

    Raises:
        RuntimeError: 所有候选均失败。
    """
    route_names = select(
        capability,
        has_mask=has_mask,
        enabled_providers=enabled_providers,
        all_candidates=True,
    )
    if isinstance(route_names, str):
        route_names = [route_names]

    # 延迟导入避免循环依赖
    from painterAgent.tools.base import registry

    last_error = None
    for name in route_names:
        client = registry.get(name)
        logger.info(
            "invoke_with_fallback: capability=%s route=%s",
            capability.value, name,
        )
        try:
            return await invoke(client)
        except Exception as exc:
            logger.warning(
                "invoke_with_fallback: route=%s failed, fallback to next: %s",
                name, exc,
            )
            last_error = exc

    raise RuntimeError(
        f"invoke_with_fallback: all {len(route_names)} candidates "
        f"failed for capability={capability.value}: {last_error}"
    )
