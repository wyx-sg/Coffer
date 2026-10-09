## 0. Decide

- [x] 0.1 ADR `sync-memory-into-each-agents-own-memory`; mark the superseded ADRs
- [x] 0.2 Proposal, design and the memory spec delta
- [ ] 0.3 On the maintainer's machine, find where Codex stores "import from Claude Code" with automatic updates, and Claude Code's Auto Dream switch; record both in design §6 and the agent child specs

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
- [ ] 1.12 Tests carrying `acceptance("memory", …)` for every ADDED and MODIFIED scenario, including a two-round curation simulation for "an absorbed copy does not circulate" and a two-machine vault test for "the hub travels with vault sync" (all but the two-machine vault round are in PR 1)

## 2. Remove the old layer (PR 2)

- [ ] 2.1 Upgrade step: remove `coffer-memory` hook entries from every agent, delete `derived/memory/` and `derived/resources/memory/`, audit `memory_hook_removed`; settings migration aggregate/distil → memory_sync
- [ ] 2.2 Remove hook install/repair/trust reporting for memory, `coffer memory hook`, `POST /api/v1/memory/hook`, the `memory_hook` connection part
- [ ] 2.3 Remove prompt-time retrieval, the session ledger, channel-turn index and note injection
- [ ] 2.4 Remove partitions, raw store, distil, retirement, tidy hand-off, note routes, Delivered, the `memory` resource kind and its derived resources
- [ ] 2.5 Remove the obsolete `coffer memory` subcommands; keep what the new page's state needs only if the CLI parity rule asks for it
- [ ] 2.6 Delete tests for removed scenarios; `scripts/audit_acceptance.py` clean

## 3. Page, docs, canvas, archive (PR 3)

- [ ] 3.1 Memory page: sync header (switch, interval, Sync now, last/next), preview panel, projects table, project detail with per-agent copy state, agents' curation rows with Curate now, Undo sync…; i18n en/zh; agent Hooks tab without memory
- [ ] 3.2 Turn the worker on by default
- [ ] 3.3 Spec deltas for resource-framework, vault-storage, vault-sync, experimental-features, agent-registry (+ claude-code, codex), channels, chat, internal-engine, web-ui; memory `data-model.md` rewritten; regenerate `contracts/api.openapi.yaml` and frontend types
- [ ] 3.4 docs-site en + zh: memory guide, memory architecture, design principles ("Pull, not push"), principles (seven kinds → six), filesystem, CLI and REST references, glossary, concepts, agents guide (hooks)
- [ ] 3.5 ADRs: delete the two superseded memory ADRs and their index rows (the new ADR carries their options); rewrite "Tidying Knowledge and Memory Is the Agent's Job" and "Sync Withholds Derived Output" to read as today; research note pointer
- [ ] 3.6 Redraw the Context canvas Memory boards and the Agents canvas Hooks board; publish
- [ ] 3.7 Update the memory spec's Purpose to the sync design at archive
- [ ] 3.8 `npx openspec validate --all --strict`, `make verify`
- [ ] 3.9 Archive the change
