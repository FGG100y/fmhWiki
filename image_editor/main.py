"""多轮修图 Agent 入口

环境变量：
  ARK_API_KEY       — 火山引擎 ARK API Key（必需）
  ARK_BASE_URL      — ARK API 地址（可选，有默认值）
  DOUBAO_MODEL      — 豆包模型名（可选，默认 doubao-pro-32k）
  IMAGE_PROVIDER    — 图片生成供应商（可选，默认 doubao）
  IMAGE_OUTPUT_DIR  — 图片输出目录（可选，默认 ./output）
  DEBUG             — 调试模式（可选）

启动：
  uvicorn image_editor.main:app --reload

或：
  python -m image_editor.main
"""

from __future__ import annotations

import uvicorn

from image_editor.api import app

if __name__ == "__main__":
    uvicorn.run(
        "image_editor.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
