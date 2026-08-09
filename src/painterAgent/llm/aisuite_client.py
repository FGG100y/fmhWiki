"""LLM 接入层 — 基于 aisuite 的供应商无关模型调用抽象。

职责：
1. build_provider_configs() — 从环境变量构建供应商凭据映射
2. get_client() — 惰性单例 aisuite.Client
3. vision_answer() — 多模态视觉问答（供 inspect_image 使用）
"""

from __future__ import annotations

import logging
from typing import Optional

import aisuite

from painterAgent.config import config

logger = logging.getLogger(__name__)

_client: Optional[aisuite.Client] = None


def build_provider_configs() -> dict[str, dict]:
    """从环境变量构建 aisuite Client 的 provider_configs（供应商配置注册表）。

    映射关系（环境变量 → provider_config）：
      ARK_API_KEY + ARK_BASE_URL → {"openai": {"api_key": ..., "base_url": ...}}
      OLLAMA_ENABLED=true → {"ollama": {"base_url": ..., "api_key": "ollama"}}
      GOOGLE_API_KEY → {"google": {"api_key": ...}}
    新增供应商只加环境变量，不改代码。
    """
    provider_configs: dict[str, dict] = {}

    # doubao / 火山引擎 ARK（OpenAI 兼容端点）
    if config.doubao.api_key:
        provider_configs["openai"] = {
            "api_key": config.doubao.api_key,
            "base_url": config.doubao.base_url,
        }

    # ollama 本地模型（OpenAI 兼容端点，无 key）
    if config.ollama.enabled:
        provider_configs["ollama"] = {
            "api_key": "ollama",
            "base_url": config.ollama.base_url,
        }

    # 其他供应商（按各自环境变量注册）
    # google: GOOGLE_API_KEY

    logger.debug("build_provider_configs: providers=%s", list(provider_configs.keys()))
    return provider_configs


def get_client() -> aisuite.Client:
    """惰性单例：aisuite Client，复用 provider_configs（进程内缓存）。"""
    global _client
    if _client is None:
        _client = aisuite.Client(provider_configs=build_provider_configs())
        logger.info("aisuite client initialized")
    return _client


async def vision_answer(model: str, image_url: str, question: str) -> str:
    """经 LLM 接入层做多模态问答（供 inspect_image 复用）。

    Args:
        model: provider:model 标识，须支持图像输入。
        image_url: 图片 URL（data URI 或 http URL）。
        question: 针对该图的检查问题。

    Returns:
        文字评价。
    """
    client = get_client()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        logger.info("vision_answer: model=%s question=%s answer=%s", model, question[:60], content[:120])
        return content
    except Exception as exc:
        logger.warning("vision_answer failed (model=%s): %s", model, exc)
        # 视觉 QA 不可用时返回占位文本，不阻塞 agentic 循环
        return f"[visual_qa_unavailable] Unable to inspect image: {exc}"
