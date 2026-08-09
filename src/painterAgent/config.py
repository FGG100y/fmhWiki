from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


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
        default_factory=lambda: os.getenv("DOUBAO_MODEL", "doubao-seedream-5-0-260128")
    )
    max_retries: int = 3
    request_timeout: int = 120


@dataclass
class ImageToolConfig:
    """图片工具配置"""

    provider: str = field(default_factory=lambda: os.getenv("IMAGE_PROVIDER", "doubao"))
    output_dir: str = field(
        default_factory=lambda: os.getenv("IMAGE_OUTPUT_DIR", "./output")
    )
    upload_dir: str = field(
        default_factory=lambda: os.getenv("IMAGE_UPLOAD_DIR", "./uploads")
    )
    max_image_size: tuple[int, int] = (2048, 2048)


@dataclass
class MoebiusConfig:
    """Moebius 本地 inpainting 模型配置"""

    enabled: bool = field(
        default_factory=lambda: os.getenv("MOEBIUS_ENABLED", "false").lower() == "true"
    )
    weight_dir: str = field(
        default_factory=lambda: os.getenv("MOEBIUS_WEIGHT_DIR", "")
    )
    variant: str = field(
        default_factory=lambda: os.getenv("MOEBIUS_VARIANT", "pretrained")
    )
    vae_weight: str = field(default_factory=lambda: os.getenv("MOEBIUS_VAE_WEIGHT", ""))
    model_config: str = field(
        default_factory=lambda: os.getenv("MOEBIUS_MODEL_CONFIG", "")
    )
    device: str = field(
        default_factory=lambda: os.getenv("MOEBIUS_DEVICE", "cuda")
    )
    resolution: int = field(
        default_factory=lambda: int(os.getenv("MOEBIUS_RESOLUTION", "512"))
    )
    num_steps: int = field(
        default_factory=lambda: int(os.getenv("MOEBIUS_NUM_STEPS", "20"))
    )
    cfg_scale: float = field(
        default_factory=lambda: float(os.getenv("MOEBIUS_CFG", "2.5"))
    )
    paste: bool = True
    compensate: bool = False

    @property
    def model_weight(self) -> str:
        """根据 weight_dir + variant 自动拼接模型权重路径"""
        import pathlib

        if not self.weight_dir:
            return ""
        weight_dir = os.path.expanduser(self.weight_dir)
        return str(pathlib.Path(weight_dir) / self.variant / "diffusion_pytorch_model.bin")

    @property
    def resolved_vae_weight(self) -> str:
        """vae 权重路径，若未单独指定则从 weight_dir 推断"""
        import pathlib

        if self.vae_weight:
            return os.path.expanduser(self.vae_weight)
        if self.weight_dir:
            weight_dir = os.path.expanduser(self.weight_dir)
            return str(pathlib.Path(weight_dir).parent / "vae")
        return ""


@dataclass
class LaMaConfig:
    """LaMa 物体移除模型配置"""

    enabled: bool = field(
        default_factory=lambda: os.getenv("LAMA_ENABLED", "false").lower() == "true"
    )


@dataclass
class OllamaConfig:
    """ollama 本地模型配置"""

    enabled: bool = field(
        default_factory=lambda: os.getenv("OLLAMA_ENABLED", "false").lower() == "true"
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )
    model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:8b")
    )
    think: bool = field(
        default_factory=lambda: os.getenv("OLLAMA_THINK", "false").lower() == "true"
    )


@dataclass
class AgenticConfig:
    """Agentic 多步编辑配置"""

    enabled: bool = field(
        default_factory=lambda: os.getenv("AGENTIC_EDIT_ENABLED", "false").lower() == "true"
    )
    planner_model: str = field(
        default_factory=lambda: os.getenv("AGENTIC_MODEL", "openai:doubao-seed-1-6-250615")
    )
    max_turns: int = field(
        default_factory=lambda: int(os.getenv("AGENTIC_MAX_TURNS", "5"))
    )
    max_tool_calls: int = field(
        default_factory=lambda: int(os.getenv("AGENTIC_MAX_TOOL_CALLS", "8"))
    )
    vision_model: str = field(
        default_factory=lambda: os.getenv("VISION_MODEL", "openai:doubao-1-5-vision-pro-32k-250115")
    )
    consecutive_fail_limit: int = field(
        default_factory=lambda: int(os.getenv("AGENTIC_CONSECUTIVE_FAIL_LIMIT", "3"))
    )
    demo_enabled: bool = field(
        default_factory=lambda: os.getenv("AGENTIC_DEMO_ENABLED", "true").lower() == "true"
    )
    demo_max_steps: int = field(
        default_factory=lambda: int(os.getenv("AGENTIC_DEMO_MAX_STEPS", "6"))
    )
    pref_enabled: bool = field(
        default_factory=lambda: os.getenv("AGENTIC_PREFERENCE_ENABLED", "true").lower() == "true"
    )
    pref_min_turns: int = field(
        default_factory=lambda: int(os.getenv("AGENTIC_PREFERENCE_MIN_TURNS", "3"))
    )


@dataclass
class AppConfig:
    doubao: DoubaoConfig = field(default_factory=DoubaoConfig)
    moebius: MoebiusConfig = field(default_factory=MoebiusConfig)
    lama: LaMaConfig = field(default_factory=LaMaConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    agentic: AgenticConfig = field(default_factory=AgenticConfig)
    image_tool: ImageToolConfig = field(default_factory=ImageToolConfig)
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )
    max_qa_retries: int = 2

    @property
    def text_llm_order(self) -> list[str]:
        """文本 LLM 候选顺序（逗号分隔，第一个优先；默认 ollama,doubao）"""
        raw = os.getenv("TEXT_LLM_ORDER", "ollama,doubao")
        return [p.strip() for p in raw.split(",") if p.strip()]

    def enabled_providers(self) -> set[str]:
        """返回当前可用的 provider 集合"""
        providers: set[str] = set()
        if self.doubao.api_key:
            providers.add("doubao")
        if self.moebius.enabled and self.moebius.weight_dir:
            providers.add("moebius")
        if self.lama.enabled:
            providers.add("lama")
        if self.ollama.enabled:
            providers.add("ollama")
        return providers


config = AppConfig()
