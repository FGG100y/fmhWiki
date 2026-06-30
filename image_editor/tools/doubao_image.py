from __future__ import annotations

import uuid
from pathlib import Path

from image_editor.config import config
from image_editor.llm.client import DoubaoImageClient
from image_editor.models import EditRequest, EditResult, GenerateRequest, GenerateResult
from image_editor.tools.base import ImageTool, registry


class DoubaoImageTool(ImageTool):
    """豆包 / 火山引擎图片生成与编辑工具"""

    def __init__(self) -> None:
        self.client = DoubaoImageClient()
        self.output_dir = Path(config.image_tool.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        metadata = request.metadata or {}
        resp = await self.client.generate(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            size=self._parse_size(request.aspect_ratio),
            seed=request.seed,
            session_id=metadata.get("session_id"),
            turn_id=metadata.get("turn_id"),
            purpose=metadata.get("purpose", "image_generate"),
        )

        image_data = resp.get("data", [{}])[0]
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        url = image_data.get("url", "")

        local_path = self._download(url, image_id)
        return GenerateResult(
            image_id=image_id,
            image_url=str(local_path),
            seed=image_data.get("seed"),
            width=image_data.get("width", 0),
            height=image_data.get("height", 0),
        )

    async def edit(self, request: EditRequest) -> EditResult:
        metadata = request.metadata or {}
        resp = await self.client.edit(
            image_url=request.input_image_url,
            prompt=request.prompt,
            mask_url=request.mask_image_url,
            seed=request.seed,
            session_id=metadata.get("session_id"),
            turn_id=metadata.get("turn_id"),
            purpose=metadata.get("purpose", "image_edit"),
        )

        image_data = resp.get("data", [{}])[0]
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        url = image_data.get("url", "")

        local_path = self._download(url, image_id)
        return EditResult(
            image_id=image_id,
            image_url=str(local_path),
            seed=image_data.get("seed"),
            width=image_data.get("width", 0),
            height=image_data.get("height", 0),
        )

    async def inpaint(
        self,
        image_url: str,
        mask_url: str,
        prompt: str,
        negative_prompt: str = "",
        seed: int | None = None,
        metadata: dict | None = None,
    ) -> EditResult:
        """局部修复（inpainting）"""
        meta = metadata or {}
        resp = await self.client.inpainting(
            image_url=image_url,
            mask_url=mask_url,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            session_id=meta.get("session_id"),
            turn_id=meta.get("turn_id"),
            purpose=meta.get("purpose", "image_inpaint"),
        )

        image_data = resp.get("data", [{}])[0]
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        url = image_data.get("url", "")

        local_path = self._download(url, image_id)
        return EditResult(
            image_id=image_id,
            image_url=str(local_path),
            seed=image_data.get("seed"),
            width=image_data.get("width", 0),
            height=image_data.get("height", 0),
        )

    def _parse_size(self, aspect_ratio: str) -> str:
        mapping = {
            "1:1": "1024x1024",
            "16:9": "1920x1080",
            "9:16": "1080x1920",
            "4:3": "1366x1024",
            "3:4": "1024x1366",
        }
        return mapping.get(aspect_ratio, "1024x1024")

    def _download(self, url: str, image_id: str) -> Path:
        """下载远程图片到本地（实际生产应上传到对象存储）"""
        import httpx

        ext = ".png"
        local_path = self.output_dir / f"{image_id}{ext}"
        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
        except Exception:
            local_path = self.output_dir / f"{image_id}.txt"
            local_path.write_text(f"模拟下载: {url}")
        return local_path


# 注册工具
registry.register("doubao_generate", DoubaoImageTool())
registry.register("doubao_edit", DoubaoImageTool())
registry.register("doubao_inpaint", DoubaoImageTool())
