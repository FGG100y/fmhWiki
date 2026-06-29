from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DoubaoConfig:
    """豆包大模型 / 火山引擎 ARK 配置"""

    api_key: str = field(default_factory=lambda: os.getenv("ARK_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv("DOUBAO_MODEL", "doubao-pro-32k")
    )
    max_retries: int = 3
    request_timeout: int = 120


@dataclass
class ImageToolConfig:
    """图片工具配置"""

    provider: str = field(default_factory=lambda: os.getenv("IMAGE_PROVIDER", "doubao"))
    output_dir: str = field(default_factory=lambda: os.getenv("IMAGE_OUTPUT_DIR", "./output"))
    max_image_size: tuple[int, int] = (2048, 2048)


@dataclass
class AppConfig:
    doubao: DoubaoConfig = field(default_factory=DoubaoConfig)
    image_tool: ImageToolConfig = field(default_factory=ImageToolConfig)
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    max_qa_retries: int = 2


config = AppConfig()
