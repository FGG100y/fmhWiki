"""错误码与用户友好提示映射层。

后端内部异常/英文原始错误 → 面向用户的中文提示 + 稳定错误码。
"""

from __future__ import annotations

SAFETY_PREFIX = "instruction blocked by safety check:"


def to_user_error(error: str | None) -> tuple[str, str]:
    """将原始错误信息映射为 (error_code, 中文提示)。"""
    if not error:
        return "unknown", "处理失败，请稍后重试"

    low = error.lower()

    if error.startswith(SAFETY_PREFIX) or "safety check" in low:
        return "safety_blocked", "指令包含敏感内容，已被安全策略拦截，请调整措辞后重试"
    if (
        "api key" in low
        or "api_key" in low
        or "apikey" in low
        or "ark_api_key" in low
        or "unauthorized" in low
        or "authentication" in low
        or "credential" in low
        or "401" in low
        or "403" in low
    ):
        return "auth_error", "图像服务未正确配置（API Key 缺失或无效），请检查 ARK_API_KEY 后重试"
    if "rate limit" in low or "429" in low or "too many requests" in low:
        return "rate_limited", "请求过于频繁，请稍后再试"
    if "timeout" in low or "timed out" in low:
        return "timeout", "生成超时，请稍后重试"
    if (
        "connection" in low
        or "network" in low
        or "getaddrinfo" in low
        or "connect" in low
    ):
        return "network_error", "网络连接失败，请检查网络后重试"
    if "content" in low and ("policy" in low or "violat" in low or "reject" in low):
        return "content_rejected", "内容不符合生成规范，请调整指令后重试"

    return "internal_error", "处理失败，请稍后重试"
