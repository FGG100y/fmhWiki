# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

多轮修图 Agent — a multi-turn image-editing agent built on Doubao Seedream 5.0 + LangGraph. Supports text-to-image, image-to-image, local inpainting (Moebius GPU), and object removal (LaMa CPU). Features agentic multi-step editing (LLM自主规划工具调用) and local LLM routing (Ollama). The frontend is a React SPA; the backend is FastAPI + Dramatiq (Redis) + PostgreSQL.

## Commands

```bash
# Backend — localhost:8000
uv run python -m painterAgent.main

# Worker (async image jobs; MUST use --processes 1 --threads 2 to avoid GPU OOM)
uv run python -m dramatiq painterAgent.worker --processes 1 --threads 2

# Frontend dev server — localhost:5173, proxies API to :8000
cd frontend && npm run dev

# All three at once
./start-dev.sh

# Production: build frontend, then backend serves dist/ as static files
cd frontend && npm run build
uv run python -m painterAgent.main      # now serves full app on :8000

# Python deps (do NOT run without explicit user request)
uv sync
uv sync --extra local-moebius   # GPU inpainting deps
uv sync --extra local-lama      # LaMa object removal deps

# Database init
cp schema.sql /tmp/
sudo -u postgres psql -d image_editor -f /tmp/schema.sql
```

No automated tests, lint, typecheck, or CI exist in this repo.

## Architecture

```
Request flow:
  Browser (React) → FastAPI (api.py) → Dramatiq (worker.py) → LangGraph workflow (workflow.py)
                                                                    ├── agentic_editor (多步规划, optional)
                                                                    ├── prompt_enhancer (LLM 改写提示词)
                                                                    ├── ToolRouter (router.py)
                                                                    │     ├── doubao (cloud API)
                                                                    │     ├── moebius (local GPU)
                                                                    │     └── lama (local CPU)
                                                                    └── visual_qa → persist
```

### Workflow graph (LangGraph StateGraph)

```
load_session → safety_check → [conditional]
  ├── fail (blocked keywords)
  ├── agentic_edit (if execution_mode=agentic/auto + AGENTIC_EDIT_ENABLED)
  │     ├── success → persist_turn → END
  │     └── degraded → fallthrough to legacy path below
  ├── enhance_prompt → run_image_tool → visual_qa → [conditional]
  │     ├── pass → persist_turn → END
  │     ├── retry → run_image_tool (max 2 retries)
  │     └── fail → persist_turn → END
  └── run_image_tool (skip enhance for local inpainting)
```

State is `ImageEditState` (TypedDict in `state.py`). Workflow nodes each return a partial dict that is merged into the accumulated state.

### Execution modes

Three modes, selectable via frontend ActivityBar:

| Mode | Behavior |
|------|----------|
| `agentic` | LLM 自主规划多步工具调用（需 `AGENTIC_EDIT_ENABLED=true`）。规划模型调用 generate → edit → verify 序列，可处理复杂多步需求 |
| `deterministic` | 固定流程 enhance → generate/edit → QA。适合简单明确的需求 |
| `auto` | `AGENTIC_EDIT_ENABLED=true` 时等同于 agentic，否则等同于 deterministic |

Agentic 模式支持降级（degraded）：规划失败时自动回退到 legacy（deterministic）路径。
规划模型通过 aisuite 统一接口调用，支持 ollama 本地模型和豆包云端模型。

### Tool routing

`tools/router.py` resolves task type from `(has_image, has_mask)`:
- No image → `generate` (text-to-image)
- Image + mask → `inpaint` (local preferred, cloud fallback)
- Image only → `edit` (image-to-image)

Routing uses a **two-level** system:
1. **Image tools**: registered with `priority` — higher = preferred. Current order: LaMa (15) > Moebius (10) > Doubao (8)
2. **Text LLMs**: priority controlled by `TEXT_LLM_ORDER` env var (e.g., `ollama,doubao`). `router.py`'s `Capability` enum distinguishes `prompt_enhance` from image capabilities.

Tools are registered via `registry.register()` + `register_route(ModelRoute(...))`. `run_image_tool` iterates candidates in priority order, falling back on failure.

`tools/__init__.py` MUST NOT be empty — its imports trigger `registry.register()` calls. Missing file = tools silently unregistered. Moebius and LaMa are conditionally imported (caught ImportError → warn, skip).

### Storage layer

`storage.py`: dual implementation — `MemoryStore` (dev, no DB needed) and `PostgresStore` (production). Selected by `DATABASE_URL` env var presence.

Key tables: `sessions` (with undo/redo stack), `turns` (tree structure via `parent_turn_id`), `images`, `jobs`, `model_calls`.

### Frontend

React 18 + TypeScript + Vite. State is managed entirely in `hooks/useSession.ts` (no Redux/router). Component tree:

```
App
├── ActivityBar (execution mode selector + upload/mask/sketch buttons)
├── ChatHistory (message bubble list)
├── ChatInput (instruction input + file uploads)
├── ImageViewer (before/after comparison, mask/sketch overlay, zoom/pan)
├── MaskCanvas (mask drawing with ResizeObserver)
├── SketchCanvas (sketch drawing)
├── TurnTimeline (editing history tree with collapse)
└── WelcomeGuide (first-visit tutorial modal)
```

Frontend polls `/jobs/{job_id}` at 1s intervals after submitting an edit. The `/replay` endpoint creates a new turn from a prior one for retries.

### LLM clients

`llm/client.py`:
- `DoubaoLLM` — wraps OpenAI-compatible SDK for prompt enhancement. Records every call to `model_calls` table with latency/tokens.
- `DoubaoImageClient` — raw httpx calls to ARK `images/generations` endpoint. All image ops (generate/edit/inpaint) go through this single endpoint with different payload shapes.

`llm/ollama_client.py`:
- `OllamaLLM` — local LLM via ollama's OpenAI-compatible endpoint (`/v1`). Provides `chat_json` (robust JSON parsing with markdown-fence stripping), `chat_stream`, and `chat_tools` (native agentic tool-call loop for qwen3, bypassing aisuite's OllamaProvider which lacks tool_calls support).

`llm/aisuite_client.py`:
- `get_client()` — aisuite unified client factory. Used by agentic editor for cloud-based planner models (doubao via OpenAI-compatible provider).

### Agentic editing (`agents/agentic_editor.py`)

Planner model autonomously decides tool-call sequences. Detects `is_ollama` from `AGENTIC_MODEL` prefix:
- **Ollama (local)**: uses `AGENTIC_SYSTEM_PROMPT_NO_VISION` (no `inspect_image` tool), calls `ollama_llm.chat_tools()` directly
- **Cloud (doubao)**: uses full prompt with `inspect_image` vision tool, calls via aisuite

`demo_learning.py` builds demonstration context (from recent turns) and preference profiles (from user history) injected into the system prompt. Controlled by `AGENTIC_DEMO_ENABLED` / `AGENTIC_PREFERENCE_ENABLED`.

## Critical constraints

0. **sudo 命令**: 任何需要 `sudo` 的命令都**不要自行执行**，改为提示用户手动运行。因为 sudo 可能需要指纹验证或密码输入，自行执行会卡住。
1. **Worker processes**: dramatiq defaults to `cpu_count` processes. Each loads Moebius into GPU VRAM independently → OOM. Always use `--processes 1 --threads 2`.
2. **Moebius model is never unloaded**: `_cleanup_gpu()` only frees cache, not model params. Restart worker after Moebius code changes.
3. **Image generation is Seedream-only**: text LLM can use ollama (local) or doubao (cloud) via `TEXT_LLM_ORDER`, but all image ops (generate/edit/inpaint) still go through Doubao Seedream 5.0. Local image tools (Moebius/LaMa) only handle inpainting.
4. **Images stored as base64 data URIs** in the `images` table (no object storage). Uploads capped at 1MB / 2048px.
5. **`persist_turn` may not execute**: if workflow fails before that node (OOM, API error), the turn record lacks `output_image_id` / `mask_image_id`. Downstream code must handle this.
6. **Frontend image display**: leaf nodes without `outputUrl` but with an instruction are no longer treated as errors (previously showed false "processing failed").
7. **Moebius `_unpad_result` padding bug**: fixed — vertical images were double-offsetting content. If old behavior reappears, check the pad-mode crop logic in `moebius_client.py`.
8. **Ollama qwen3 tool_calls**: must set `OLLAMA_THINK=false` (extra_body `{"think": false}`) — otherwise qwen3's thinking mode interferes with structured tool_call output.
9. **Agentic degraded fallback**: when agentic planning fails (`degraded=True`), workflow falls through to the legacy deterministic path. Code must handle both paths producing output.

## API endpoints (key ones)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/projects/{id}/sessions` | Create session |
| GET | `/sessions/{id}` | Full session + turn tree |
| POST | `/sessions/{id}/execute` | Enqueue async turn (returns `job_id`) |
| POST | `/sessions/{id}/replay` | Sync retry of a prior turn |
| GET | `/jobs/{id}` | Poll job status |
| POST | `/jobs/{id}/cancel` | Cancel queued/running job |
| POST | `/sessions/{id}/undo` / `/redo` | Undo/redo navigation |
| DELETE | `/sessions/{id}/turns/{tid}` | Delete a turn |
| POST | `/upload` | Image upload (auto-compresses >1MB) |

## Env vars

`.env.example` is authoritative. Required: `ARK_API_KEY`, `DATABASE_URL`.

Key env vars by category:

| Category | Var | Note |
|----------|-----|------|
| Cloud API | `ARK_API_KEY`, `ARK_BASE_URL`, `DOUBAO_MODEL` | Seedream 5.0 (image gen + LLM reasoning) |
| Local GPU | `MOEBIUS_ENABLED`, `MOEBIUS_WEIGHT_DIR`, `MOEBIUS_DEVICE`, `MOEBIUS_VARIANT` | Inpainting, requires `uv sync --extra local-moebius` |
| Local CPU | `LAMA_ENABLED` | Object removal, requires `uv sync --extra local-lama` |
| Local LLM | `OLLAMA_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_THINK` | Text LLM routing, `OLLAMA_THINK=false` required for agentic |
| LLM order | `TEXT_LLM_ORDER` | Comma-separated provider list, e.g. `ollama,doubao` |
| Agentic | `AGENTIC_EDIT_ENABLED`, `AGENTIC_MODEL`, `AGENTIC_MAX_TURNS`, `AGENTIC_MAX_TOOL_CALLS`, `VISION_MODEL` | Multi-step editing; model format: `openai:name` or `ollama:name` |
| Agentic learning | `AGENTIC_DEMO_ENABLED`, `AGENTIC_DEMO_MAX_STEPS`, `AGENTIC_PREFERENCE_ENABLED`, `AGENTIC_PREFERENCE_MIN_TURNS` | Demo + preference injection into planner prompt |
| Infra | `DATABASE_URL` (empty → MemoryStore), `REDIS_URL`, `DEBUG` | |
