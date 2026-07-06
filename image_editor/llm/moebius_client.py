"""Moebius 本地 inpainting 推理客户端

需要 Moebius 仓库代码可用（通过 MOEBIUS_HOME 环境变量指定仓库根目录）。
模型权重通过 MoebiusConfig 配置。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import torch
from PIL import Image

from image_editor.config import config

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


class MoebiusClient:
    """封装 Moebius pipeline 的惰性加载与推理调用"""

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._loaded = False
        self._device = config.moebius.device
        self._http = httpx.AsyncClient(timeout=60)

    # ── 惰性加载 ──────────────────────────────────────────────────────────────

    def _ensure_moebius_importable(self) -> None:
        """将 Moebius 仓库根目录加入 sys.path，使其内部模块可 import"""
        moebius_home = os.path.expanduser(os.environ.get("MOEBIUS_HOME", ""))
        if not moebius_home:
            raise RuntimeError(
                "MOEBIUS_HOME 未设置。请设置为 Moebius 仓库根目录路径，"
                "例如: export MOEBIUS_HOME=/path/to/Moebius"
            )
        moebius_home = str(Path(moebius_home).resolve())
        if moebius_home not in sys.path:
            sys.path.insert(0, moebius_home)
        logger.info("Moebius repo added to sys.path: %s", moebius_home)

    def _load_pipeline(self) -> None:
        """加载 Moebius 模型和 pipeline（同步，仅首次调用）"""
        if self._loaded:
            return

        cfg = config.moebius
        if not cfg.model_weight:
            raise RuntimeError("MOEBIUS_WEIGHT_DIR 未配置")

        logger.info(
            "Loading Moebius pipeline: variant=%s device=%s",
            cfg.variant,
            cfg.device,
        )
        start = time.monotonic()

        self._ensure_moebius_importable()

        from diffusers import DDIMScheduler

        from removal.v1_2 import build_removal_model, load_cfg, load_removal_model
        from removal.v1_2.pipeline import RemovalSDXLPipeline_BatchMode
        from utils_train import build_vae

        # 加载模型配置
        model_config_path = cfg.model_config
        if not model_config_path:
            moebius_home = os.path.expanduser(os.environ.get("MOEBIUS_HOME", ""))
            if moebius_home:
                model_config_path = str(Path(moebius_home) / "config" / "model_cfg" / "moebius.yaml")
        model_cfg = load_cfg(model_config_path)

        # 构建 removal model
        removal_model = build_removal_model(model_cfg, 20).to(cfg.device)
        load_removal_model(removal_model, cfg.model_weight, cfg.device)

        # 构建 VAE
        vae = build_vae(model_cfg).to(cfg.device)

        # 调度器
        scheduler = DDIMScheduler(
            beta_start=0.00085,
            beta_end=0.012,
            beta_schedule="scaled_linear",
            num_train_timesteps=1000,
            clip_sample=False,
        )

        # 构建 pipeline
        self._pipeline = RemovalSDXLPipeline_BatchMode(
            removal_model=removal_model,
            vae=vae,
            scheduler=scheduler,
            device=cfg.device,
            dtype=torch.float,
        )
        self._loaded = True
        elapsed = time.monotonic() - start
        logger.info("Moebius pipeline loaded in %.1fs", elapsed)

    # ── 推理 ──────────────────────────────────────────────────────────────────

    async def inpaint(
        self,
        image_url: str,
        mask_url: str,
        prompt: str = "",
        seed: int = 0,
    ) -> dict[str, Any]:
        """执行 inpainting 推理

        Args:
            image_url: 输入图片 URL
            mask_url: 掩码图片 URL
            prompt: 文本提示（Moebius 内部不使用，保留接口兼容）
            seed: 随机种子

        Returns:
            {"image_pil": PIL.Image, "width": int, "height": int}
        """
        self._load_pipeline()

        # 下载图片
        image_pil = await self._download_image(image_url)
        mask_pil = await self._download_image(mask_url)

        # 转为 RGB
        if image_pil.mode != "RGB":
            image_pil = image_pil.convert("RGB")
        mask_pil = _convert_mask_to_l(mask_pil)

        # 保存原图用于后续贴回
        orig_image = image_pil.copy()

        # 模型要求正方形 latent（h == w），用黑边填充为正方形而非裁剪，避免丢失画面
        cfg = config.moebius
        image_size = cfg.resolution
        image_pil, mask_pil, unpad = self._pad_to_square(image_pil, mask_pil, image_size)

        # 执行推理（同步阻塞，放到线程池）
        import asyncio

        result_list = await asyncio.to_thread(
            self._pipeline,
            [image_pil],
            [mask_pil],
            image_size=cfg.resolution,
            num_steps=cfg.num_steps,
            guidance_scale=cfg.cfg_scale,
            paste=cfg.paste,
            compensate=cfg.compensate,
            noise_offset=0.0357,
            retry=seed,
        )

        result_pil = result_list[0]

        # 将裁剪后的结果贴回原图
        result_pil = self._unpad_result(result_pil, unpad, orig_image)

        return {
            "image_pil": result_pil,
            "width": result_pil.width,
            "height": result_pil.height,
        }

    # ── 辅助 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _pad_to_square(
        img: Image.Image, mask: Image.Image, target_size: int
    ) -> tuple[Image.Image, Image.Image, dict]:
        """用黑边填充为正方形后 resize，不裁剪画面。

        返回 (填充 resize 后的图像, 填充 resize 后的 mask, unpad_info)。
        mask 的填充区域值为 0（不会触发 inpainting）。
        """
        w, h = img.size
        square = max(w, h)
        pad_w = (square - w) // 2
        pad_h = (square - h) // 2

        img_padded = Image.new("RGB", (square, square), (0, 0, 0))
        img_padded.paste(img, (pad_w, pad_h))
        mask_padded = Image.new("L", (square, square), 0)
        mask_padded.paste(mask, (pad_w, pad_h))

        unpad = {"left": pad_w, "top": pad_h, "crop_size": square}

        img_resized = img_padded.resize((target_size, target_size), Image.Resampling.LANCZOS)
        mask_resized = mask_padded.resize((target_size, target_size), Image.Resampling.LANCZOS)
        return img_resized, mask_resized, unpad

    @staticmethod
    def _crop_square_from_mask(
        img: Image.Image, mask: Image.Image, target_size: int
    ) -> tuple[Image.Image, Image.Image, dict]:
        """围绕 mask 区域裁剪正方形，返回 (裁剪后的图像, 裁剪后的 mask, unpad_info)。

        若 mask 为空则回退到中心裁剪。
        图像和 mask 使用相同的裁剪坐标以保证对齐。
        """
        import numpy as np

        mask_arr = np.array(mask)
        if mask_arr.ndim == 3:
            mask_arr = mask_arr[:, :, 0]

        mask_ys, mask_xs = np.nonzero(mask_arr > 0)
        if len(mask_ys) == 0:
            img_cropped, unpad = MoebiusClient._resize_to_square(img, target_size)
            mask_cropped, _ = MoebiusClient._resize_to_square(mask, target_size)
            return img_cropped, mask_cropped, unpad

        y0, y1 = int(mask_ys.min()), int(mask_ys.max())
        x0, x1 = int(mask_xs.min()), int(mask_xs.max())

        mask_h = y1 - y0 + 1
        mask_w = x1 - x0 + 1
        side = max(mask_h, mask_w, target_size)
        padding = max(side // 4, 16)

        cy = (y0 + y1) // 2
        cx = (x0 + x1) // 2
        half = (side + padding * 2) // 2

        t = max(0, cy - half)
        b = min(img.height, t + side + padding * 2)
        l = max(0, cx - half)
        r = min(img.width, l + side + padding * 2)

        actual_h = b - t
        actual_w = r - l
        actual_side = max(actual_h, actual_w)

        t = max(0, cy - actual_side // 2)
        b = min(img.height, t + actual_side)
        l = max(0, cx - actual_side // 2)
        r = min(img.width, l + actual_side)
        actual_h = b - t
        actual_w = r - l
        if actual_w != actual_side:
            l = max(0, min(l, img.width - actual_side))
            r = l + actual_side
        if actual_h != actual_side:
            t = max(0, min(t, img.height - actual_side))
            b = t + actual_side
        actual_side = b - t

        img_cropped = img.crop((l, t, r, b))
        mask_cropped = mask.crop((l, t, r, b))
        unpad = {"left": l, "top": t, "crop_size": actual_side}

        img_resized = img_cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
        mask_resized = mask_cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
        return img_resized, mask_resized, unpad

    @staticmethod
    def _resize_to_square(img: Image.Image, size: int) -> tuple[Image.Image, dict]:
        """中心裁剪为正方形后 resize 到 size×size，返回 (结果, unpad_info)"""
        w, h = img.size
        crop_size = min(w, h)
        left = (w - crop_size) // 2
        top = (h - crop_size) // 2
        img_cropped = img.crop((left, top, left + crop_size, top + crop_size))
        unpad = {"left": left, "top": top, "crop_size": crop_size}
        return img_cropped.resize((size, size), Image.Resampling.LANCZOS), unpad

    @staticmethod
    def _unpad_result(result: Image.Image, unpad: dict, original: Image.Image) -> Image.Image:
        """将正方形结果贴回原始尺寸图像"""
        crop_size = unpad["crop_size"]
        left = unpad["left"]
        top = unpad["top"]
        # 将 512×512 结果 resize 回填充/裁剪区域尺寸
        resized = result.resize((crop_size, crop_size), Image.Resampling.LANCZOS)
        out = original.copy()
        # 判断是 pad 还是 crop：如果 crop_size >= original 的宽高，则为 pad 模式
        pw, ph = original.size
        if crop_size >= max(pw, ph):
            # pad 模式：结果图尺寸 ≥ 原图，裁剪对应原图区域的子图粘贴
            crop = resized.crop((left, top, left + pw, top + ph))
            out.paste(crop, (0, 0))
        else:
            # crop 模式：结果图尺寸 ≤ 原图，直接粘贴到对应位置
            out.paste(resized, (left, top))
        return out

    async def _download_image(self, url: str) -> Image.Image:
        """从 URL 或本地路径加载图片并返回 PIL.Image"""
        import base64
        import io

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

        resp = await self._http.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))

    async def close(self) -> None:
        await self._http.aclose()
        if self._pipeline is not None:
            # 释放 GPU 显存
            del self._pipeline
            self._pipeline = None
            self._loaded = False
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
