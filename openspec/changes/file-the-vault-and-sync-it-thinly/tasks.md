## 1. Vault core

- [x] 1.1 `domain/vault/`: layout and classes, writers and trailers, resource document (JSON, unknown fields kept), format versions and upgrade chains, findings, content ids, write-path value types
- [x] 1.2 `infrastructure/vault/`: class directories, git plumbing, repository (history, trees, blobs, status, staging), the writer (lock, compare-and-swap, validation, one commit per operation, settle of hand edits, problems), JSON store for `local/`, scanner (watch hint + quiet check + periodic and boot scans)
- [x] 1.3 `application/vault/`: ports, composite validator, history/diff/restore service, attention source
- [x] 1.4 Tests for the core (unit + integration against real git)

## 2. Resources and state as files

- [ ] 2.1 File resource store (vault / local / derived by kind), reach store in `local/reach.json`, uid index and revision counter in `derived/`
- [ ] 2.2 `Resource.id` removed; history tables re-keyed to uids; `runs.db` revision 0117
- [ ] 2.3 Resource validator (schema, uid rules, format versions, secret scan) registered on `resources/`
- [ ] 2.4 MCP preferences, channel pairings, engine settings as vault state documents; seen-times and health and skill bindings in `derived/derived.db`
- [ ] 2.5 Retention policies and skill source status in `local/`
- [ ] 2.6 Tests moved off the SQL resource repository

## 3. Credentials as files

- [ ] 3.1 Ciphertext store over `vault/credentials/<ref>.enc`
- [ ] 3.2 Secret boundary (bindings, approvals, settings) over `local/secrets/`

## 4. Class directories

- [ ] 4.1 knowledge → `vault/knowledge`, skills → `vault/skills`, memory → `derived/memory`, media and workspace → `content/`, transcript cache → `derived/cache/agent`
- [ ] 4.2 Knowledge history on the vault repository; curation finds edits by blob, not mtime

## 5. Writer model surfaces

- [ ] 5.1 Scanner and validator wired at boot; problems on the attention list
- [ ] 5.2 Mandatory expected fingerprints on skill and knowledge saves
- [ ] 5.3 `GET /api/v1/vault/history`, `/diff`, `/content`, `POST /restore`, `GET /problems`; `coffer vault history|diff|show|restore|problems`
- [ ] 5.4 Skills History tab

## 6. Thin sync

- [ ] 6.1 Round engine: fetch, merge-tree, stop on conflict, guard both directions, snapshot, CAS checkout, push
- [ ] 6.2 Stopped round with per-file answers (mine / theirs / edited) and the editor copy
- [ ] 6.3 Join new / returning with a preview; same name, different uid = conflict
- [ ] 6.4 Rollback from the ten newest snapshots; machines; problems classified
- [ ] 6.5 REST + CLI; the translation layer, arbiter, agent resolver and per-kind adapters deleted
- [ ] 6.6 Frontend Sync page on the new API

## 7. Migration

- [ ] 7.1 One-time migration from `coffer.db` at 0116 into the five classes, with the move manifest
- [ ] 7.2 `coffer migrate --rollback` and `--rehearse`
- [ ] 7.3 Rehearsal gate test from fixtures of the current schema; rollback byte for byte
- [ ] 7.4 Two-machine cross-version sync test

## 8. Specs and docs

- [ ] 8.1 `vault-storage` spec; deltas for vault-sync, resource-framework, credentials, knowledge, skill-manager, memory, daemon; acceptance markers on every new scenario
- [ ] 8.2 `data-model.md` files describe files; contracts regenerated
- [ ] 8.3 docs-site persistence, vault-sync, filesystem reference and guides; ADR amendments; principles clauses
- [ ] 8.4 `make verify`; archive the change
