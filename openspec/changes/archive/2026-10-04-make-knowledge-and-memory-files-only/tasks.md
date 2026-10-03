## 1. Knowledge backend

- [x] 1.1 Remove `coffer__write`: the builtin tool, its registration and advertising, the feature gate for it, and the gateway `initialize` text that names it
- [x] 1.2 Recognise a new inbox file written outside Coffer during the sweep's on-disk step: normalise its frontmatter (design §1), commit it, audit `knowledge_written` with `actor_reported`
- [x] 1.3 Rewrite curation's precedence instruction to newer-or-better-evidenced with no writer exemption; keep the changed-bytes refusal and the frontmatter-key preservation
- [x] 1.4 Update the `coffer-guide` manual: add knowledge by writing into `<collection>/.inbox/`, edit documents in place, never run git in the vault; drop every `coffer__write` and `coffer knowledge` mention; re-render

## 2. Memory backend

- [x] 2.1 Remove triggers: domain, store, service, routes, distil proposal fields, hook guard and error paths, the CLI hook's local trigger read, ledger trigger keys, `memory_trigger_*` events
- [x] 2.2 Install two hook entries (`SessionStart`, `UserPromptSubmit`) for Claude Code and Codex; confirm the reconciler rewrites four to two and that Codex trust hashes for the two survive
- [x] 2.3 Migration: delete `vault/memory-triggers/`
- [x] 2.4 Add `PUT /api/v1/memory/partitions/{uid}/notes/{slug}` (fingerprint, conflict body, `updated_at`, `memory_note_edited`)
- [x] 2.5 Give distil the newer-or-better-evidenced instruction for an edited note

## 3. CLI and REST surfaces

- [x] 3.1 Remove `coffer knowledge`, `coffer memory` (keep `hook`, hidden), `coffer path knowledge|memory`
- [x] 3.2 Remove every knowledge and memory route the web UI does not call (audit `frontend/src/lib/api/knowledge.ts`, `memory.ts`, hooks); keep `POST /api/v1/memory/hook`
- [x] 3.3 Drop `knowledge`, `memory` and `path knowledge|memory` from the parity test's reviewed table
- [x] 3.4 Regenerate contracts and frontend types

## 4. Frontend and canvas

- [x] 4.1 Memory partition page: Edit on the selected memory, reusing the knowledge editor's conflict dialog
- [x] 4.2 Agents Hooks tab and any hook counts show two memory entries
- [ ] 4.3 Redraw the Memory partition boards and the Agents Hooks board; publish the canvas

## 5. Specs, policy and docs

- [x] 5.1 Spec deltas: knowledge, memory, resource-framework, mcp-gateway, experimental-features, agent-registry (+ claude-code, codex), vault-storage, vault-sync, daemon, web-ui
- [x] 5.2 `data-model.md` for knowledge, memory and vault-storage
- [x] 5.4 docs-site (en + zh): knowledge and memory guides and architecture pages, references (CLI, REST, MCP tools, filesystem, glossary, error codes), concepts and quickstart; regenerate the CLI and REST references
- [x] 5.5 ADRs: rewrite "Memory reaches a session at three moments" to two moments; update "Knowledge is plain files", "Knowledge curation", "Coffer ships its own skill", "Agent hook installation"

## 6. Verify

- [x] 6.1 Acceptance markers follow the scenarios; removed scenarios lose their tests
- [x] 6.2 `npx openspec validate --all --strict`, `make lint`, `make verify`
- [x] 6.3 Archive the change
