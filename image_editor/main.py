"""多轮修图 Agent 入口

环境变量：
  ARK_API_KEY       — 火山引擎 ARK API Key（必需）
  ARK_BASE_URL      — ARK API 地址（可选，有默认值）
  DOUBAO_MODEL      — 豆包模型名（可选，默认 doubao-seedream-5-0-260128）
  IMAGE_PROVIDER    — 图片生成供应商（可选，默认 doubao）
  IMAGE_OUTPUT_DIR  — 图片输出目录（可选，默认 ./output）
  DEBUG             — 调试模式（可选）

启动：
  uvicorn image_editor.main:app --reload

或：
  python -m image_editor.main
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class TruncatingFilter(logging.Filter):
    """截断过长日志消息（避免 base64 图片撑满日志）"""
    MAX_LEN = 500
    def filter(self, record: logging.LogRecord) -> bool:
        if len(record.msg) > self.MAX_LEN:
            record.msg = f"{record.msg[:self.MAX_LEN]}...<truncated {len(record.msg) - self.MAX_LEN} chars>"
        return True


_logs_dir = Path(__file__).parent.parent / "logs"
_logs_dir.mkdir(parents=True, exist_ok=True)

_log_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = RotatingFileHandler(
    _logs_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_log_fmt)
_file_handler.addFilter(TruncatingFilter())

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_fmt)
_console_handler.addFilter(TruncatingFilter())

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_console_handler)

logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

import uvicorn

from image_editor.api import app

if __name__ == "__main__":
    uvicorn.run(
        "image_editor.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=[
            "*.log",
            "*.log.*",
            "*.pyc",
            "__pycache__",
            "node_modules",
            ".vite-temp",
            "output",
            "logs",
        ],
    )
