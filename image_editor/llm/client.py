from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx
from openai import AsyncOpenAI

from image_editor.config import config
from image_editor.models import ModelCallRecord
from image_editor.storage import store

logger = logging.getLogger(__name__)


class DoubaoLLM:
    """豆包大模型 LLM 客户端 (兼容 OpenAI SDK)"""

    def __init__(self) -> None:
        cfg = config.doubao
        self.client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            max_retries=cfg.max_retries,
            timeout=cfg.request_timeout,
        )
        self.model = cfg.model

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        response_format: Optional[dict] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        purpose: str = "llm_reasoning",
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        input_tokens = None
        output_tokens = None
        try:
            resp = await self.client.chat.completions.create(**kwargs)
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
                    provider="doubao",
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
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        purpose: str = "llm_reasoning",
    ) -> dict[str, Any]:
        text = await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
            session_id=session_id,
            turn_id=turn_id,
            purpose=purpose,
        )
        return json.loads(text)

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


class DoubaoImageClient:
    """豆包 / 火山引擎 图片生成客户端 (ARK Image API)
    统一使用 DOUBAO_MODEL (Seedream 5.0) 作为多模态模型。
    """

    def __init__(self) -> None:
        cfg = config.doubao
        self.api_key = cfg.api_key
        self.model = cfg.model
        self.http = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=cfg.request_timeout,
        )

    def _base_body(
        self, prompt: str, size: str, image_url: str = "", mask_url: str = ""
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "sequential_image_generation": "disabled",
            "response_format": "url",
            "stream": False,
            "watermark": True,
        }
        if image_url:
            body["image"] = image_url
        if mask_url:
            body["mask"] = mask_url
        return body

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: str = "2K",
        seed: Optional[int] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        purpose: str = "image_generate",
    ) -> dict[str, Any]:
        body = self._base_body(prompt, size)

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        try:
            logger.debug("images/generations (create): model=%s", self.model)
            resp = await self.http.post("images/generations", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.error("images/generations failed: %s", exc)
            raise
        finally:
            store.record_model_call(
                ModelCallRecord(
                    call_id=f"call_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    provider="doubao",
                    model_name=self.model,
                    endpoint="images/generations",
                    purpose=purpose,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    status=status,
                    error_message=error_message,
                    created_at=datetime.utcnow().isoformat(),
                    metadata={"size": size, "seed": seed},
                )
            )

    async def edit(
        self,
        image_url: str,
        prompt: str,
        mask_url: Optional[str] = None,
        size: str = "2K",
        seed: Optional[int] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        purpose: str = "image_edit",
    ) -> dict[str, Any]:
        body = self._base_body(
            prompt, size, image_url=image_url, mask_url=mask_url or ""
        )

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        try:
            logger.debug(
                "images/generations (edit): model=%s has_image=%s",
                self.model,
                bool(image_url),
            )
            resp = await self.http.post("images/generations", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.error("images/generations (edit) failed: %s", exc)
            raise
        finally:
            store.record_model_call(
                ModelCallRecord(
                    call_id=f"call_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    provider="doubao",
                    model_name=self.model,
                    endpoint="images/generations",
                    purpose=purpose,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    status=status,
                    error_message=error_message,
                    created_at=datetime.utcnow().isoformat(),
                    metadata={"size": size, "seed": seed, "has_mask": bool(mask_url)},
                )
            )

    async def inpainting(
        self,
        image_url: str,
        mask_url: str,
        prompt: str,
        negative_prompt: str = "",
        seed: Optional[int] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        purpose: str = "image_inpaint",
    ) -> dict[str, Any]:
        body = self._base_body(prompt, "2K", image_url=image_url, mask_url=mask_url)

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        try:
            logger.debug("images/generations (inpaint): model=%s", self.model)
            resp = await self.http.post("images/generations", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.error("images/generations (inpaint) failed: %s", exc)
            raise
        finally:
            store.record_model_call(
                ModelCallRecord(
                    call_id=f"call_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    provider="doubao",
                    model_name=self.model,
                    endpoint="images/generations",
                    purpose=purpose,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    status=status,
                    error_message=error_message,
                    created_at=datetime.utcnow().isoformat(),
                    metadata={"seed": seed},
                )
            )

    async def close(self) -> None:
        await self.http.aclose()
