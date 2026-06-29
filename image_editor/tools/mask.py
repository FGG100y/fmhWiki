"""Mask 生成工具 — 用于局部编辑时自动生成或处理 mask"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from image_editor.config import config
from image_editor.tools.base import registry


class MaskGenerationTool:
    """Mask 生成工具

    功能：
    1. 根据用户描述的"对象区域"生成粗略 mask
    2. 实际生产环境应由前端圈选或 SAM 模型生成
    3. 此处提供基础实现以供局部编辑流程跑通
    """

    def __init__(self) -> None:
        self.output_dir = Path(config.image_tool.output_dir) / "masks"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def create_blank_mask(
        self,
        image_url: str,
        width: int = 1024,
        height: int = 1024,
    ) -> str:
        """创建一个全白 mask（默认编辑整张图）"""
        mask = Image.new("L", (width, height), 255)
        mask_id = f"mask_{uuid.uuid4().hex[:12]}"
        path = self.output_dir / f"{mask_id}.png"
        mask.save(path)
        return str(path)

    async def create_region_mask(
        self,
        image_url: str,
        region_description: str,
    ) -> str:
        """根据区域描述生成 mask

        实际应接入 SAM/Grounded-SAM 或接收前端圈选坐标。
        这里返回全图 mask 作为 fallback。
        """
        return await self.create_blank_mask(image_url)

    async def download_mask(self, mask_url: str) -> str:
        """下载外部 mask 并保存"""
        mask_id = f"mask_{uuid.uuid4().hex[:12]}"
        path = self.output_dir / f"{mask_id}.png"
        try:
            resp = httpx.get(mask_url, timeout=30)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        except Exception:
            mask = Image.new("L", (1024, 1024), 255)
            mask.save(path)
        return str(path)


registry.register("mask_generation", MaskGenerationTool())
