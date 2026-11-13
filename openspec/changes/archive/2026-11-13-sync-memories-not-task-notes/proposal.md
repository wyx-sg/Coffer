## Why

A review of the memory design on 2026-11-13 measured the hub on the maintainer's Mac: 232 of 308 entries were Codex v1 task-group bullets, the working notes of single tasks, and Claude Code's 4 KB block held 14 of one project's 90 memories. The curation panel read two undocumented Claude Code sources and its **Curate now** prompt had named no folder since Claude Code's copies became one block. A memory whose checkout was deleted could be removed from the hub on the next re-read. Upgrade code for builds no machine runs any more was still shipped.

## What Changes

- Codex is read only from `memories_v2/memory_summary.md`: each topic of **What's in Memory** is one memory. `memories/MEMORY.md` task groups are no longer read. The content-identity carry-over and `search_terms` go with them. The ledger's reader revision is bumped, so the first sync deletes the v1 entries each machine published.
- **BREAKING** Removed: the curation rows on each agent's Memory tab, **Turn on** (Auto Dream) and **Curate now**; `coffer memory curate` and `coffer memory curation-enable`; `/api/v1/memory/sync/curation/handoff` and `/curation/enable`. The tab shows what Coffer wrote into the agent, or why it cannot write.
- A memory already in the hub stays when its source still holds it and its checkout is gone from the origin machine.
- The vault's own checkout, `~/.coffer/vault`, is not a project: nothing learned there is published and nothing is written there.
- A memory that did not fit in Claude Code's block has the copy state `over_limit`, shown on its row.
- Removed upgrade code: the retired memory hook's removal, the deletion of `derived/memory/`, the clean-up of `coffer_*.md` copies and the Claude Code rules file, the `global/` hub folder, and the error code `MEMORY_DELIVERY_CONFIG_INVALID`.
- The main spec `openspec/specs/memory/spec.md` and `data-model.md` were edited directly (requirements and scenarios renamed and removed), so this change carries no delta.

## Capabilities

### Modified Capabilities

- `memory`: read Codex from its v2 summary only; no curation surface; keep a memory whose checkout is gone; exclude the vault; show what did not fit.
- `agent-registry`: the Memory tab's sync section no longer mentions curation.

## Impact

Backend memory sync (readers, publish, view, HTTP routes, CLI), the frontend agent Memory tab and Memory page, docs-site (en and zh), ADRs `sync-memories-not-task-notes`, `leave-agent-memory-curation-to-the-agent`, `a-memory-outlives-its-checkout` (new), `sync-only-project-memories` and `follow-codex-memory-into-every-version-folder` (revised), `codex-memory-identity-is-content-with-rewrite-carry-over` (deleted).

On upgrade, a machine's first sync removes its Codex v1 entries from the hub and their copies from the agents; when more than 50 copies change it waits as a preview on the Memory page.
