## Why

1.0 keeps no backward compatibility. Coffer carried code whose only job was to recognise, move or tolerate what earlier builds wrote: old command-line forms in agent configs, retired config keys, old secret stores, old web addresses. Each piece kept a second, older contract alive beside the current one, with requirements, scenarios and tests of its own. What earlier builds left on the owner's machine is cleaned once by a reviewed upgrade step, not by permanent code.

## What Changes

- **Agent configs.**
  - Only the current `coffer proxy token` helper is recognised as Coffer's.
  - Codex projection no longer strips an earlier `COFFER_PROVIDER_KEY` shell exclusion; Codex authenticates through its `auth` command, so no key reaches its environment.
  - Projection no longer deletes the retired `ANTHROPIC_MODEL` / `ANTHROPIC_SMALL_FAST_MODEL` keys.
  - The MCP-entry reconciler reads and repairs only each agent's own file, and no longer moves entries out of the default file.
  - Memory-hook repair no longer special-cases older builds' hooks.
- **Command line.**
  - `coffer memory context` is removed (it existed only for hooks older builds installed), with its REST route `POST /api/v1/memory/context`.
  - The CLI no longer treats a 404 from the approvals list as an older daemon.
- **Config and stored data.**
  - `daemon-config.json` no longer strips `idle_shutdown_hours`.
  - Migration 0199 strips `idle_timeout_seconds` from stored MCP server configs, which now reject unknown keys.
  - Skill names no longer accept underscores.
  - The MCP server name cap applies on every register and rename, not only when a uid is minted.
  - The daemon-log parser no longer reads the old alembic line shape.
  - Binary deploy no longer removes the in-place layout's sentinel.
  - The desktop app requires `login_service_supported` in the residency answer.
- **Startup moves.** The daemon no longer:
  - moves pre-0.2 keychain secrets into the store;
  - moves a file or login-keychain master key into a signed build's access group;
  - auto-approves every binding that existed before the secret boundary;
  - reports removed agent types' config dirs.
- **Web addresses.** Every redirect from an old address is removed; an old address shows the not-found page or the default tab.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: projection keeps only the current forms; the connection surface names only `/model-providers`.
- `agent-registry`: the stale-hook scenario no longer describes an older build.
- `agent-registry/claude-code`: the MCP entry reconciler reads only the agent's own file.
- `memory`: `coffer memory context` and its route are gone, and hook repair has no older-build case.
- `daemon`: `idle_shutdown_hours` is an ordinary unknown key, and the log tail reads only the current shape.
- `mcp-gateway`: the 24-character name cap covers every name, and the name-only handshake scenario no longer calls the key older.
- `skill-manager`: names are hyphen-only, and the old Skills address is gone.
- `secret`: the startup moves are gone.
- `web-ui`: the redirect requirements are removed.

## Impact

- Code: backend provider, agent, memory, secret, daemon, skill and log modules; the CLI; `frontend/src` routing and pages; the desktop tray watcher.
- Migration: `0199` (a placeholder number, renumbered at merge).
- Tests: the old-form tests are removed, and acceptance tests for kept scenarios are pointed at current surfaces.
- Docs: docs-site guides, architecture and reference pages, and the data-model files.
- `scripts/check_removed_commands.py` lists `coffer memory context`.
- The one-time upgrade steps live outside the repository, for the owner to review.
