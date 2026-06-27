# AGENTS.md

## Repo Scope

- Documentation-only knowledge base: no code, package manifests, CI, build system, lint, typecheck, or tests.
- Main content is `LLM-VLM-JEPA-Interview-Roadmap.md`, a Simplified Chinese technical interview roadmap for LLM, VLM, JEPA / world models, with emphasis on application engineering.
- Do not invent setup, build, or verification commands; none are present in the repo.

## Document Conventions

- Keep the document in Simplified Chinese except for established technical terms like `RAG`, `Agent`, `KV Cache`, `LoRA`.
- Major sections use `---` separators and top-level numbering like `## 第零部分：...`, `## 第一部分：...` through `## 第九部分：...`.
- Subsections use numeric headings such as `### 1.3` or `#### 7.1`; preserve existing section order unless the user asks for restructuring.
- Interview questions use Markdown checkboxes: `- [ ] ...`.
- Tables are used for comparisons and scoring; keep them compact and aligned with the surrounding section purpose.
- Sections marked `背景了解` are intentionally thin; do not expand them into deep training or paper notes unless explicitly requested.

## Editing Priorities

- Optimize for interview usefulness: priority, answer frameworks, system-design checkpoints, project metrics, and common follow-up questions.
- Prefer high-signal additions over broad encyclopedic coverage; this is a roadmap, not a textbook.
- Preserve the application-layer focus. JEPA / world-model content should explain motivation and conceptual differences, not imply mature production practice.
