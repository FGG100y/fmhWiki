from __future__ import annotations

import uuid
from pathlib import Path

from image_editor.config import config
from image_editor.llm.client import DoubaoImageClient
from image_editor.models import EditRequest, EditResult, GenerateRequest, GenerateResult
from image_editor.tools.base import ImageTool, registry
from image_editor.tools.router import ToolMeta, register_tool_meta


class DoubaoImageTool(ImageTool):
    """豆包 / 火山引擎图片生成与编辑工具"""

    def __init__(self) -> None:
        self.client = DoubaoImageClient()
        self.output_dir = Path(config.image_tool.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _save_result(self, image_data: dict) -> GenerateResult:
        remote_url = image_data.get("url", "")
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        local_path = self._download(remote_url, image_id)
        return GenerateResult(
            image_id=image_id,
            image_url=remote_url,
            seed=image_data.get("seed"),
            width=image_data.get("width", 0),
            height=image_data.get("height", 0),
            metadata={"local_path": str(local_path)},
        )

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
        return self._save_result(resp.get("data", [{}])[0])

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
        r = self._save_result(resp.get("data", [{}])[0])
        return EditResult(
            image_id=r.image_id,
            image_url=r.image_url,
            seed=r.seed,
            width=r.width,
            height=r.height,
            metadata=r.metadata,
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
        r = self._save_result(resp.get("data", [{}])[0])
        return EditResult(
            image_id=r.image_id,
            image_url=r.image_url,
            seed=r.seed,
            width=r.width,
            height=r.height,
            metadata=r.metadata,
        )

    def _parse_size(self, aspect_ratio: str) -> str:
        seedream_sizes = {"2K", "4K"}
        if aspect_ratio in seedream_sizes:
            return aspect_ratio
        mapping = {
            "1:1": "2K",
            "16:9": "2K",
            "9:16": "2K",
            "4:3": "2K",
            "3:4": "2K",
        }
        return mapping.get(aspect_ratio, "2K")

    def _download(self, url: str, image_id: str) -> Path:
        """下载远程图片到本地（实际生产应上传到对象存储）"""
        import base64

        ext = ".png"
        local_path = self.output_dir / f"{image_id}{ext}"
        try:
            if url.startswith("data:"):
                header, encoded = url.split(",", 1)
                data = base64.b64decode(encoded)
                if "image/jpeg" in header:
                    ext = ".jpg"
                elif "image/webp" in header:
                    ext = ".webp"
                local_path = self.output_dir / f"{image_id}{ext}"
                local_path.write_bytes(data)
            else:
                import httpx

                resp = httpx.get(url, timeout=30)
                resp.raise_for_status()
                local_path.write_bytes(resp.content)
        except Exception:
            local_path = self.output_dir / f"{image_id}.txt"
            local_path.write_text(f"模拟下载: {url}")
        return local_path


# 注册工具
_doubao_tool = DoubaoImageTool()
registry.register("doubao_generate", _doubao_tool)
registry.register("doubao_edit", _doubao_tool)
registry.register("doubao_inpaint", _doubao_tool)

# 注册元数据（云端兜底，priority 最低）
register_tool_meta(
    ToolMeta(name="doubao_generate", task_types=frozenset({"generate"}), is_local=False, priority=0)
)
register_tool_meta(
    ToolMeta(name="doubao_edit", task_types=frozenset({"edit"}), is_local=False, priority=0)
)
register_tool_meta(
    ToolMeta(name="doubao_inpaint", task_types=frozenset({"inpaint"}), is_local=False, priority=0)
)
