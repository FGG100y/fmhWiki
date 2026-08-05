from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from PIL import Image

from painterAgent.config import config
from painterAgent.models import EditRequest, EditResult, GenerateRequest, GenerateResult
from painterAgent.tools.base import ImageTool, registry
from painterAgent.tools.router import ToolMeta, register_tool_meta

logger = logging.getLogger(__name__)


def _convert_mask_to_l(mask: Image.Image) -> Image.Image:
    """将任意格式的 mask 图片正确转换为 L 模式（灰度图）。

    前端绘制 mask 以红色笔触绘于黑色画布，导出为 RGBA PNG 时：
    - R 通道包含 mask 强度（0=无遮罩, 255=完全遮罩）
    - G/B 通道均为 0
    - A 通道均为 255（与黑色底合成后全不透明）

    PIL 默认 RGBA→L 转换使用亮度公式 L=0.299R+0.587G+0.716B，
    会削弱 mask 强度（最大值从 255 降到 76），导致 inpainting 效果微弱。
    此函数检测并纠正该问题。
    """
    if mask.mode == "L":
        return mask

    if mask.mode in ("RGBA", "RGB"):
        bands = mask.split()
        r, g, b = bands[0], bands[1], bands[2]
        a = bands[3] if mask.mode == "RGBA" else None

        # Alpha 通道有变化 → 用 alpha 作为 mask
        if a is not None:
            a_extrema = a.getextrema()
            if a_extrema[0] != a_extrema[1]:
                return a

        # G/B 全为 0 且 alpha 全为 255（整体不透明）→ mask 数据在 R 通道（前端绘制格式）
        g_extrema = g.getextrema()
        b_extrema = b.getextrema()
        a_is_solid_255 = a is not None and a.getextrema() == (255, 255)
        if g_extrema == (0, 0) and b_extrema == (0, 0) and (a is None or a_is_solid_255):
            return r

    return mask.convert("L")


class LamaImageTool(ImageTool):
    """LaMa 物体移除工具（纯上下文填充，不需要 text prompt）

    特点：
    - 极轻量（~45MB），CPU/GPU 均可运行
    - 适合"删除物体"场景，自动用上下文填充
    - 不支持文生图
    """

    def __init__(self) -> None:
        self._lama = None
        self.output_dir = Path(config.image_tool.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_lama(self):
        """惰性加载 LaMa 模型"""
        if self._lama is None:
            from simple_lama_inpainting import SimpleLama

            self._lama = SimpleLama()
            logger.info("LaMa model loaded")
        return self._lama

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        raise NotImplementedError("LaMa 不支持文生图，请使用 doubao_generate")

    async def edit(self, request: EditRequest) -> EditResult:
        if not request.mask_image_url:
            raise ValueError("LaMa edit 需要 mask_image_url，请提供掩码")
        return await self.inpaint(
            image_url=request.input_image_url,
            mask_url=request.mask_image_url,
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
        """执行 LaMa 物体移除（不需要 prompt）"""
        meta = metadata or {}

        # 下载图片
        image_pil = await self._download_image(image_url)
        mask_pil = await self._download_image(mask_url)

        if image_pil.mode != "RGB":
            image_pil = image_pil.convert("RGB")
        mask_pil = _convert_mask_to_l(mask_pil)

        # 执行推理（同步阻塞，放到线程池）
        lama = self._get_lama()
        result_pil: Image.Image = await asyncio.to_thread(lama.run, image_pil, mask_pil)

        image_id = f"img_{uuid.uuid4().hex[:12]}"
        local_path = self._save_pil(result_pil, image_id)

        return EditResult(
            image_id=image_id,
            image_url=f"/output/{image_id}.png",
            width=result_pil.width,
            height=result_pil.height,
            metadata={
                "local_path": str(local_path),
                "provider": "lama",
            },
        )

    def _save_pil(self, image: Image.Image, image_id: str) -> Path:
        local_path = self.output_dir / f"{image_id}.png"
        image.save(local_path, "PNG")
        return local_path

    async def _download_image(self, url: str) -> Image.Image:
        import base64
        import io

        import httpx

        if url.startswith("data:"):
            header, encoded = url.split(",", 1)
            data = base64.b64decode(encoded)
            return Image.open(io.BytesIO(data))

        if url.startswith("/") and not url.startswith("//"):
            local_path = Path(url)
            if local_path.exists():
                return Image.open(local_path)
            local_path = Path.cwd() / url.lstrip("/")
            if local_path.exists():
                return Image.open(local_path)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content))


# 注册工具实例和元数据
_lama_tool = LamaImageTool()
registry.register("lama_inpaint", _lama_tool)
registry.register("lama_edit", _lama_tool)

register_tool_meta(
    ToolMeta(
        name="lama_inpaint",
        task_types=frozenset({"inpaint"}),
        requires_mask=True,
        is_local=True,
        priority=5,  # 比 doubao(0) 高，比 moebius(10) 低
    )
)
