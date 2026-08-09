import logging

logger = logging.getLogger(__name__)

from painterAgent.tools import doubao_image  # noqa: F401 — triggers registry.register()

# 条件导入本地模型工具（依赖可选，缺失时跳过）
try:
    from painterAgent.tools import moebius_image  # noqa: F401
except ImportError as e:
    logger.warning("moebius_image import failed (local GPU inpainting unavailable): %s", e)

try:
    from painterAgent.tools import lama_image  # noqa: F401
except ImportError as e:
    logger.warning("lama_image import failed (local object removal unavailable): %s", e)

# 文本 LLM 路由注册（prompt_enhance 能力）
from painterAgent.llm import ollama_client  # noqa: F401 — triggers route registration
# doubao_llm 路由由 llm/client.py 注册，已通过 doubao_image 的导入链触发
