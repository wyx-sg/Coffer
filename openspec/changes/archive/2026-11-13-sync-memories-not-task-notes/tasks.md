## 1. Backend

- [x] 1.1 Codex reader reads only the v2 summary's topics; delete the v1 reader path, `codex_identity`, `codex_summary`, `search_terms`
- [x] 1.2 Bump `READER_REVISION`
- [x] 1.3 Keep a hub entry whose checkout is gone; exclude the vault checkout
- [x] 1.4 Copy state `over_limit` from the writer's own block selection
- [x] 1.5 Remove curation state, hand-off and enable (service, routes, CLI)
- [x] 1.6 Remove upgrade code: legacy hook removal, retired derived tree, `coffer_*` and rules-file clean-up, `global/` folder, `MEMORY_DELIVERY_CONFIG_INVALID`

## 2. Frontend

- [x] 2.1 Agent Memory tab: copies and writer status only
- [x] 2.2 Memory page: `over_limit` on a row; no global group in the preview
- [x] 2.3 Locales (en, zh), generated contract types

## 3. Spec, docs, ADRs

- [x] 3.1 `openspec/specs/memory/spec.md`, `data-model.md`, `agent-registry/spec.md`
- [x] 3.2 ADRs and index
- [x] 3.3 docs-site en and zh: architecture and guide pages, CLI and error-code reference

## 4. Verify

- [x] 4.1 `make verify`
