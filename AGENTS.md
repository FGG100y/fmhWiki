# AGENTS.md

## Repo Structure — Two Zones

**Root docs** (markdown files at root):
- `LLM-VLM-JEPA-Interview-Roadmap.md` — Simplified Chinese technical interview roadmap for LLM / VLM / JEPA / world models, application-layer focus.
- `Multi-Round-Image-Editing-System-Architecture.md` and `Multi-Turn-Image-Editing-Long-Term-Implementation.md` — architecture docs for a multi-turn image editing product.

**`image_editor/`** — Python implementation of the multi-turn image editing agent framework.
- Entrypoint: `image_editor.main` (uvicorn serves `image_editor.api:app`)
- Deps in `pyproject.toml` (editable install via `pip install -e image_editor/`)
- Requires `ARK_API_KEY` env var (火山引擎 ARK)
- Pre-created pyenv virtualenv: `image-editor` (Python 3.11.9). Activate with `pyenv activate image-editor`.
- Uses `MemoryStore` by default; production needs Postgres + S3/OSS.
- No tests, lint, typecheck, or CI config present.

## Doc Conventions (Roadmap Only)

- Keep Simplified Chinese except established technical terms (`RAG`, `Agent`, `KV Cache`, `LoRA`).
- Major sections: `---` separators, top-level numbering `## 第零部分：` through `## 第九部分：`.
- Subsections: numeric headings `### 1.3` / `#### 7.1`; preserve order.
- Interview questions: `- [ ] ...`.
- `背景了解` sections intentionally thin — do not expand into deep training or paper notes.

## Editing Priorities (Roadmap Only)

- Optimize for interview usefulness: priority, answer frameworks, system-design checkpoints.
- Prefer high-signal additions over broad encyclopedic coverage.
- Preserve application-layer focus; JEPA / world-model content should explain motivation, not imply mature production practice.

## Python Project Notes

- `storage.py` is `MemoryStore` — swap for Postgres before production.
- `/execute` endpoint is synchronous — needs async Job Queue for production.
- See `image_editor/TODOs.md` for full production migration checklist.
- The LangGraph workflow is the core orchestrator (`workflow.py`); each agent node is in `agents/`.
