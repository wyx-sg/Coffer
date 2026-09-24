## MODIFIED Requirements

### Requirement: Offer every skill operation on REST, CLI and web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the Skills page in the web UI — except `verify`, which has no web surface ("Report skill drift on request"). The master-folder file viewer and editor ("Show a skill's master folder read-only", "Save an existing skill file conditionally") are on all three: `coffer skill files <name> [--json]` prints the tree, `coffer skill cat <name> <path> [--json]` a file with its fingerprint, and `coffer skill write <name> <path>` saves one from stdin or `--from-file`, conditional on the fingerprint of a fresh read unless `--fingerprint` names the read the edit started from. `skill write` MUST NOT save empty content unless `--allow-empty` is given — stdin already at end-of-file (cron, CI, an agent's shell, `</dev/null`) reads as nothing, and taking that as the new file would empty it silently — and with stdin a terminal and no `--from-file` it MUST refuse up front rather than wait for input; both refusals exit with the usage code (2), say why on stderr and write nothing. `skill cat` on a file the read truncated MUST print the part it has, say on stderr that the file was truncated and how large it is, and exit with the generic failure code (1), so a script never takes the part for the file; with `--json` it exits 0 and the `truncated` flag carries the fact. Per-(skill, agent) enable/disable is not among them: the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes and the `coffer skill enable|disable` CLI commands are REMOVED. Delivery is driven by the skill's `enabled` flag and `scope` through the generic resource surfaces — `coffer scope set skill <name> --agents …` and `coffer resource enable|disable skill <name>`.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with import via a folder picker. It manages the skill resource itself, not per-agent bindings: a skill's detail view has an Overview metadata tab and a Files tab (file tree plus the viewer of "Show a skill's master folder read-only"), where every file and folder offers "open in external editor" and "reveal in file manager". The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via `coffer skill ...`,
- **THEN** the same effect is achieved in either surface and CLI provides `--json` for read operations,
- **AND** a skill's files are listed, read with their fingerprint and saved from `coffer skill files|cat|write`, a stale save exiting with the conflict code and a builtin skill's save refused with the route's message.

#### Scenario: an empty or interactive `skill write` saves nothing
- **GIVEN** an imported skill with an existing text file
- **WHEN** `coffer skill write` runs with stdin at end-of-file, or with an empty `--from-file`, or with stdin a terminal and no `--from-file`
- **THEN** it exits 2 with the reason on stderr and the file is byte-identical
- **AND** the same write with `--allow-empty` empties the file and exits 0

#### Scenario: a truncated `skill cat` does not pass for the whole file
- **GIVEN** an imported skill with a text file larger than the read cap
- **WHEN** `coffer skill cat` prints it
- **THEN** it prints the capped part, names the file's true size on stderr and exits 1
- **AND** `coffer skill cat --json` on the same file exits 0 with `truncated` true and the true `size`
