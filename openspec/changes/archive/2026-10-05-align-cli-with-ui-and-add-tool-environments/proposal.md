## Why

Coffer is driven by coding agents, and an agent works through a command line,
not a window. Until now the command line carried only what the web UI could not
do ("Keep the command line to what needs it"), so an agent asked to set up a
custom tool, bind a secret, reach an MCP server to one agent or check the sync
state had to hand the work back to the person, or drive the private REST
routes by hand. The owner's decision (2026-10-05) reverses that policy:
**every management operation a person can do in the web UI or the desktop app
has a `coffer` command**, built on the same REST routes and application
services, so validation, audit and lifecycle are the same whoever acts. The
old rules "a web UI operation owes no CLI counterpart" and "custom tools have
no command" are withdrawn.

Three gaps sit next to it. A custom-tool group could talk to one base URL
only, so a team with test, staging and live copies of one API duplicated every
tool per environment and had to keep the copies in step. A custom tool's
arguments were checked only for the schema's top-level `required`, so a wrong
type, an out-of-range number or an extra field reached the upstream API. And an
agent that hit a pending secret approval could only tell the person to open the
Secrets page, find the row and click Approve.

## What Changes

- **Command line parity (policy).** `.agents/openspec.md` and
  [resource-framework] "Keep the command line to what needs it" are replaced by
  "Offer every management operation on the command line": each web UI and
  desktop operation maps to a command recorded in one registry beside the REST
  route it calls and the acceptance test that covers it; a test fails when a
  route the web UI calls, or a desktop shell command, has no command and no
  recorded exemption. Exempt are only plain file contents a spec declares
  directly editable (knowledge documents, memory notes, skill files, agents'
  own config and native-memory files) and acts that only make sense to a person
  at a window (a native folder picker, open in editor / terminal / Finder, the
  window's language and theme). Registration, binding, reach, delivery and
  history restore stay commands even where the thing they manage is a file;
  internal YAML, `runs.db` and ciphertext are never edited as files.
- **One command line contract.** Every command takes `--json` (machine output
  on stdout, an error envelope `{error: {code, message, details}}` on stderr),
  reads bodies from `--data '<json>'`, `--data @file` or `--data -` (stdin) and
  `--set key=value`, prints help for every group, never prompts when stdin is
  not a terminal, and exits with a stable code (0 ok, 2 usage, 3 daemon
  unreachable, 4 not found, 5 conflict, 6 invalid input, 7 upstream test
  failed, 8 secret, 9 approval pending, 10 git needed, 11 presence not
  confirmed, 12 desktop app unavailable, 13 wait timed out). Long operations
  (a sync round, a skill import, a daemon restart, a presence check) offer
  `--wait` / `--timeout` and a status command.
- **Custom tools on the command line.** `coffer custom-tool` creates, reads,
  changes and deletes groups, tools and environments; switches groups and tools
  on and off; sets a group's reach; sets `changes_data`, request templates and
  argument schemas (from flags, a file or stdin); tests a draft or a saved tool
  against a chosen environment; imports an OpenAPI document; and previews and
  applies a re-import. No script, local HTTP adapter, proxy or MCP wrapper is
  involved: the commands call the daemon's own routes and the gateway calls the
  upstream API directly.
- **Environments in one custom-tool group.** A group keeps one set of tools
  and any number of user-named environments, each with its base URL, header
  rows (plain or a stored secret), non-sensitive variables (`{env:NAME}` in a
  template), an on/off switch and an optional timeout. Every caller — an MCP
  call, a CLI test, a UI test — names the environment per request through the
  reserved argument `coffer_environment` (required once a group has more than
  one enabled environment); it is stripped before rendering and never reaches
  the upstream body. A caller can choose only a registered, enabled
  environment and cannot override its URL or headers. Each environment is its
  own secret destination (target: its base URL; slot:
  `<environment key>:<header>`), so a missing key or a pending approval in one
  environment does not stop another, and moving an environment's URL asks
  again for that environment only. A group saved before environments existed
  reads as one environment `default` whose approvals keep working. The
  invocation log records the environment of each call, never a credential. A
  re-import keeps every environment.
- **Full argument validation.** A tool's argument schema is checked as JSON
  Schema when the tool is saved, and every call's arguments are validated
  against it — types, `enum`/`const`, numeric and length ranges, `pattern`,
  array bounds and uniqueness, `additionalProperties`, `allOf`/`anyOf`/`oneOf`/
  `not`, local `$ref` — by one validator shared by MCP calls, CLI tests and UI
  draft and saved tests. Invalid arguments, an unknown or disabled environment,
  and a missing or unapproved secret are refused before any upstream request,
  with `CUSTOM_TOOL_ARGUMENTS_INVALID` and one entry per field.
- **Approve from the command line with Touch ID.** `coffer approval list /
  show / approve / reject`. A command whose change waits for approval prints
  the approval ids and the next command. `coffer approval approve <id>…` asks
  the daemon for a **desktop request**; the desktop shell picks it up, reads
  the approvals from the daemon itself, runs the operating system's presence
  check naming the action, target, secret and environment, signs a grant
  pinned to each approval's target fingerprint, and the command returns the
  result. The CLI starts the desktop app when it is not running. Cancelled,
  failed, timed-out or unavailable checks leave the approval pending; no flag
  skips the check. `coffer secret reveal` and `coffer secret backup-key` start
  the same kind of request, and the value or the backup stays in the desktop
  app.

## Capabilities

### Modified Capabilities

- `resource-framework` — the command line policy and its test; the coverage
  registry; the shared CLI contract.
- `mcp-gateway` — environments, argument validation, custom-tool and MCP
  commands, environment in the invocation log.
- `secret` — approving, revealing and backing up started from the command line;
  pending approvals reported with their ids; a single approval's grant pinned to
  its target.
- `desktop-app` — the shell serves desktop requests.
- `agent-registry`, `channels`, `chat`, `daemon`, `knowledge`, `memory`,
  `provider-switching`, `skill-manager`, `vault-sync`, `web-ui` — each kind's
  "no command" clause becomes its command group.

## Impact

- Backend: `domain/mcp/http_api*.py`, a new `domain/mcp/json_schema.py`,
  `application/mcp/custom_tools*.py`, the gateway's custom-tool call path,
  `secret_target.py` and the boundary wiring, a desktop-request queue
  (`application/secret/desktop_requests.py` + routes), migration `0151`
  (`mcp_invocations.environment`), the CLI package (`surfaces/cli/`).
- Desktop: `desktop_requests.rs` (watcher), `secrets.rs` (pinned single grant,
  shared approve flow), `presence.rs` (prompt names environment).
- Frontend: Custom tools page (environments, per-environment secrets, test
  environment picker, actual target), invocation log environment column.
- Docs: CLI reference and guides (en + zh), ADR
  `command-line-parity-with-the-web-ui`, architecture pages.
