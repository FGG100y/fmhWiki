# AGENTS.md

## Setup & Run

```bash
# 后端
uv run python -m painterAgent.main           # localhost:8000

# Worker（异步任务队列）
uv run python -m dramatiq painterAgent.worker --processes 1 --threads 2

# 前端
cd frontend
npm run dev                            # localhost:5173, API proxy → 8000

# 或一键启动全部三个进程
./start-dev.sh
```

- Python 3.11+，由 uv 管理（`.python-version` / `uv.lock`，包位于 `src/painterAgent/`）
- **不要运行** `uv sync` / `uv add` / `npm install` 除非用户明确要求
- 杀死所有 worker 后需显式指定 `--processes 1 --threads 2`，否则 dramatiq 默认 fork CPU 核数个进程，每份独立加载 Moebius 模型到 GPU 显存导致 OOM

## Env

`.env.example` 是来源。`ARK_API_KEY` 为 doubao 云服务必需；Moebius 本地 inpainting 不需要。关键变量：

| 变量 | 作用 |
|---|---|
| `ARK_API_KEY` | 火山引擎 ARK（doubao 云服务），不配则云 API 返回 401 |
| `MOEBIUS_ENABLED=true` | 启用本地 inpainting（需 GPU + Moebius 仓库） |
| `MOEBIUS_HOME` | Moebius 仓库根目录（`git clone` 后路径） |
| `MOEBIUS_WEIGHT_DIR` | 模型权重目录 |

## Architecture

**Seedream 5.0 单模型 + 本地 Moebius 双模式** — 不再只有云服务。

- `src/painterAgent/tools/router.py` 根据 `has_image` / `has_mask` 推断任务类型：`generate`（文生图）→ `edit`（图生图）→ `inpaint`（局部重绘）
- 每个任务类型有候选工具列表，按 `priority` 降序选：
  - `inpaint` → `moebius_inpaint` (priority 10, 本地 GPU) > `doubao_inpaint` (0, 云)
  - `edit` → `doubao_edit` (云)
  - `generate` → `doubao_generate` (云)
- 本地候选失败（OOM / 模型错误）自动 fallback 到云服务
- **`src/painterAgent/tools/__init__.py` 必须不为空** — 其中的 `import` 触发 `registry.register()`。空文件 = 所有工具未注册

## Storage & Workflow

- 存储：内存 `MemoryStore` / Postgres 双实现（`storage.py`），通过 `DATABASE_URL` 环境变量切换
- Workflow 引擎：LangGraph `StateGraph`（`workflow.py`），节点顺序：`load_session → safety_check → enhance_prompt → run_image_tool → visual_qa → persist_turn`
- 执行：Dramatiq 异步 Job Queue（`worker.py`），API 立即返回 `job_id`，前端轮询
- **Workflow 可能中途失败（OOM / API 401），`persist_turn` 未执行则 turn 缺少 `mask_image_id` / `output_image_id`**。`execute_turn` 和 `replay_turn` 在创建 turn 后已即时保存 `mask_image_id`，但仍可能缺 output

## Frontend Gotchas

- **叶子节点右侧误报"处理失败"**：已修复，`ImageViewer.tsx` 不再把 `!outputUrl && instruction` 当作失败
- **多原图自动折叠**：`TurnTimeline.tsx` 中每个根节点（原图）有 `▼/▶` 折叠按钮，上传新图时旧分支自动收起
- 重试按钮调 `/replay` 端点，用相同 instruction + mask 创建新 turn

## GPU / Worker

- **worker 进程数必须控制**：dramatiq 默认 fork CPU 核数个进程。每份独立加载 Moebius 模型进 GPU 显存。生产环境用 `--processes 1 --threads 2`
- `src/painterAgent/worker.py` 中 `_cleanup_gpu()` 在每次 workflow 结束后调用 `torch.cuda.synchronize()` + `gc.collect()` + `torch.cuda.empty_cache()`。但只能释放缓存，**不能卸载模型参数本身**
- Moebius OOM 可尝试降低 `MOEBIUS_RESOLUTION`（默认 512）

## Moebius Client Bugs (记过簿)

- **`_unpad_result` pad 模式内容偏移**：竖长图（1150×2048）用黑边填充到正方形后，`out.paste(resized, (left, top))` 会重复偏移内容。已修复为 pad 模式裁出原图区域再粘贴
- 重新提交后如需生效，必须重启 worker 进程（pipeline 是惰性加载并缓存）

## Testing

- 无自动化测试、无 lint、无 typecheck、无 CI
- 功能验证见 `TODOs.md` 中 4 条链路（文生图、图生图、版本分支、undo/redo）
