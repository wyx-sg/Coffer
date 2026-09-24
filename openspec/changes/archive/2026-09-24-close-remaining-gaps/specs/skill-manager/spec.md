## MODIFIED Requirements

### Requirement: Offer every skill operation on REST, CLI and web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the Skills page in the web UI — except `verify`, which has no web surface ("Report skill drift on request"). The master-folder file viewer and editor ("Show a skill's master folder read-only", "Save an existing skill file conditionally") are on all three: `coffer skill files <name> [--json]` prints the tree, `coffer skill cat <name> <path> [--json]` a file with its fingerprint, and `coffer skill write <name> <path>` saves one from stdin or `--from-file`, conditional on the fingerprint of a fresh read unless `--fingerprint` names the read the edit started from. Per-(skill, agent) enable/disable is not among them: the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes and the `coffer skill enable|disable` CLI commands are REMOVED. Delivery is driven by the skill's `enabled` flag and `scope` through the generic resource surfaces — `coffer scope set skill <name> --agents …` and `coffer resource enable|disable skill <name>`.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with import via a folder picker. It manages the skill resource itself, not per-agent bindings: a skill's detail view has an Overview metadata tab and a Files tab (file tree plus the viewer of "Show a skill's master folder read-only"), where every file and folder offers "open in external editor" and "reveal in file manager". The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via `coffer skill ...`,
- **THEN** the same effect is achieved in either surface and CLI provides `--json` for read operations,
- **AND** a skill's files are listed, read with their fingerprint and saved from `coffer skill files|cat|write`, a stale save exiting with the conflict code and a builtin skill's save refused with the route's message.

### Requirement: Save an existing skill file conditionally
The system MUST provide a write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as "Show a skill's master folder read-only"; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. The in-app editor, programmatic REST clients and `coffer skill write` share this one endpoint. Because the master folder is also a folder the user edits in their own editor, file reads MUST return a **content fingerprint** (a digest of the file's raw on-disk bytes — not of the possibly-truncated text returned, so an oversized file's fingerprint still round-trips and an edit past the truncation point is still detected), and a write MAY carry that fingerprint back: when it no longer matches the bytes on disk the write MUST be rejected with `conflict` (409) and the file left byte-identical, so the user re-reads and reapplies rather than silently losing the other edit. A write that omits the fingerprint stays unconditional (last writer wins), which is what a programmatic client that never read the file first needs.

#### Scenario: edit and save a skill file
- **GIVEN** an imported skill that contains an existing text file,
- **WHEN** the user edits that file in the in-app editor (or a programmatic REST client or `coffer skill write` saves new contents for it) by its folder-relative path, passing back the fingerprint the read returned,
- **THEN** Coffer overwrites the file atomically and returns the file's new fingerprint, and a subsequent read returns the new contents; writing a non-existent path, a path outside the master folder, an existing binary file, or content over the size cap is rejected (`404`/`400`) and the file is left unchanged. A save that omits the fingerprint still writes, so programmatic clients that never read the file first keep working.

#### Scenario: reject a stale save of a skill file
- **GIVEN** an imported skill file opened in the in-app editor, whose read returned a content fingerprint,
- **WHEN** the user changes that same file in their own external editor and only then saves the in-app buffer with the now-stale fingerprint,
- **THEN** Coffer rejects the save with `conflict` (409, `SKILL_FILE_STALE`) and leaves the externally edited file byte-identical on disk; re-reading yields the current fingerprint and the retried save succeeds.
