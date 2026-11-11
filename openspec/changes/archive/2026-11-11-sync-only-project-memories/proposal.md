## Why

The Memory page was mostly noise. Global memories (Codex's profile and preferences, task groups with no repository) were mostly one employer's tool habits, loaded into every Claude Code session through `rules/coffer-memory.md`. Task notes were flagged, held back from the other agent and counted for a "Sort into knowledge" hand-off that never ran, so Codex project memories never reached Claude Code.

## What Changes

- A memory learned outside any repository is no longer published; nothing is filed under `global`. The Claude Code rules file is no longer written, and the next sync deletes one an earlier build wrote. `global/` hub entries from an earlier build are written into no agent and not listed; the ledger's reader revision makes their origin machine delete them.
- Task notes are no longer flagged or held back: within a project every memory syncs.
- **BREAKING** Removed: the "to sort" line and badge, **Sort into knowledge**, the `memory_to_sort` attention item, sorted records, `coffer memory to-sort/sort/sorted`, and `/api/v1/memory/sync/to-sort`, `/sort/handoff`, `/sorted`. The Memory page lists projects only; `/memory/global` opens the page.
- The main spec `openspec/specs/memory/spec.md` and `data-model.md` were edited directly (scenarios renamed and removed), so this change carries no delta.

## Capabilities

### Modified Capabilities

- `memory`: sync only project memories; no task-note sorting.

## Impact

Backend memory sync, HTTP routes and CLI, the frontend Memory page and Overview attention, docs-site (en and zh), ADR `docs/decisions/sync-only-project-memories.md`.
