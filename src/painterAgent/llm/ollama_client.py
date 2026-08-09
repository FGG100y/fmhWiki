"""ollama 本地模型 LLM 客户端

通过 ollama 的 OpenAI 兼容接口 (http://localhost:11434/v1) 调用本地模型。
chat_json 做健壮 JSON 解析：去除 markdown 围栏、抽取首个 {...}。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from painterAgent.config import config
from painterAgent.models import ModelCallRecord
from painterAgent.storage import store
from painterAgent.tools.base import registry
from painterAgent.tools.router import Capability, ModelRoute, register_route

logger = logging.getLogger(__name__)


class OllamaLLM:
    """ollama OpenAI 兼容客户端。

    chat_json 做健壮 JSON 解析：先尝试直接解析，失败后去除 markdown
    围栏并抽取首个 JSON 对象；仍失败则抛错（被 fallback 循环吞掉）。
    """

    def __init__(self) -> None:
        cfg = config.ollama
        self.client = AsyncOpenAI(
            api_key="ollama",  # ollama 不需要 key，但 openai SDK 要求非空
            base_url=cfg.base_url,
            max_retries=2,
            timeout=60.0,
        )
        self.model = cfg.model
        self.provider = "ollama"

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        session_id: str | None = None,
        turn_id: str | None = None,
        purpose: str = "llm_reasoning",
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        input_tokens = None
        output_tokens = None
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            if getattr(resp, "usage", None):
                input_tokens = resp.usage.prompt_tokens
                output_tokens = resp.usage.completion_tokens
            return resp.choices[0].message.content or ""
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            store.record_model_call(
                ModelCallRecord(
                    call_id=f"call_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    provider=self.provider,
                    model_name=self.model,
                    endpoint="chat.completions",
                    purpose=purpose,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    created_at=datetime.utcnow().isoformat(),
                )
            )

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        session_id: str | None = None,
        turn_id: str | None = None,
        purpose: str = "llm_reasoning",
    ) -> dict[str, Any]:
        text = await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            session_id=session_id,
            turn_id=turn_id,
            purpose=purpose,
        )
        return self._parse_json(text)

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """健壮 JSON 解析：直接解析 → 去 markdown 围栏 → 抽取首个 {...}"""
        # 1) 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2) 去除 markdown 代码围栏 (```json ... ```)
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = cleaned.replace("```", "")
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            pass

        # 3) 抽取首个 {...} 或 [...] 对象
        for pattern in [r"\{.*\}", r"\[.*\]"]:
            m = re.search(pattern, cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"OllamaLLM: 无法解析 JSON 输出: {text[:200]}")


# ── 注册 ──────────────────────────────────────────────────────────────────────

_ollama_llm = OllamaLLM()
registry.register("ollama_qwen3", _ollama_llm)

register_route(
    ModelRoute(
        name="ollama_qwen3",
        provider="ollama",
        capabilities=frozenset({Capability.prompt_enhance}),
        is_local=True,
        priority=0,  # 由 select() 中的 TEXT_LLM_ORDER 折算覆盖
    )
)
