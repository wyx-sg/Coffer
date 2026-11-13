## Context

The options and the measurements behind each decision are in the ADRs: `docs/decisions/sync-memories-not-task-notes.md`, `leave-agent-memory-curation-to-the-agent.md` and `a-memory-outlives-its-checkout.md`. This file records only how the change is made.

## Decisions

- **Codex reader.** One source, `<config_dir>/memories_v2/memory_summary.md`. A topic's anchor is `<scope>::What's in Memory::<sha256(body)[:16]>`; its project root is the `cwd:` of the rollout summary it points at. The profile, preferences and General Tips are not parsed: none can be filed under a project.
- **Deleting the v1 entries.** `READER_REVISION` goes from 3 to 4. A ledger written under another revision forgets its source digests, so the next sync re-reads every source; entries no source yields are deleted by their origin machine through the ordinary plan.
- **Checkout gone.** In `_publish_source`, an entry that cannot be placed is kept when it is already in the hub and its recorded directory no longer exists. It is not rewritten.
- **Vault exclusion.** `checkouts()` and `project_of()` drop a repository whose root resolves to the vault root, so the vault is neither published from nor written into.
- **`over_limit`.** The view asks the Claude Code writer which entries its block would hold for a project (`block_entries`, the same function the writer renders from) and reports the rest as `over_limit`.
- **Checkout discovery for Codex** uses the `cwd:` of v2 rollout summaries only.
- **Audit.** `memory_curation_requested`, `memory_curation_enabled` and `memory_hook_removed` are no longer emitted; the types and their labels stay so older rows keep their names.

## Risks

- A Codex without a v2 summary publishes nothing. Accepted: see the ADR.
- A machine still on a build older than 2026-11-11 would keep its hook entries and `coffer_*.md` copies after jumping straight to this build. The only installation is on current main.
