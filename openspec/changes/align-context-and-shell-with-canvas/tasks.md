## 1. Automatic upkeep on its page

- [x] 1.1 `last_pass_at` / `next_pass_at` on every upkeep pass of the internal-engine settings read (audit log for last, the worker's wait for next)
- [x] 1.2 Knowledge header **Automatic** control: curate switch, interval with its default named, Curate now over every collection with items waiting, last / next line, **Curation runs on** once the registry names several machines (owner fault shown on the pill and in the popover)
- [x] 1.3 Memory header and partition header **Automatic** control: one switch over `aggregate` + `distil`, the `aggregate` interval, last / next read
- [x] 1.4 Settings › General keeps only Coffer's model: the upkeep card and the curation owner line removed

## 2. Knowledge

- [x] 2.1 A collection has no title: migration `0133` strips stored titles, the kind refuses one, the heading is the folder name with an editable description
- [x] 2.2 Restore a deleted collection or document from Recent changes (`POST /api/v1/knowledge/changes/{version}/restore`, CLI parity), refused when it would overwrite
- [x] 2.3 The page follows boards 5.1.01–5.1.29: reader and rail, history and compare, editor and stale save, Recent changes with filters, inbox, curation pass and undo, collection, dialogs, upload states, first run, no model

## 3. Memory

- [x] 3.1 `GET /api/v1/memory/reading`: the last read and each agent it could not read; header "Read … · 1 agent failed" and the failure banner with Retry and Open Activity
- [x] 3.2 Update memory's progress on the run list; header "Reading agents' memory…" / "Distilling 2 of 5 partitions", rows "Distilling…"
- [x] 3.3 Partitions table columns Partition, Path, Sample memory, Memories, Sources, Distil; memories name the agents they came from; first run with the agents found on this Mac, or Connect an agent

## 4. Shell, palette, Overview, Foundations

- [x] 4.1 Palette jumps to pages and objects only (Recent, Best match, per-kind groups)
- [x] 4.2 Sidebar count badges only for things that need the user; no badge for the Knowledge inbox
- [x] 4.3 Daemon reconnecting / offline states in the workspace, version menu with theme and language, update card, 404 with the closest page
- [x] 4.4 Overview follows boards 1.3.01–1.3.07; a hand-edited memory hook Coffer could not rewrite is a Needs-you row opening the agent's Hooks tab
- [x] 4.5 Tokens and shared components follow the Foundations sheets

## 5. Wrap-up

- [x] 5.1 en / zh strings, docs-site guides and architecture pages, generated contracts and references
- [ ] 5.2 `make verify`, `make verify-visual` with the moved baselines re-recorded
- [ ] 5.3 Archive the change (`npx openspec archive align-context-and-shell-with-canvas --yes`)
