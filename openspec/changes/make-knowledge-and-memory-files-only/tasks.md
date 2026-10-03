## 1. Knowledge backend

- [ ] 1.1 Remove `coffer__write`: the builtin tool, its registration and advertising, the feature gate for it, and the gateway `initialize` text that names it
- [ ] 1.2 Recognise a new inbox file written outside Coffer during the sweep's on-disk step: normalise its frontmatter (design §1), commit it, audit `knowledge_written` with `actor_reported`
- [ ] 1.3 Rewrite curation's precedence instruction to newer-or-better-evidenced with no writer exemption; keep the changed-bytes refusal and the frontmatter-key preservation
- [ ] 1.4 Update the `coffer-guide` manual: add knowledge by writing into `<collection>/.inbox/`, edit documents in place, never run git in the vault; drop every `coffer__write` and `coffer knowledge` mention; re-render

## 2. Memory backend

- [ ] 2.1 Remove triggers: domain, store, service, routes, distil proposal fields, hook guard and error paths, the CLI hook's local trigger read, ledger trigger keys, `memory_trigger_*` events
- [ ] 2.2 Install two hook entries (`SessionStart`, `UserPromptSubmit`) for Claude Code and Codex; confirm the reconciler rewrites four to two and that Codex trust hashes for the two survive
- [ ] 2.3 Migration: delete `vault/memory-triggers/`
- [ ] 2.4 Add `PUT /api/v1/memory/partitions/{uid}/notes/{slug}` (fingerprint, conflict body, `updated_at`, `memory_note_edited`)
- [ ] 2.5 Give distil the newer-or-better-evidenced instruction for an edited note

## 3. CLI and REST surfaces

- [ ] 3.1 Remove `coffer knowledge`, `coffer memory` (keep `hook`, hidden), `coffer path knowledge|memory`
- [ ] 3.2 Remove every knowledge and memory route the web UI does not call (audit `frontend/src/lib/api/knowledge.ts`, `memory.ts`, hooks); keep `POST /api/v1/memory/hook`
- [ ] 3.3 Replace the CLI parity test with the command-reason list and its test (design §5); list other kinds' commands as `legacy`
- [ ] 3.4 Regenerate contracts and frontend types

## 4. Frontend and canvas

- [ ] 4.1 Memory partition page: Edit on the selected memory, reusing the knowledge editor's conflict dialog
- [ ] 4.2 Agents Hooks tab and any hook counts show two memory entries
- [ ] 4.3 Redraw the Memory partition boards and the Agents Hooks board; publish the canvas

## 5. Specs, policy and docs

- [ ] 5.1 Spec deltas: knowledge, memory, resource-framework, mcp-gateway, experimental-features, agent-registry (+ claude-code, codex), vault-storage, vault-sync, daemon, web-ui
- [ ] 5.2 `data-model.md` for knowledge, memory and vault-storage
- [ ] 5.3 `.agents/openspec.md`: the minimal-CLI rule replaces REST/CLI parity
- [ ] 5.4 docs-site (en + zh): knowledge and memory guides and architecture pages, references (CLI, REST, MCP tools, filesystem, glossary, error codes), concepts and quickstart; regenerate the CLI and REST references
- [ ] 5.5 ADRs: rewrite "Memory reaches a session at three moments" to two moments; update "Knowledge is plain files", "Knowledge curation", "Coffer ships its own skill", "Agent hook installation"

## 6. Verify

- [ ] 6.1 Acceptance markers follow the scenarios; removed scenarios lose their tests
- [ ] 6.2 `npx openspec validate --all --strict`, `make lint`, `make verify`
- [ ] 6.3 Archive the change
