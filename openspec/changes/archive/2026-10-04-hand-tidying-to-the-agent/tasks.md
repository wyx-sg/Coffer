## 1. Specs

- [x] 1.1 knowledge delta: remove the curation requirements, promote at once, guide teaches writing and tidying, Tidy hand-off
- [x] 1.2 memory delta: mechanical distil only, `retired:` frontmatter, Tidy hand-off
- [x] 1.3 internal-engine, provider-switching, resource-framework deltas
- [x] 1.4 vault-sync, web-ui, experimental-features deltas
- [x] 1.5 `openspec validate --all --strict` passes

## 2. Backend

- [x] 2.1 coffer-guide: writing, tidying a collection, tidying memory; description triggers
- [x] 2.2 knowledge: delete curation modules, routes and errors; `submit()` always promotes; sweep worker with three mechanical duties; `tidy_handoff` on collections; drop `curated_at`, `local/curation.json`, inbox views
- [x] 2.3 memory: distil mechanical only; `retired:` frontmatter processed; `tidy_handoff` on partitions
- [x] 2.4 engine and providers: delete engine model, internal-default flag and route, curate pass and owner; keep transcription, timeout and aggregate/distil upkeep; retired keys ignored
- [x] 2.5 delete LangChain/LangGraph code and dependencies; refresh `uv.lock` and the PyInstaller spec
- [x] 2.6 wiring, sync lock comments, import-linter contracts
- [x] 2.7 `make contracts` and frontend codegen

## 3. Frontend

- [x] 3.1 Tidy button (auto-sending hand-off) on collections and partitions
- [x] 3.2 Knowledge: remove Curate now, Automatic popover, pass undo, waiting/inbox views, no-model lines, Last curated
- [x] 3.3 Memory: remove the no-model notice and model wording
- [x] 3.4 Settings: delete Coffer's model picker; timeout moves into Speech-to-text
- [x] 3.5 Providers and Sync: drop the engine use, internal-default actions, Runs curation tag
- [x] 3.6 i18n en + zh; error-code fixture

## 4. Tests

- [x] 4.1 backend tests and acceptance markers follow the deltas
- [x] 4.2 frontend tests; e2e specs

## 5. Docs and design

- [x] 5.1 docs-site knowledge, memory, providers, configuration, filesystem, error codes, glossary, architecture pages (en + zh)
- [x] 5.2 ADRs: remove the curation, internal-engine and owner-machine records; edit the ones that mention them; update the index
- [x] 5.3 Context, Shell, Agents and System canvases

## 6. Verify and ship

- [x] 6.1 `make verify`
- [x] 6.2 archive the change, open the PR
