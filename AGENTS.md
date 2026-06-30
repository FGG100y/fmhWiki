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

## Tooling Notes

### Edit tool Unicode quote matching

The edit tool does exact byte-level string matching. Chinese files in this repo use Unicode curly quotes (`\u201c` \u2014 `U+201C` LEFT DOUBLE QUOTATION MARK, `\u201d` \u2014 `U+201D` RIGHT DOUBLE QUOTATION MARK), not ASCII straight quotes (`"` \u2014 `U+0022`). They look visually identical but differ at the byte level:

| Character | Unicode | UTF-8 bytes |
|-----------|---------|-------------|
| ASCII `"` | `U+0022` | `0x22` (1 byte) |
| Chinese `\u201c` | `U+201C` | `0xE2 0x80 0x9C` (3 bytes) |
| Chinese `\u201d` | `U+201D` | `0xE2 0x80 0x9D` (3 bytes) |

When the LLM generates the `oldString` parameter, it tends to normalize `\u201c`/`\u201d` into ASCII `"`, causing `oldString not found` errors. The edit tool will report the exact error message but the mismatch is invisible to the eye.

**Fix**: For edits involving Chinese punctuation, use a Python script with explicit `\u` escape sequences.

```bash
python3 << 'PYEOF'
with open('/path/to/file.md', 'r') as f:
    content = f.read()
old = '目标文本 \u201c包含中文引号\u201d'
new = '替换文本'
assert old in content, f"old not found"
content = content.replace(old, new, 1)
with open('/path/to/file.md', 'w') as f:
    f.write(content)
PYEOF
```
