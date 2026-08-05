from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

from PIL import Image

from painterAgent.config import config
from painterAgent.llm.moebius_client import MoebiusClient
from painterAgent.models import EditRequest, EditResult, GenerateRequest, GenerateResult
from painterAgent.tools.base import ImageTool, registry
from painterAgent.tools.router import ToolMeta, register_tool_meta

logger = logging.getLogger(__name__)


class MoebiusImageTool(ImageTool):
    """Moebius 本地 inpainting 工具（仅支持 inpaint/edit，不支持文生图）"""

    def __init__(self) -> None:
        self.client = MoebiusClient()
        self.output_dir = Path(config.image_tool.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        raise NotImplementedError("Moebius 不支持文生图，请使用 doubao_generate")

    async def edit(self, request: EditRequest) -> EditResult:
        if not request.mask_image_url:
            raise ValueError("Moebius edit 需要 mask_image_url，请提供掩码")
        return await self.inpaint(
            image_url=request.input_image_url,
            mask_url=request.mask_image_url,
            prompt=request.prompt,
            seed=request.seed,
            metadata=request.metadata,
        )

    async def inpaint(
        self,
        image_url: str,
        mask_url: str,
        prompt: str = "",
        seed: int = 0,
        metadata: dict | None = None,
    ) -> EditResult:
        """执行 Moebius inpainting"""
        meta = metadata or {}
        result = await self.client.inpaint(
            image_url=image_url,
            mask_url=mask_url,
            prompt=prompt,
            seed=seed or 0,
        )

        image_pil: Image.Image = result["image_pil"]
        image_id = f"img_{uuid.uuid4().hex[:12]}"
        local_path = self._save_pil(image_pil, image_id)

        return EditResult(
            image_id=image_id,
            image_url=f"/output/{image_id}.png",
            width=result["width"],
            height=result["height"],
            metadata={
                "local_path": str(local_path),
                "provider": "moebius",
                "variant": config.moebius.variant,
            },
        )

    def _save_pil(self, image: Image.Image, image_id: str) -> Path:
        """保存 PIL Image 到本地并返回路径"""
        local_path = self.output_dir / f"{image_id}.png"
        image.save(local_path, "PNG")
        return local_path


# 注册工具实例和元数据
_moebius_tool = MoebiusImageTool()
registry.register("moebius_inpaint", _moebius_tool)
registry.register("moebius_edit", _moebius_tool)

register_tool_meta(
    ToolMeta(
        name="moebius_inpaint",
        task_types=frozenset({"inpaint"}),
        requires_mask=True,
        is_local=True,
        priority=10,
    )
)
