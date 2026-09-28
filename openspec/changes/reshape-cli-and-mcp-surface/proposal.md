# Proposal: Reshape the CLI and MCP surface

## Why

Coffer's command line has grown to 16 groups and 159 commands, one group at a time,
and it shows: `coffer mcp remove` and `coffer resource delete` call the same route,
setting the engine's model takes one command in `provider` and another in `engine`,
three spellings of delete coexist, and about twenty commands only print or overwrite
plain files an agent or a person can open directly. The MCP side carries two
built-in tools, `coffer__recall` and `coffer__diagnose`, that answer questions an
agent can already answer with its own file tools or with a CLI command. Separately,
an MCP server's name can be changed from the CLI even though that name is baked into
every tool name an agent sees (`<server>__<tool>`), so a rename silently breaks agent
permission rules and skills that cite the old tool names. Every agent client and
gateway surveyed treats that name as fixed once registered.

## What Changes

- **BREAKING** The MCP gateway advertises two built-in tools, `coffer__search_tools`
  and `coffer__write`. `coffer__recall` and `coffer__diagnose` are removed; the
  handshake instructions and the `coffer-guide` manual point agents at the memory
  directory and at `coffer log` instead.
- **BREAKING** The CLI is rebuilt around one grammar. Every resource kind's group
  offers the same lifecycle verbs, `list`, `show`, `add`, `edit`, `rm`, `enable`,
  `disable` and `scope`, generated from the kind registry and limited to the verbs
  the kind supports. A group adds only the operations that are unique to its kind.
  The kind-agnostic `coffer resource` and `coffer scope` groups are removed.
- **BREAKING** Settings move to `coffer config list|get|set|unset <key>`. This covers
  the daemon port, experimental features, the engine's connection, model, timeout,
  upkeep passes and curation owner, the speech-to-text connection and model,
  retention periods, and where the credential master key is stored. The per-setting
  subcommands under `daemon port`, `daemon features`, `engine`, `retention`, and
  `credentials storage` are removed, as are `provider internal-default` and
  `provider transcribe-default`.
- **BREAKING** Records are read with `coffer log audit|mcp|daemon` and pruned with
  `coffer log prune`. This replaces `coffer audit list`, `coffer mcp invocations`
  and `coffer retention prune-now`. The daemon log gains a command-line reader.
- **BREAKING** Plain files are located with `coffer path` instead of being printed by
  per-kind commands. The removed commands are `knowledge ls|read|delete`,
  `memory notes|note|retired|ls|read`, `skill files|cat|write`,
  `agent config ls|cat|files` and `agent native-memory|native-memory-files`. Their
  REST routes remain for the web UI.
- **BREAKING** Anything an agent holds that Coffer does not manage is handled by
  `coffer scan`, `coffer adopt` and `coffer discard`. These replace `agent detect`,
  `agent mcp entries|adopt|remove-entry` and `skill unmanaged|adopt|rm-unmanaged`.
- The remaining per-kind commands are renamed or merged where they duplicated each
  other:
  - `mcp refresh` and `mcp test` become `mcp test`.
  - `mcp tool|resource|prompt list|enable|disable` becomes `mcp cap list|enable|disable`.
  - `agent mcp install|uninstall|status` becomes `agent connect|disconnect`, with the
    status reported by `agent show`.
  - `memory delivery-install|delivery-remove` becomes `memory delivery on|off`.
  - `sync rollback` becomes `sync restore` with no revision.
  - `sync remote show` is folded into `sync status`.
  - `engine upkeep runs` is folded into `daemon status`.
- **BREAKING** A resource's name is fixed after registration for any kind whose name
  is visible outside Coffer, which today means MCP servers and skills. A rename of
  one of these is refused. Every resource gains an optional, editable `title` that
  the web UI and the CLI show in place of the name.
- An MCP server's name is capped in length at registration. The capabilities view
  flags any tool whose client-visible name (`mcp__coffer__<server>__<tool>`) exceeds
  64 characters.
- The project rule that every management operation is reachable from both REST and
  the CLI is narrowed. Every mutation and every read of state must be reachable from
  both. A read of plain files that their owning spec declares directly usable is
  satisfied on the CLI by `coffer path`. The rule is updated in `.agents/openspec.md`
  and `openspec/config.yaml`.

## Capabilities

### New Capabilities

None. Each new command belongs to the capability that owns the state it touches.

### Modified Capabilities

- `resource-framework`:
  - The kind-agnostic CLI surface becomes per-kind verbs generated from the registry.
  - A name is fixed for kinds that declare it so, and every resource gains `title`.
  - `coffer log audit`, `coffer log prune` and the retention settings move under
    `config`.
  - The REST/CLI parity requirement is narrowed.
  - Upkeep runs are read from `daemon status`.
- `mcp-gateway`: MCP servers are managed through the uniform verbs, and the name is
  fixed and capped in length. `mcp test` absorbs `refresh`, and `mcp cap` replaces
  the three capability groups. The invocation log is read with `coffer log mcp`.
- `skill-manager`: the skill name is fixed, so a skill has no rename. Master files
  are edited on disk and located by `coffer path`. Unmanaged skills are handled by
  `scan`, `adopt` and `discard`.
- `knowledge`: the gateway exposes only `coffer__write`, which is unchanged.
  Collections use the uniform verbs, documents are read and deleted on disk, and the
  guide skill names two built-in tools.
- `memory`: `coffer__recall` is removed, and notes are located on disk. Delivery is
  switched with `memory delivery on|off` and reported on `agent show`.
- `agent-registry`:
  - Discovery and adoption move to `scan`, `adopt` and `discard`.
  - Coffer's MCP entry is installed with `connect` and `disconnect`.
  - Config files are read on disk, while edits keep their backup and audit.
  - Native memory is located with `coffer path`.
- `provider-switching`: the internal-engine and speech-to-text defaults are set
  through `config`, and `use-builtin` becomes `builtin`.
- `internal-engine`: every engine setting is read and changed through
  `coffer config`.
- `daemon`: the port and residency settings move to `config`. `daemon status`
  reports the passes in flight, and `coffer log daemon` reads the daemon log.
- `experimental-features`: features are switched with `coffer config`, and the
  gating requirements drop `coffer__recall`.
- `credentials`: the storage location moves to `config`, and `delete` becomes `rm`.
- `channels`:
  - Channels use the uniform verbs, so `register` becomes `add` and `status` becomes
    `show`.
  - The group-gating switches move to `edit`.
- `vault-sync`: `rollback` is folded into `restore`, `remote show` into `status`, and
  `machine remove` becomes `machine rm`.
- `web-ui`: MCP servers and skills show their `title`. The Activity page no longer
  cites `coffer__diagnose`, and the command-line record readers are `coffer log`.

## Impact

- **Code:**
  - `backend/coffer/surfaces/cli/` is rebuilt. Common verbs are generated from the
    `Kind` registry, and new `config`, `log`, `path`, `scan`, `adopt` and `discard`
    modules are added.
  - `application/diagnostics.py` and `application/memory/builtin_recall_tool.py` are
    removed, along with their registrations and gateway instructions.
  - `Kind` gains `name_fixed`, and `resources` gains a `title` column through an
    Alembic migration.
  - The `mcp_server` name rule gains a length cap.
- **REST:**
  - Resource responses and updates carry `title`.
  - A `name` change on a name-fixed kind is refused with `NAME_IMMUTABLE`.
  - The routes behind removed CLI commands stay.
  - `contracts/api.openapi.yaml` and the frontend codegen are regenerated.
- **Web UI:**
  - MCP server and skill pages edit and show `title`.
  - The MCP import preview names the fixed server name and flags long tool names.
- **Docs:** the following are regenerated or rewritten:
  - `docs-site/reference/cli.md` and `docs-site/reference/mcp-tools.md`
  - the guides that quote commands
  - the `coffer-guide` and `coffer-vault` skills
  - `.agents/openspec.md` and `openspec/config.yaml`
  - a new ADR that records the fixed-name decision
- **Tests:**
  - The parity test's reviewed command table is rewritten.
  - CLI tests follow the new names.
  - Acceptance markers follow renamed and removed scenarios.
- **Users:** there are no compatibility aliases. Scripts and skills that call removed
  commands must move to the new ones, and the design lists every mapping.
