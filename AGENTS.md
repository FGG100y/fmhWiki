# AGENTS.md

## Architecture

**Seedream 5.0 单模型模式** — 所有图片操作统一走 `POST /api/v3/images/generations`。
- 无当前图 → 文生图；有当前图 → 图生图。
- seedream 本身是多模态的，**不需要额外的 LLM 做意图识别、prompt 改写或路由**。客户端只做 undo/redo 判断和透传用户指令。
- **不引入独立 Visual QA / VLM 图像评估** — seedream 多模态生成时已内建质量把控（多模态大模型兜底）。`agents/visual_qa.py` 保留 `passed=True` 直通节点只是为维持 workflow 结构，**不是待补的功能缺口**，勿反复提「接入真实 Visual QA」。
- `DoubaoLLM` 类仍存在于 `llm/client.py` 但未被任何 agent 导入使用。

## Setup & Run

> **Python 环境：默认按 pyenv 处理。** 优先用 pyenv 虚拟环境（`image-editor`）里的 `python` 做验证/启动（如 `python -m image_editor.main`、`python -c "import image_editor.api"`），前端用 `npm run build` / `npm run dev`。下方 `uv ...` 命令仅在装了 `uv` 时可用；若发现本机既非 pyenv 也无 uv（例如 `python`/`uv` 都不可用或找不到虚拟环境），**先询问用户**该用哪种方式，不要擅自猜测或运行改依赖的命令（`pip install`、`uv sync` 等）。

```bash
# 后端 (Python >= 3.11, uv)
cd image_editor
uv sync                                 # 安装依赖
uv run python -m image_editor.main      # 启动 localhost:8000

# 前端 (Node.js >= 18)
cd image_editor/frontend
npm install
npm run dev                             # 启动 localhost:5173，API 代理到 8000
```

环境变量见 `.env.example`。**禁止直接读取 `.env` 文件**，变量名和默认值以 `.env.example` 为准。`ARK_API_KEY` 必填。

## Key Gotchas

- **`tools/__init__.py` 必须不为空** — 其中 `import doubao_image` 触发底部的 `registry.register()` 调用。如果该文件为空，所有工具未注册，workflow 会在 `run_image_tool` 报 `未知工具: doubao_generate`。
- **图片 API 用相对路径** — `DoubaoImageClient` 的 `base_url` 以 `/v3` 结尾，请求路径 `images/generations`（无前导 `/`），最终 URL 为 `.../api/v3/images/generations`。
- **`_download` 返回本地路径，但返回给前端的 URL 是远程 URL** — `DoubaoImageTool._save_result` 将 `image_url` 设为远程 URL（火山引擎 CDN），本地路径只写入 `metadata.local_path`。
- **Workflow 是同步执行** — `/execute` 端点同步跑完整个 LangGraph workflow。生产环境需改为异步 Job Queue（见 TODOs.md P0）。

## Logging

- 日志文件在项目根目录 `logs/app.log`（`main.py` 启动时自动创建）。
- `RotatingFileHandler`，单文件 5MB，保留 3 个备份。
- `watchfiles`/`asyncio`/`httpx` 等第三方库的 DEBUG 日志已被屏蔽。

## Golden Rules (记过簿)

- **永远先读 README 和 AGENTS.md ** — 项目的启动、验证、构建方式以 README 为准。不要自己想当然地跑命令。不知道怎么做时先读文档，不要猜。
- **禁止运行任何修改环境/依赖的命令** — 包括但不限于 `pip install`、`uv pip install`、`uv sync`、`npm install`（除非用户明确要求）。`uv run` 本身不会改依赖，可以用于验证。
- **对应到本文的 Setup & Run** — 启动后端是 `uv run python -m image_editor.main`，不是 import 检查或其它方式。前端的启动方式是 `npm run dev`，写在 `frontend/package.json` 里。

## Testing & Verification

- 无自动化测试、无 lint、无 typecheck、无 CI。
- `image_editor/TODOs.md` 中有 4 条**功能验证清单**（文生图、图生图、版本分支、undo/redo），每次改完代码应手动跑一遍。

## Production Migration

见 `image_editor/TODOs.md`。核心三项：MemoryStore → Postgres，/execute → 异步 Job Queue，本地下载 → S3/OSS。
