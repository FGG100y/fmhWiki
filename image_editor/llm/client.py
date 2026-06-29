from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx
from openai import AsyncOpenAI

from image_editor.config import config


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

        resp = await self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        text = await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
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
    """豆包 / 火山引擎 图片生成客户端 (ARK Image API)"""

    def __init__(self) -> None:
        cfg = config.doubao
        self.api_key = cfg.api_key
        self.base_url = cfg.base_url.rstrip("/v3").rstrip("/")
        self.http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=cfg.request_timeout,
        )

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: str = "1024x1024",
        n: int = 1,
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": "seed-xx-large",
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if seed is not None:
            body["seed"] = seed

        resp = await self.http.post("/api/v3/images/generations", json=body)
        resp.raise_for_status()
        return resp.json()

    async def edit(
        self,
        image_url: str,
        prompt: str,
        mask_url: Optional[str] = None,
        size: str = "1024x1024",
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": "seed-xx-large-edit",
            "image": image_url,
            "prompt": prompt,
            "size": size,
        }
        if mask_url:
            body["mask"] = mask_url
        if seed is not None:
            body["seed"] = seed

        resp = await self.http.post("/api/v3/images/edits", json=body)
        resp.raise_for_status()
        return resp.json()

    async def inpainting(
        self,
        image_url: str,
        mask_url: str,
        prompt: str,
        negative_prompt: str = "",
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": "seed-xx-large-inpaint",
            "image": image_url,
            "mask": mask_url,
            "prompt": prompt,
            "size": "1024x1024",
        }
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if seed is not None:
            body["seed"] = seed

        resp = await self.http.post("/api/v3/images/inpainting", json=body)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self.http.aclose()
