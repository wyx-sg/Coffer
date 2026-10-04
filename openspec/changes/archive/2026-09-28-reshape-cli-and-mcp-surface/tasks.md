# Tasks

## 1. Fixed names and `title` (backend)

- [x] 1.1 Add `name_fixed: bool = False` to `Kind` (`domain/resource.py`) and set it for `mcp_server` and `skill`; `resource_rename_ops.rename` refuses a changed name on such a kind with a new `NameImmutable` error mapped to `409 NAME_IMMUTABLE` before any hook or write — verify with a unit test that a PATCH renaming an MCP server or a skill returns 409 and leaves the row, the skill master folder and the audit log untouched
- [x] 1.2 Remove skill's `on_rename` hook and `SkillService` rename path (`application/skill/kind.py`, `service.py`, `skill_file_routes.py` comment) — verify skill tests pass with the rename tests deleted or converted to refusal tests
- [x] 1.3 Alembic migration adding nullable `resources.title` (≤80 chars); carry `title` through `Resource`, `ResourceRepo`, `ResourceOut`/`ResourceUpdate`, and the vault-sync resource document (absent key → null) — verify `alembic upgrade head` on a copy of a real vault and a round-trip test through PATCH and through sync serialize/apply
- [x] 1.4 Cap `mcp_server` names at 24 characters in the kind's `validate_name` at registration only (existing longer rows still load and serve) — verify registration of a 25-character name is refused with a message naming the cap
- [x] 1.5 Add `client_name_length` to each discovered capability row (length of `mcp__coffer__<server>__<tool>`) in the capabilities read — verify with a unit test over a long tool name

## 2. MCP built-ins

- [x] 2.1 Delete `application/diagnostics.py`, `application/memory/builtin_recall_tool.py` and their registrations; the gateway advertises exactly `coffer__search_tools` and (knowledge on) `coffer__write` — verify `tools/list` in the gateway integration test
- [x] 2.2 Rewrite the handshake instructions (`application/mcp/gateway_instructions.py`) and the `coffer-guide` render (`application/knowledge/guide_render.py`) to name two tools, the memory root to grep and `coffer log` / `coffer path logs` — verify the ≤800-char cap test and the guide golden test
- [x] 2.3 Update the session-start delivery text so it names the memory root that spans every partition — verify the delivery composition test

## 3. CLI framework

- [x] 3.1 Build the lifecycle-verb factory (`surfaces/cli/_kind_verbs.py`): `list|show|add|edit|rm|enable|disable|scope` from a `Kind`, omitting unsupported verbs, `--json` on reads, `--title`/`--description` on `edit`, name-or-uid resolution — verify unit tests per verb against a fake daemon client
- [x] 3.2 Build `coffer config` over a setting-key registry (`surfaces/cli/config_cmd.py`) with every key in design.md D2, typed validation, `unset` → default, `list [prefix]` with type/default/help — verify a test per key family (daemon, feature, engine, transcribe, retention, credentials)
- [x] 3.3 Build `coffer log audit|mcp|daemon|prune` (`surfaces/cli/log_cmd.py`) over the existing routes with `--since --errors --status --kind --name --server --limit --json` — verify against a daemon fixture holding one row of each record
- [x] 3.4 Build `coffer path` (`surfaces/cli/path_cmd.py`) for knowledge, memory, skill, agent config/memory/transcripts, logs and vault — verify each target prints an existing absolute path in an isolated `COFFER_HOME`
- [x] 3.5 Build `coffer scan|adopt|discard` (`surfaces/cli/scan_cmd.py`) over agent discovery, unmanaged skills and direct MCP entries — verify one row of each kind is listed, adopted and (skill, mcp) discarded

- [x] 3.6 Add `DELETE /api/v1/daemon/features/{key}` clearing this machine's setting so the feature returns to the channel default (service method + route + contract), and turn the strict xfail on experimental-features "unsetting a feature returns it to the channel default" into a pass
- [x] 3.7 Change the switched-off-feature hint everywhere (`_client.py`, `domain/features.py`, `channel/document_save.py`, their tests) from `coffer daemon features enable` to `coffer config set feature.<key> on`

## 4. CLI per-kind groups

- [x] 4.1 `mcp`: verbs + `test` (refresh then health) + `cap list|enable|disable` with `tool:`/`prompt:`/`resource:` refs; flag `client_name_length > 64` in `cap list` — verify the mcp CLI tests
- [x] 4.2 `agent`: verbs + `connect|disconnect`, `show` carrying `coffer_mcp` and `memory_delivery`, `transcript [<id>]`, `models`, `config edit|rm`, `plugin list|enable|disable|rm` — verify the agent CLI tests
- [x] 4.3 `skill` (verbs, `add <folder>`, `verify`), `knowledge` (verbs, `write`, `upload`, `curate`), `memory` (verbs without `add`, `sync`, `distil`, `context`, `delivery on|off`) — verify each group's CLI tests and that `memory context` output is byte-identical to before
- [x] 4.4 `provider` (verbs, `switch`, `builtin`, `key`), `channel` (verbs, `pair`, `bind`, `notify`, `edit` with the group-gating switches), `credentials` (`set`, `get`, `list`, `rm`) — verify each group's CLI tests
- [x] 4.5 `daemon` (`start|stop|restart|status|rotate-token|service install|uninstall|status`, with passes in flight in `status`) and `sync` (`restore` without `--at` undoes the last round; `status` includes the remote; `machine rm`) — verify the daemon and sync CLI tests
- [x] 4.6 Switch `surfaces/cli/main.py` to the new tree and delete the retired modules (`resource_cmd.py`, `scope_cmd.py`, `audit_cmd.py`, `retention_cmd.py`, `engine_*`, `daemon_port_cmd.py`, `daemon_features_cmd.py`, `skill_file_cmd.py`, `memory_delivery_cmd.py`, `agent_native_memory_cmd.py`, …) — verify `coffer --help` and every group's `--help` render

- [x] 4.7 Sweep user-facing messages that still name removed commands (e.g. `domain/skill/drift.py` → `coffer skill add` / `coffer adopt skill`), and drop `--description` from `coffer knowledge edit` because a collection's description comes from its README — verify `grep -rn` over `backend/coffer` for every removed command name finds nothing user-facing

- [x] 4.8 Give `coffer mcp edit` the config and timeout flags the web UI's edit form sets (transport command/args/url, env and header credential refs, timeouts) so an MCP server's config is changeable from the CLI — verify a CLI test round-trips each flag through `PATCH /resources/{uid}`

## 5. Web UI

- [x] 5.1 Show `title` in place of the name on list and detail pages of every kind, editable in each kind's edit form; MCP server and skill pages show the name as fixed — verify component tests
- [x] 5.2 MCP JSON import preview shows the fixed server name and warns above 24 characters; the Tools tab flags `client_name_length > 64` — verify `AddMcpServerDialog` and `CapabilityList` tests
- [x] 5.3 Remove the `coffer__diagnose` citations from the Activity page copy — verify the Activity tests

## 6. Tests and acceptance markers

- [x] 6.1 Rewrite the reviewed command table in the REST/CLI parity test to the new tree and add the reviewed list of file-backed REST reads answered by `coffer path` — verify it passes in both directions
- [x] 6.2 For each spec below, add a test carrying `acceptance(<spec>, <scenario>)` for every NEW scenario the delta introduces, and rewrite the test behind every existing marker whose scenario text the delta changed — verify `scripts/audit_acceptance.py` reports no uncovered scenario:
  - resource-framework: 13 new (title, `log audit`, `config`, `path`, `scan/adopt/discard`, lifecycle verbs, `scope`, fixed name, retention, file-backed parity), 10 changed
  - mcp-gateway: 6 new (two built-ins, 24-char cap, long client name flag, `test`, `cap`, `log mcp`), 13 changed
  - skill-manager: 6 new (fixed name ×2, title, `scan` rows, `adopt/discard`, group verbs), 13 changed
  - agent-registry: 12 new (`scan`/`adopt`/`discard`, `connect`/`disconnect`, `show` fields, `config edit --from-file`, `path agent`, `transcript`, `enable/disable`, title), 25 changed
  - memory: 5 new (no memory tool, memory root, `path memory`, `agent show` delivery state, two renamed compose scenarios), 8 changed
  - knowledge: 2 new (manual names two tools, `path knowledge`), 8 changed
  - daemon: 4 new (passes in flight, port with no daemon, `path logs`, `log daemon`), 10 changed
  - internal-engine: 1 new, 6 changed; provider-switching: 3 new, 11 changed
  - vault-sync: 5 new (title ×3, `restore` without `--at`, `status` remote), 6 changed
  - web-ui: 4 new (titles ×2, Activity route, import review), 4 changed
  - experimental-features: 1 new, 11 changed; credentials: 2 new, 3 changed; channels: 1 new, 4 changed
- [x] 6.3 Delete or move the markers of removed scenarios — skill-manager "renaming a skill carries its master folder, links and frontmatter name", "manage unmanaged skills from the skill command group", "an empty or interactive `skill write` saves nothing", "a truncated `skill cat` does not pass for the whole file"; memory "advertise recall as a locator and no remember tool", "recall answers with locations, and never with a retired note", "compose context and recall without creating a partition", "compose context and recall without calling any model"; web-ui "an agent reads recent changes and failures in one call" — verify `scripts/audit_acceptance.py` passes
- [x] 6.4 Update e2e specs that drive removed commands — verify `make e2e` (spare-port run with `COFFER_CORS_ORIGINS`)

## 7. Contracts, docs and conventions

- [x] 7.1 `contracts/api.openapi.yaml`: `title` on resource schemas, `NAME_IMMUTABLE` error, `client_name_length` on capabilities; regenerate frontend codegen — verify `make verify-contract`
- [x] 7.2 `data-model.md` for `resources.title`
- [x] 7.3 Narrow the parity rule in `.agents/openspec.md` and `openspec/config.yaml` (design.md D8)
- [x] 7.4 Add ADR `docs/decisions/names-visible-to-agents-are-fixed.md` and cross-link it from `resource-identity-is-an-immutable-uid.md`
- [x] 7.5 Regenerate `docs-site/reference/cli.md` and rewrite `docs-site/reference/mcp-tools.md`; update every guide and architecture page quoting a removed command or tool (`grep -rn "coffer resource\|coffer scope\|coffer audit\|coffer retention\|coffer engine\|coffer__recall\|coffer__diagnose" docs-site`) — verify `make docs-reference` and `make lint`
- [x] 7.6 Update the shipped `coffer-vault` skill and any skill body quoting removed commands; add a lint gate that fails on removed command names under `docs-site/`, shipped skills and `e2e/` — verify the gate fails on a planted old name and passes on the tree
- [x] 7.7 Update the main specs' `## Purpose` text that names removed commands or tools: resource-framework (`coffer engine upkeep runs`, `coffer resource|scope|audit|retention`, the parity sentence), mcp-gateway ("rename" in the framework list), web-ui (the `coffer__diagnose` sentence), internal-engine (`coffer engine …`, `provider internal-default|transcribe-default`), daemon (the "gap with no reason" sentence about the daemon log), credentials (`delete|storage`), skill-manager (`coffer skill files|cat|write`) — verify by grepping the main specs for every removed command name
- [x] 7.8 Move requirement citations off removed titles — `.agents/openspec.md` example ("Keep one master folder per skill and carry it through a rename" → "Keep one master folder per skill"), `docs/decisions/cross-platform-skill-delivery.md`, `backend/coffer/application/mcp/gateway.py` and other code/test comments citing "Create partitions only by aggregation" or "Send content out only for distil" (→ "Provision partitions only from aggregation", "Send file content out only for distil"), `agent_unmanaged_skill_routes.py` ("Expose unmanaged-skill operations on REST, CLI and web"), `test_cli_parity.py` ("Cover skill management on REST, the CLI and the web") — verify `python3 scripts/check_spec_citations.py` prints no "removed or renamed" note

- [x] 7.9 Replace the illustrative `coffer scan` and `coffer mcp cap list` output in `docs-site/start/quickstart.md` with output captured from a real run in an isolated home; drop the `coffer__recall` mention from `openspec/specs/memory/contracts/api.openapi.yaml`

## 8. Verify and archive

- [x] 8.1 Run `make verify` (with the frozen venv) and fix every failure
- [x] 8.2 Run `npx openspec validate reshape-cli-and-mcp-surface --strict`, then `npx openspec archive reshape-cli-and-mcp-surface --yes` in the same PR and confirm `npx openspec validate --all --strict` passes
