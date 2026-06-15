---
tags: [spencer, reference]
updated: 2026-06-15T18:00+05:30
managed: true
source_path: "docs/OBSIDIAN_BRAIN.md"
---
# OBSIDIAN BRAIN

> Managed mirror of `docs/OBSIDIAN_BRAIN.md`. Edit the source file, not this copy.

# Spencer Obsidian Brain

Obsidian is Spencer's primary knowledge and memory layer. The repository-local
vault is `brain/`.

## Two Layers

- Generated truth: notes with `managed: true`. These are refreshed from the
  database, research journal, workflow state, scoreboard, and canonical docs.
- Reviewed memory: notes under `brain/Memory/` with `managed: false`. The
  exporter never overwrites them.

Generated notes cannot authorize live trading or override the paper-only
doctrine, deployment gate, journal, or research verdicts.

## Runtime

`bot/obsidian_brain.py` provides:

- lexical search across Markdown titles, tags, links, and content;
- cited prompt context and local recall;
- individual note reads;
- graph, backlink, broken-link, and orphan diagnostics;
- atomic capture into memory inboxes;
- a machine-readable index at `brain/.spencer-brain-index.json`.

The quote server exposes:

```text
GET  /api/brain/status
GET  /api/brain/search?q=...
GET  /api/brain/context?q=...
GET  /api/brain/recall?q=...
GET  /api/brain/note?path=...
GET  /api/brain/graph
POST /api/brain/capture
POST /api/brain/reindex
```

Memory capture requires `confirmed: true`, accepts only supported memory
categories, limits content size, writes only inside the vault, and is restricted
to local browser origins.

## Chat

`POST /api/ai/chat` retrieves Obsidian context before calling Gemini. The prompt
requires evidence-bound answers and Obsidian citations. If Gemini is unavailable,
Spencer returns local cited recall instead of inventing an answer.

## Commands

```powershell
python scripts/export_brain.py
python scripts/brain_cli.py status
python scripts/brain_cli.py search "why was SPNCR-002 killed"
python scripts/brain_cli.py context "what blocks live trading?"
python scripts/brain_cli.py reindex
```

The daily market-data job runs the exporter after collection and integrity
checks, so the vault and runtime index follow verified system state.
