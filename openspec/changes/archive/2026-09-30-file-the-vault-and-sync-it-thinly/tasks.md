## 1. Vault core

- [x] 1.1 `domain/vault/`: layout and classes, writers and trailers, resource document (JSON, unknown fields kept), format versions and upgrade chains, findings, content ids, write-path value types
- [x] 1.2 `infrastructure/vault/`: class directories, git plumbing, repository (history, trees, blobs, status, staging), the writer (lock, compare-and-swap, validation, one commit per operation, settle of hand edits, problems), JSON store for `local/`, scanner (watch hint + quiet check + periodic and boot scans)
- [x] 1.3 `application/vault/`: ports, composite validator, history/diff/restore service, attention source
- [x] 1.4 Tests for the core (unit + integration against real git)

## 2. Resources and state as files

- [x] 2.1 File resource store (vault / local / derived by kind), reach store in `local/reach.json`, uid index and revision counter in `derived/`
- [x] 2.2 `Resource.id` removed; history tables re-keyed to uids; `runs.db` revision 0136
- [x] 2.3 Resource validator (schema, uid rules, format versions, secret scan) registered on `resources/`
- [x] 2.4 MCP preferences, channel pairings, engine settings as vault state documents; seen-times and health and skill bindings in `derived/derived.db`
- [x] 2.5 Retention policies and skill source status in `local/`
- [x] 2.6 Tests moved off the SQL resource repository

## 3. Credentials as files

- [x] 3.1 Ciphertext store over `vault/secret/<ref>.enc`
- [x] 3.2 Secret boundary (bindings, approvals, settings) over `local/secret-boundary/`

## 4. Class directories

- [x] 4.1 knowledge → `vault/knowledge`, skills → `vault/skills`, memory → `derived/memory`, media and workspace → `content/`, transcript cache → `derived/cache/agent`
- [x] 4.2 Knowledge history on the vault repository; curation finds edits by blob, not mtime

## 5. Writer model surfaces

- [x] 5.1 Scanner and validator wired at boot; problems on the attention list
- [x] 5.2 Mandatory expected fingerprints on skill and knowledge saves
- [x] 5.3 `GET /api/v1/vault/history`, `/diff`, `/content`, `POST /restore`, `GET /problems`; `coffer vault history|diff|show|restore|problems`
- [x] 5.4 Skills History tab

## 6. Thin sync

- [x] 6.1 Round engine: fetch, merge-tree, stop on conflict, guard both directions, snapshot, CAS checkout, push
- [x] 6.2 Stopped round with per-file answers (mine / theirs / edited) and the editor copy
- [x] 6.3 Join new / returning with a preview; same name, different uid = conflict
- [x] 6.4 Rollback from the ten newest snapshots; machines; problems classified
- [x] 6.5 REST + CLI; the translation layer, arbiter, agent resolver and per-kind adapters deleted
- [x] 6.6 Frontend Sync page on the new API

## 7. Migration

- [x] 7.1 One-time migration from `coffer.db` at 0135 into the five classes, with the move manifest
- [x] 7.2 `coffer migrate --rollback` and `--rehearse`
- [x] 7.3 Rehearsal gate test from fixtures of the current schema; rollback byte for byte
- [x] 7.4 Two-machine cross-version sync test

## 8. Specs and docs

- [x] 8.1 `vault-storage` spec; deltas for vault-sync, resource-framework, credentials, knowledge, skill-manager, memory, daemon; acceptance markers on every new scenario
- [x] 8.2 `data-model.md` files describe files; contracts regenerated
- [x] 8.3 docs-site persistence, vault-sync, filesystem reference and guides; ADR amendments; principles clauses
- [x] 8.4 `make verify`; archive the change
