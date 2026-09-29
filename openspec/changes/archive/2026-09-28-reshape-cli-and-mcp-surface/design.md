# Design: Reshape the CLI and MCP surface

## Context

See proposal.md "Why" for the motivation.

The CLI is a Typer tree assembled in `backend/coffer/surfaces/cli/main.py`. It has one
module per group, and each module talks to the daemon over the management API through
`_client.py`. The kind-agnostic REST surface (`/api/v1/resources*`) and the `Kind`
descriptor (`domain/resource.py`) already exist. Every kind's lifecycle operations
(update, enable, disable, delete, reach) are therefore served by the same routes, and
per-kind CLI groups re-implement calls to those same routes by hand.
`resource-framework` "Reach every management operation from both REST and the CLI"
asserts a hand-reviewed table of the live command tree in both directions.

The following facts shape the design:

- **Plain files on disk:**
  - Knowledge documents, under `~/.coffer/knowledge/<collection>/`.
  - Memory notes, under `~/.coffer/memory/<partition>/`, with the files `MEMORY.md`,
    `notes/*.md` and `RETIRED.md`.
  - Skill master folders.
  - Agents' own config files.
  - The daemon log, which is one JSON object per line.
  - The knowledge spec already declares that editing those files directly is a
    complete way to change knowledge.
- **Name exposure:** an MCP server's name is the prefix of every tool name the gateway
  advertises. `gateway_handlers.py` resolves an incoming call by that name. Clients
  then add their own prefix, and Claude Code shows `mcp__coffer__<server>__<tool>`. A
  skill's name is the directory an agent loads it from.
- **Recorded usage** in `mcp_invocations` on the author's machine, since 2026-08-31:
  - `search_tools`: 34 calls.
  - `write`: 9 calls.
  - `recall`: 5 calls.
  - `diagnose`: 2 calls, both on one day.

## Goals / Non-Goals

**Goals:**

- One CLI grammar. A reader who knows one kind's group knows every kind's lifecycle
  verbs.
- The CLI and the MCP tools cover only what a file tool cannot: mutations that need
  validation, audit or curation, and reads of state that is not a file.
- An MCP server's or a skill's name, once registered, stays valid everywhere it has
  been quoted.

**Non-Goals:**

- Changing any REST route's path or behaviour, except that resources gain `title` and
  a fixed name refuses a change.
- Per-tool renaming or aliasing in the gateway, as MetaMCP's `override_name` does.

## Decisions

### D1. Generate the lifecycle verbs from the kind registry

Every kind group gets `list`, `show`, `add`, `edit`, `rm`, `enable`, `disable` and
`scope`. They are built by one factory that reads the `Kind` descriptor and calls the
kind-agnostic routes. A verb the kind cannot support is omitted instead of being
refused at run time:

- `add` requires `generic_create_allowed`, or a kind-specific `add` that the group
  registers itself. Skill's `add` takes a folder path, and agent's `add` takes a type.
- `scope` requires `supports_scope`.
- `memory` has no `add`, because partitions are created only by aggregation.

`show` resolves a name or a uid. `edit` takes `--title` and `--description` for every
kind, plus the kind's own flags. Every list and show verb supports `--json`.

- *Alternative: keep `coffer resource` as the only lifecycle entry.* Rejected. A user
  managing MCP servers would then have to switch groups to disable one, and each kind
  would still need its own `list` to show kind columns.
- *Alternative: hand-write each kind's verbs.* Rejected. Hand-writing them is how
  `mcp remove` came to exist beside `resource delete`, and how three spellings of
  delete arose.

### D2. One key-value `config` command for settings

`coffer config list|get|set|unset <key>` replaces about 30 per-setting subcommands.
Keys come from one registry. Each entry names:

- its type,
- its default,
- a one-line help,
- the REST route that stores it.

`config list` prints every key with its current value, its default and its help, and
`--json` is available. `unset` returns a key to its default, which replaces the
inconsistent `clear` and `default` verbs.

| Key | Replaces |
|---|---|
| `daemon.port` | `daemon port show/set/clear` |
| `feature.<key>` (on/off; `unset` = channel default) | `daemon features list/enable/disable` |
| `engine.provider` | `provider internal-default` |
| `engine.model` | `engine model show/set/clear` |
| `engine.timeout` | `engine timeout show/set/default` |
| `engine.curate_owner` (`this` or a machine id) | `engine curate-owner show/set/clear` |
| `engine.upkeep.<pass>.enabled`, `engine.upkeep.<pass>.interval` | `engine upkeep list/set` |
| `transcribe.provider` | `provider transcribe-default` |
| `transcribe.model` | `engine transcribe-model show/set/clear` |
| `retention.<table>` (days or `forever`) | `retention list/set` |
| `credentials.storage` | `credentials storage` |

`engine.provider` and `engine.model` are stored where they are today: the provider
flag and the engine row. The key namespace is what joins them, so the storage does
not change.

A key with no default refuses `unset`, and the refusal names the way to change the
key instead. This applies to `engine.provider` and `transcribe.provider`, whose flag
moves only by naming another connection; no route clears them. `daemon.port` is the
one key stored in the pre-bind settings file instead of behind a route, so it works
with no daemon running.

- *Alternative: keep typed subcommands per setting.* Rejected. They produced the
  `provider internal-default` + `engine model set` split, where one concept had two
  entry points, and one naming inconsistency (`timeout default`).

### D3. `coffer log` for records, `coffer path` for files

- `coffer log audit|mcp|daemon [--since] [--errors] [--kind] [--name] [--server]
  [--limit] [--json]` reads the three records the Activity page shows, from the same
  routes. `coffer log prune` runs the on-demand prune.
- `coffer path [knowledge [<collection>] | memory [<partition>] | skill <name> |
  agent <name> config|memory|transcripts | logs | vault]` prints absolute paths.
  With `--json`, it prints them as a JSON object. It composes the paths from reads
  the daemon already serves, so no route is added.

Together these replace `coffer__diagnose`. An agent in a shell runs
`coffer log daemon --errors --since 1h`, or greps the daemon log that
`coffer path logs` names.

### D4. `scan`, `adopt` and `discard` for whatever Coffer does not manage yet

`coffer scan [--agent <name>] [--json]` lists the following in one table with a
`kind` column:

- detected agents that are not registered,
- skill-shaped folders in agents' skill locations that Coffer does not manage,
- MCP entries in agents' own config files.

`coffer adopt <kind> <ref>` and `coffer discard <kind> <ref>` act on one row. `ref`
is the value the scan printed for that row. Detected agents cannot be discarded,
because nothing of Coffer's put them there.

### D5. Remove `coffer__recall` and `coffer__diagnose`

Both answer "where is X", and an agent already answers that with grep. The
replacements are:

- **For `recall`:** memory notes are Markdown under the directory the session-start
  delivery already names. The handshake instructions and `coffer-guide` tell the agent
  to grep that directory.
- **For `diagnose`:** use `coffer log` and `coffer path logs` (D3).

`coffer__search_tools` stays, because only the gateway can see tools that tiering did
not list. `coffer__write` stays, because material has to be validated, attributed to
the calling agent and queued for curation, and a file an agent drops on disk would
skip all three. The experimental-feature gating of `coffer__write` is unchanged.

### D6. A name is fixed where it is visible outside Coffer

`Kind` gains `name_fixed: bool`. For a kind with `name_fixed`, a `PATCH` whose `name`
differs from the current one is refused with `409 NAME_IMMUTABLE`. The message says
to delete and register the resource again under the new name. `mcp_server` and
`skill` set the flag:

- **MCP server:** the name is the tool-name prefix, and agents' permission rules and
  skills quote it.
- **Skill:** the name is the directory and the identifier an agent invokes.

`provider`, `agent`, `channel`, `knowledge` and `memory` keep renamable names, because
their names appear only on Coffer's own surfaces. This follows the MCP spec's own
split between an immutable `name` and a display `title`. Every client surveyed treats
a server name as fixed: Claude Code, Codex, Cursor, VS Code and MCPJungle.
ContextForge allows a rename, and the rename rewrites every tool name.

Every resource gains an optional `title`:

- It is at most 80 characters of free text.
- It is stored in a new nullable `resources.title` column.
- It is carried in the resource document that vault-sync serializes.
- It can be edited on every kind through `edit --title` and the PATCH route.

Surfaces show `title` when it is set and the name when it is not.

The `on_rename` hook of skill is removed, since a skill cannot be renamed any more.
The hook stays for knowledge and memory. The recorded decision becomes an ADR:
`docs/decisions/names-visible-to-agents-are-fixed.md`. It amends
`resource-identity-is-an-immutable-uid.md` without replacing it, because the uid is
still the identity.

- *Alternative: allow the rename and keep the old prefix as an alias for a
  deprecation window.* This is github-mcp-server's pattern for tools. Rejected for
  now. It adds a second resolution path in the gateway, and it still breaks when the
  window closes. It is worth revisiting if users ask for renames after the
  display-name field has shipped.
- *Alternative: warn on rename instead of refusing it.* Rejected. The breakage lands
  in files Coffer cannot see, so a warning printed now protects nobody later.

### D7. Cap the MCP server name and flag long tool names

At registration, the `mcp_server` name rule refuses names longer than 24 characters.
The existing pattern and the `__` ban still apply, and names that already exist are
kept.

After discovery, each capability row gets a `client_name_length` field. It is the
length of `mcp__coffer__<server>__<tool>`. The Tools tab and `mcp cap list` flag rows
above 64 characters, which is the provider API limit, and note that Cursor drops
tools above 60 characters.

The 24-character cap follows from the limit. `mcp__coffer__` (13) plus 24 plus `__`
(2) leaves 25 characters of the 64 for the upstream tool name, which covers the long
tail seen in practice.

The JSON import preview in the web UI shows the server name as fixed and warns when
the name is longer than 24 characters, before submit.

### D8. Narrow the REST/CLI parity rule

The amended rule has two parts:

- Every mutation, and every read of state that is not a plain file, is reachable from
  both REST and the CLI.
- For a plain file that its owning spec declares directly readable or editable, the
  CLI satisfies parity by naming the file with `coffer path`.

The REST routes that serve such files to the web UI remain, because a browser page
cannot read the disk. The parity scenario's reviewed table is rewritten to the new
tree, and it lists every file-backed route that is answered by `coffer path`. That
list keeps "a REST read with no CLI counterpart" a reviewed decision, not a gap that
passes unnoticed.

## Command mapping

The table below is the complete mapping from the old CLI to the new one. A command
that keeps its name is absent from it.

| Old | New |
|---|---|
| `resource list/show/rename/enable/disable/delete` | `<kind> list/show/edit --name/enable/disable/rm` |
| `scope show/set/clear` | `<kind> scope <name> [--agents a,b \| --all \| --none]` |
| `audit list` | `log audit` |
| `retention list/set` | `config list retention.` / `config set retention.<table>` |
| `retention prune-now` | `log prune` |
| `daemon port show/set/clear` | `config get/set/unset daemon.port` |
| `daemon features list/enable/disable` | `config list feature.` / `config set feature.<key> on\|off` |
| `mcp remove` | `mcp rm` |
| `mcp refresh`, `mcp test` | `mcp test` (re-queries capabilities, then reports health) |
| `mcp invocations [<server>]` | `log mcp [--server <name>]` |
| `mcp tool/resource/prompt list` | `mcp cap list <server> [--type tool\|prompt\|resource]` |
| `mcp tool/resource/prompt enable/disable` | `mcp cap enable/disable <server> <tool:x\|prompt:x\|resource:uri>...` |
| `credentials delete` | `credentials rm` |
| `credentials storage` | `config get/set credentials.storage` |
| `agent detect` | `scan` |
| `agent native-memory`, `agent native-memory-files` | `path agent <name> memory` |
| `agent transcripts`, `agent transcript <id>` | `agent transcript <name> [<id>]` |
| `agent config ls/cat/files` | `path agent <name> config` |
| `agent config edit/write` | `agent config edit <name> <key>[/<child>] [--from-file]` |
| `agent config rm` | `agent config rm <name> <key>/<child>` |
| `agent mcp install/uninstall` | `agent connect/disconnect <name>` |
| `agent mcp status` | `agent show` (field `coffer_mcp`) |
| `agent mcp entries` | `scan --agent <name>` |
| `agent mcp adopt` | `adopt mcp <agent>:<entry> [--name]` |
| `agent mcp remove-entry` | `discard mcp <agent>:<entry>` |
| `agent plugin uninstall` | `agent plugin rm` |
| `channel register` | `channel add` |
| `channel status` | `channel show` |
| `channel set` | `channel edit --[no-]require-mention --[no-]ignore-other-mentions` |
| `skill import` | `skill add <folder>` |
| `skill files/cat/write` | `path skill <name>`; edit on disk |
| `skill unmanaged` | `scan` |
| `skill adopt` | `adopt skill <path>` |
| `skill rm-unmanaged` | `discard skill <path>` |
| `knowledge collections` | `knowledge list` |
| `knowledge create` | `knowledge add` |
| `knowledge ls/read` | `path knowledge [<collection>]` |
| `knowledge delete` | delete the file on disk |
| `memory partitions` | `memory list` |
| `memory notes/note/retired/ls/read` | `path memory [<partition>]` |
| `memory delivery` | `agent show` (field `memory_delivery`) |
| `memory delivery-install/delivery-remove` | `memory delivery on/off <agent>` |
| `provider use-builtin` | `provider builtin` |
| `provider internal-default` | `config set engine.provider <name>` |
| `provider transcribe-default` | `config set transcribe.provider <name>` |
| `engine model/timeout/curate-owner/transcribe-model/upkeep list,set` | `config … engine.* / transcribe.*` (D2) |
| `engine upkeep runs` | `daemon status` (section "passes in flight") |
| `sync rollback` | `sync restore` (no `--at`: undo the last applied round) |
| `sync remote show` | `sync status` |
| `sync machine remove` | `sync machine rm` |

The resulting top level is:

`daemon`, `open`, `config`, `log`, `path`, `scan`, `adopt`, `discard`, `mcp`,
`credentials`, `agent`, `channel`, `skill`, `knowledge`, `memory`, `provider`, `sync`.

`coffer memory context` stays unchanged, because it is the command the installed
session-start hook runs.

## Risks / Trade-offs

- **Scripts and skills break with no aliases.** Coffer has no external CLI users, so
  the callers are:
  - the repo's own tests, e2e and docs,
  - the shipped `coffer-guide` and `coffer-vault` skills,
  - the installed session-start hook.

  Mitigation: the hook runs `memory context`, which is unchanged. The skills and docs
  are regenerated in the same change, and a grep gate over `docs-site/`,
  `backend/coffer/**/skills/` and `e2e/` fails on any removed command.
- **`config` loses per-setting `--help`.** Mitigation: `config list` prints each key's
  type, default and help from the same registry, and `config set` validates against
  the key's type before calling the route.
- **Agents lose `recall`'s cross-partition locator.** Mitigation: the memory root is
  one directory, so one grep covers every partition. The delivery text names that
  root.
- **A user who wants a different MCP server or skill name must delete it and add it
  again.** This loses the server's capability toggles and reach, or the skill's
  bindings. Mitigation: `title` covers the cosmetic case. The refusal message names
  what a re-registration resets.
- **An existing MCP server whose name is longer than 24 characters** stays, and keeps
  working. Only a new registration is capped.

## Migration Plan

1. Add an Alembic migration that adds the nullable `resources.title` column. There is
   no data change. Vault-sync documents gain an optional `title` key. A peer on an
   older version ignores the key, and a document without it leaves `title` null.
2. Build the backend changes: `name_fixed`, `title`, the name-length cap and
   `client_name_length`. Remove the two built-in tools.
3. Build the new CLI tree beside the old one. Switch `main.py` over, then delete the
   old modules.
4. Regenerate the OpenAPI contract, the frontend codegen and the CLI reference. Update
   the skills and guides.

Rollback is a revert of the change. The `title` column is nullable and ignored by
older code.
