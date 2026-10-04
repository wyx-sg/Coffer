# Tasks — knowledge-curate-and-history

## 1. Curate now drains

- [x] 1.1 `drain_curation`: snapshot of pending items, one pass each in order, stop at `failed` / `no_model`, single-document form, `CurationRunOut`
- [x] 1.2 Upkeep-run progress (`done`, `total`) on the registry and `GET /upkeep/runs`; a `change` event per finished pass
- [x] 1.3 `coffer knowledge curate` prints `n of m` while it waits and one line per pass; `--json`
- [x] 1.4 Frontend adapts to `CurationRunOut` (types regenerated)

## 2. History

- [x] 2.1 `infrastructure/knowledge/history.py`: repository under the knowledge root, exclude file, trailers, transactions, disk snapshot, sync marks, log / show / diff
- [x] 2.2 Commits from every write: save, delete, submit (promote), collection create / rename / remove, the pass (one commit), the sweep's disk snapshot, sync's applier
- [x] 2.3 The item's agent from the `knowledge_written` audit event (now naming the item)
- [x] 2.4 History service: versions, version diff, restore, changes feed with waiting items, one change, undo with the conflict rule
- [x] 2.5 REST routes and schemas; `coffer knowledge history | restore | changes | undo`
- [x] 2.6 503 `KNOWLEDGE_HISTORY_UNAVAILABLE` without git

## 3. Editor, entrances, wording

- [x] 3.1 409 `KNOWLEDGE_FILE_CONFLICT` carries `saved`, `current_body`, `current_fingerprint`
- [x] 3.2 Sweep lists every collection; no "disabled" wording left in knowledge
- [x] 3.3 CLI help and messages: curate / curation, documents, items

## 4. Spec, contract, docs

- [x] 4.1 Acceptance markers for every new scenario; the changed parity scenario
- [x] 4.2 `make contracts`; CLI and REST reference pages regenerated
- [x] 4.3 knowledge spec Purpose and data-model; docs-site knowledge architecture and guide
- [x] 4.4 Archive; `make verify`
