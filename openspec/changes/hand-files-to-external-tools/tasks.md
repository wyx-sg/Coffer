## 1. Plan

- [x] 1.1 Proposal, design, spec deltas

## 2. Agent config files

- [ ] 2.1 Backend: remove config-file content/child routes, service methods, validators, models, `resolved_within`/`remove_tree`; keep the list, the store, backups and `CONFIG_FILE_STALE`; stop emitting the two config-file audit events
- [ ] 2.2 Frontend: Config files tab as a read-only list with Open in editor / Reveal in Finder; Hooks tab file links open the file; MCP parse-error link opens the file; delete editor, LineEditor, notices, New file, hooks
- [ ] 2.3 Tests and markers; contracts regenerated

## 3. Knowledge, memory and skill files

- [ ] 3.1 Backend: remove `PUT /knowledge/file`, `PUT /memory/.../notes/{slug}`, `PUT /skills/{uid}/files/content`, fingerprints and conflict codes
- [ ] 3.2 Frontend: read-only panes with Open in editor / Reveal in Finder; delete editor, compare, conflict banner, draft, leave guard
- [ ] 3.3 Tests and markers

## 4. History

- [ ] 4.1 Backend: remove knowledge per-document history, vault history/diff/content/restore/changes and their services; move describe + changes feed + restore-a-delete; add `POST /api/v1/vault/history/handoff`
- [ ] 4.2 Frontend: delete History tabs, version panels, Recent changes; History dialog on knowledge documents and skills; collection delete asks first; missing master banner without Restore
- [ ] 4.3 Tests and markers

## 5. Sync conflicts

- [ ] 5.1 Backend: drop `base`/`edited`/`merged`/`merged_diff` from file versions
- [ ] 5.2 Frontend: one card for editing / merged-by-agent with Open in editor, Mark resolved, Back to two choices; held deletions answered with two buttons
- [ ] 5.3 Tests and markers

## 6. Shared code

- [ ] 6.1 Remove dead diff/history/editor modules and i18n keys; knip clean

## 7. Docs and close

- [ ] 7.1 Docs site (en + zh): guides, architecture, reference, error codes
- [ ] 7.2 ADR headers (partly superseded), data models, `.agents/frontend.md`
- [ ] 7.3 e2e specs and visual routes
- [ ] 7.4 `make verify`; restore main specs and archive the change
