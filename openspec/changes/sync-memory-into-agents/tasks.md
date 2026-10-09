## 0. Decide

- [x] 0.1 ADR `sync-memory-into-each-agents-own-memory`; mark the superseded ADRs
- [x] 0.2 Proposal, design and the memory spec delta
- [x] 0.3 ~~On the maintainer's machine, find where Codex stores "import from Claude Code" with automatic updates, and Claude Code's Auto Dream switch~~ Deferred: neither setting is documented, so both read "unknown" and the page offers the manual switch design §6 describes; reading them is a follow-up once their keys are confirmed

## 1. Hub and writers (PR 1, beside the old layer, worker off)

- [x] 1.1 Domain: hub entry (id, origin, project key, type, frontmatter round-trip), project folder name, path portability (`<repo>`, `~`, boundary-safe replace and expand)
- [x] 1.2 Infrastructure: hub store under `vault/memory/` through the vault write path, one commit per sync, writer `memory-sync`; traversal guard for every built segment
- [x] 1.3 Readers: keep both; skip Coffer's own copies (`coffer_` + `coffer.entry`, marked block, rules file, `extensions/`, `[via Coffer]`); carry `reference` memories; stable source identity
- [x] 1.4 Checkout map: working directories recorded by registered agents → `resolve_repository` → project key → local root
- [x] 1.5 Claude Code writer: project directory by `encode_slug`, `coffer_<slug>.md`, marked block with cap and overflow line, backup before change, rules file for global
- [x] 1.6 Codex writer: layout check, `memories` feature check, `instructions.md`, `resources/<id>-<slug>.md`
- [x] 1.7 Ledger `local/memory-sync.json`: sources, copies with state, delivered sentence fingerprints; absorption check
- [x] 1.8 Secret withholding with the bundled plaintext detector
- [x] 1.9 Sync service: plan → publish → write (or save preview) → `memory_synced`; one at a time; Sync now; Write preview; Undo sync; Curate now
- [x] 1.10 Worker with switch and interval in the internal-engine settings (default off until PR 3)
- [x] 1.11 REST routes for the new page (state, sync now, preview write/cancel, undo, curate, projects and entries)
- [x] 1.12 Tests carrying `acceptance("memory", …)` for every ADDED and MODIFIED scenario, including a two-round curation simulation for "an absorbed copy does not circulate" and a two-machine vault test for "the hub travels with vault sync" (the two-machine vault round landed in PR 2)

## 2. Remove the old layer, ship the page, archive (PR 2)

- [x] 2.1 Upgrade step: remove `coffer-memory` hook entries from every agent, delete `derived/memory/` and `derived/resources/memory/`, audit `memory_hook_removed`; settings migration aggregate/distil → memory_sync
- [x] 2.2 Remove hook install/repair/trust reporting for memory, `coffer memory hook`, `POST /api/v1/memory/hook`, the `memory_hook` connection part
- [x] 2.3 Remove prompt-time retrieval, the session ledger, channel-turn index and note injection
- [x] 2.4 Remove partitions, raw store, distil, retirement, tidy hand-off, note routes, Delivered, the `memory` resource kind and its derived resources, and the storage cache it filled
- [x] 2.5 Remove the obsolete `coffer memory` subcommands; the group keeps one command per operation of the new page
- [x] 2.6 Delete tests for removed scenarios; `scripts/audit_acceptance.py` clean
- [x] 2.7 Memory page: sync header (switch, interval, Sync now, last/next), preview panel, projects table, project detail with per-agent copy state, agents' curation rows with Curate now, Undo sync…; i18n en/zh; agent Hooks tab without memory
- [x] 2.8 Turn the worker on by default
- [x] 2.9 Spec deltas for the other capabilities; memory `data-model.md` rewritten; regenerate `contracts/` and frontend types
- [x] 2.10 docs-site en + zh: memory guide, memory architecture, principles, filesystem, CLI and REST references, glossary, concepts, agents guide (hooks)
- [x] 2.11 ADRs: delete the superseded memory ADRs and the hook-installation ADR with their index rows; rewrite the ADRs that cited them to read as today; research note pointer
- [x] 2.12 Update the memory spec's Purpose to the sync design at archive
- [x] 2.13 `npx openspec validate --all --strict`, `make verify`
- [x] 2.14 Archive the change

## 3. After the merge

- [ ] 3.1 Redraw the Context canvas Memory boards and the Agents canvas Hooks board; publish (canvases live outside the repository)
