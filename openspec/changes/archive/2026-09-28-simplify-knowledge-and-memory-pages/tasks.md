## 1. Backend — resource framework and migration

- [x] 1.1 `Kind.toggleable` (default true); the enable/disable ops refuse a non-toggleable kind with `RESOURCE_NOT_TOGGLEABLE` (409); `toggleable` on the resource read; `knowledge` and `memory` declare false and drop `on_enabled_changed`
- [x] 1.2 Alembic migration enabling every `knowledge` and `memory` row stored disabled
- [x] 1.3 Test acceptance(resource-framework, "a non-toggleable kind refuses to be disabled")

## 2. Backend — knowledge

- [x] 2.1 Serve every collection: the service's enabled filter goes; `coffer__write` refuses only an unknown collection
- [x] 2.2 Tree route lists a collection root's `.inbox/` and its items; read route reads an inbox item; nothing else hidden
- [x] 2.3 Read carries `fingerprint`; `PUT /api/v1/knowledge/file` saves a body, keeps frontmatter, 409 `KNOWLEDGE_FILE_CONFLICT` on a stale fingerprint, refuses inbox items
- [x] 2.4 `coffer knowledge save <path> <body-file>` reads the fingerprint and saves through `PUT /file`
- [x] 2.5 Tests acceptance(knowledge, "expose every knowledge operation on both surfaces"), (knowledge, "every collection is in every agent's skill"), (knowledge, "leave hidden entries out of every listing"), (knowledge, "save an edited body and refuse a stale one")

## 3. Backend — memory

- [x] 3.1 Serve every partition on delivery and recall
- [x] 3.2 Partition tree omits `.raw/`, reading under it is refused; `FileNodeOut.derived` removed
- [x] 3.3 `POST /memory/sync` and `coffer memory sync` aggregate then distil every partition with new raw entries; a running pass is reported as skipped
- [x] 3.4 Tests acceptance(memory, "a partition is registered as a resource keyed on its repository"), (memory, "one action reads new agent memory and distils it"), (memory, "a partition's own directory is browsable as a file tree")

## 4. Contracts

- [x] 4.1 `knowledge/contracts/api.openapi.yaml`, `memory/contracts/api.openapi.yaml`, the resource contract, error codes; `knowledge/data-model.md`, `memory/data-model.md`; regenerate frontend types

## 5. Frontend

- [x] 5.1 Knowledge detail: drop filter and pending banner; `.inbox` folder in the tree; preview becomes the skill viewer's Edit / Save with conflict handling; inbox items read-only
- [x] 5.2 Knowledge and memory lists: drop the Status column and bulk enable/disable; detail headers drop ScopeControl
- [x] 5.3 Memory: one Update memory button on list and detail; `.raw` handling and derived notice removed; frontmatter shown as metadata in Markdown previews
- [x] 5.4 Every file tree and preview fills the window to its bottom edge
- [x] 5.5 Tests acceptance(knowledge, "the viewer shows one tree of documents"), (knowledge, "edit a document in place"), (memory, "browse a partition as a file tree with a read-only preview"), (web-ui, "a kind that cannot be disabled shows no status control")

## 6. Docs and close-out

- [x] 6.1 docs-site guides and architecture pages for knowledge and memory; ADR note where "enabled is the only gate" is recorded
- [x] 6.2 `make verify`
- [x] 6.3 `npx openspec archive simplify-knowledge-and-memory-pages --yes`
