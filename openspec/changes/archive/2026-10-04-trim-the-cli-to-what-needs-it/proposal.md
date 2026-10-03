## Why

Coffer's CLI grew in step with the web UI because of one rule: every
management operation must be reachable from both REST and the CLI. The result
is 187 commands. Almost none of them are run by a program: an audit of the
tree found two commands that Coffer's own wiring runs (the memory hook entry
point and the model proxy's key helper), a handful a person needs when the
daemon is down, and a handful Coffer's own hand-off prompts ask an agent to
run. Everything else duplicates a page of the web UI, and every new page
dragged a new command, its tests and its reference page along with it.

The CLI should carry only what needs it.

## What Changes

- **BREAKING** The REST/CLI parity rule is replaced by a minimal-CLI rule. A
  command exists only for one of four reasons, each recorded next to it:
  1. **program** — a program Coffer installs or writes runs it (the memory
     hook, an agent's key helper);
  2. **offline** — it must work when the daemon is down or cannot start
     (start, stop, restart and status of the daemon, the one-time migration,
     locating the logs, the daemon's own pre-bind settings);
  3. **hand-off** — a prompt Coffer gives an agent tells it to run the command,
     because what it reads or writes is not a file (running a command with
     secrets in its environment, naming and storing secrets, reading the audit,
     MCP and daemon logs, testing an MCP server after installing it);
  4. **no-ui** — the web UI cannot do it (listing refused hand edits to the
     vault).
  A test asserts the command tree equals the reasoned list.
- **BREAKING** Every other command is removed — about 165 of 187: the `mcp`,
  `tool`, `agent`, `channel`, `skill`, `cli`, `provider`, `proxy` (but
  `token`), `usage`, `sync`, `vault` (but `problems`), `drift`, `scan`,
  `adopt`, `discard`, `attention`, `open`, `secret` (but `list`, `set`),
  `path` (but `logs`) and `daemon service` / `daemon rotate-token` commands.
  Each removed spelling is listed in `scripts/check_removed_commands.py`
  with where the operation now lives.
- **BREAKING** `coffer config` accepts only the keys read before the daemon
  binds (the daemon's own settings file); every other setting is changed on
  the Settings page.
- Prompts, hints, error messages and web UI copy that told a person or agent to
  run a removed command now point at the web UI or at a kept command.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `resource-framework`: "Keep the command line to what needs it" replaces "Reach every management operation from both REST and the CLI"; `coffer path` keeps `logs` only; the lifecycle-verb and audit-reading requirements stop promising CLI verbs.
- Every capability whose requirements or scenarios name a removed command — `mcp-gateway`, `agent-registry` (and children), `skill-manager`, `channels`, `provider-switching`, `secret`, `vault-storage`, `vault-sync`, `daemon`, `chat`, `internal-engine`, `experimental-features`, `desktop-app`, `web-ui` — states the operation through the web UI or REST instead.

## Impact

- Code: about 40 modules under `backend/coffer/surfaces/cli/` shrink or go;
  their CLI tests go; the parity test becomes the reasoned-list test.
- Hand-off prompts and the `coffer-guide` skill are rewritten to the kept
  commands.
- Docs: the generated CLI reference shrinks to the kept commands; every guide
  that showed a removed command shows the web UI step.
- Policy: `.agents/openspec.md` "End-to-End Deliverable Rule" states the
  minimal-CLI rule.
