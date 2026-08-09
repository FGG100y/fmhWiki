# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

多轮修图 Agent — a multi-turn image-editing agent built on Doubao Seedream 5.0 + LangGraph. Supports text-to-image, image-to-image, and local inpainting (Moebius GPU model) with cloud fallback. The frontend is a React SPA; the backend is FastAPI + Dramatiq (Redis) + PostgreSQL.

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
                                                                    ├── prompt_enhancer (LLM)
                                                                    ├── ToolRouter (router.py)
                                                                    │     ├── doubao (cloud API)
                                                                    │     ├── moebius (local GPU)
                                                                    │     └── lama (local)
                                                                    └── visual_qa → persist
```

### Workflow graph (LangGraph StateGraph)

```
load_session → safety_check → [conditional]
  ├── fail (blocked keywords)
  ├── enhance_prompt → run_image_tool → visual_qa → [conditional]
  │     ├── pass → persist_turn → END
  │     ├── retry → run_image_tool (max 2 retries)
  │     └── fail → persist_turn → END
  └── run_image_tool (skip enhance for local inpainting)
```

State is `ImageEditState` (TypedDict in `state.py`). Workflow nodes each return a partial dict that is merged into the accumulated state.

### Tool routing

`tools/router.py` resolves task type from `(has_image, has_mask)`:
- No image → `generate` (text-to-image)
- Image + mask → `inpaint` (local GPU preferred, cloud fallback)
- Image only → `edit` (image-to-image)

Tools are registered with metadata (`ToolMeta`): task_types, requires_mask, is_local, priority. `run_image_tool` iterates candidates in priority order, falling back on failure.

`tools/__init__.py` MUST NOT be empty — its imports trigger `registry.register()` calls. Missing file = tools silently unregistered.

### Storage layer

`storage.py`: dual implementation — `MemoryStore` (dev, no DB needed) and `PostgresStore` (production). Selected by `DATABASE_URL` env var presence.

Key tables: `sessions` (with undo/redo stack), `turns` (tree structure via `parent_turn_id`), `images`, `jobs`, `model_calls`.

### Frontend

React 18 + TypeScript + Vite. State is managed entirely in `hooks/useSession.ts` (no Redux/router). Simple component tree:

```
App
├── TurnTimeline (editing history tree with collapse)
├── ImageViewer (before/after comparison, mask/sketch overlay)
├── InstructionInput (text + file uploads + mask controls)
└── WelcomeGuide (first-visit tutorial modal)
```

Frontend polls `/jobs/{job_id}` at 1s intervals after submitting an edit. The `/replay` endpoint creates a new turn from a prior one for retries.

### LLM clients

`llm/client.py`:
- `DoubaoLLM` — wraps OpenAI-compatible SDK for prompt enhancement. Records every call to `model_calls` table with latency/tokens.
- `DoubaoImageClient` — raw httpx calls to ARK `images/generations` endpoint. All image ops (generate/edit/inpaint) go through this single endpoint with different payload shapes.

## Critical constraints

1. **Worker processes**: dramatiq defaults to `cpu_count` processes. Each loads Moebius into GPU VRAM independently → OOM. Always use `--processes 1 --threads 2`.
2. **Moebius model is never unloaded**: `_cleanup_gpu()` only frees cache, not model params. Restart worker after Moebius code changes.
3. **Seedream 5.0 is the sole model**: both LLM reasoning and image generation use the same `DOUBAO_MODEL` (multimodal). There is no separate LLM model.
4. **Images stored as base64 data URIs** in the `images` table (no object storage). Uploads capped at 1MB / 2048px.
5. **`persist_turn` may not execute**: if workflow fails before that node (OOM, API error), the turn record lacks `output_image_id` / `mask_image_id`. Downstream code must handle this.
6. **Frontend image display**: leaf nodes without `outputUrl` but with an instruction are no longer treated as errors (previously showed false "processing failed").
7. **Moebius `_unpad_result` padding bug**: fixed — vertical images were double-offsetting content. If old behavior reappears, check the pad-mode crop logic in `moebius_client.py`.

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

`.env.example` is authoritative. Required: `ARK_API_KEY`, `DATABASE_URL`. Optional GPU: `MOEBIUS_ENABLED`, `MOEBIUS_WEIGHT_DIR`, `MOEBIUS_DEVICE`, `LAMA_ENABLED`.
