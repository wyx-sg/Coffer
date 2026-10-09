## 1. Implementation

- [x] 1.1 Drop `title` from the resource model, REST bodies and responses, the resource file and the CLI help
- [x] 1.2 Add `Kind.free_name` for `provider` and `channel`: the name rule, case-insensitive uniqueness and uid file names
- [x] 1.3 Apply the per-kind name rule and the case-insensitive name-taken check in the vault validator
- [x] 1.4 Migrate old-shape provider and channel files on start (title into name, drop the key, file to `<uid>.json`)
- [x] 1.5 Channels: register the typed name directly, rename on the Settings tab, `(id: <uid>)` in the origin block, the thread tool takes the id
- [x] 1.6 Web UI: show the name everywhere

## 2. Specs and docs

- [x] 2.1 Write the spec deltas and the ADR
- [x] 2.2 Update `data-model.md` files and `docs-site/` (English and Chinese)
- [x] 2.3 Archive the change
