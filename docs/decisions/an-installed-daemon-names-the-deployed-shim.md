# An Installed Daemon Names the Deployed Shim

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Agents Reach the Gateway Through a stdio Shim, Not a Native HTTP Entry](stdio-shim-bridge.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](one-level-triggered-reconciler-compares-parameters.md), [Distribution — Four PyInstaller Binaries, Shipped as a CLI Archive and a Desktop App](distribution-pyinstaller.md), spec agent-registry "Install Coffer's MCP server into an agent in one action", PR #408, PR #643

## Context

Connecting an agent writes a `coffer` entry into its MCP config whose
`command` is the absolute path of `coffer-mcp-shim`. The resolver used to try
a `PATH` lookup, the interpreter's scripts directory and the binary beside the
running executable, in that order, and name the first hit. On one machine an
installed Coffer can be started three ways, and they answered differently:

- **The desktop app's daemon** has no shell `PATH`, so it found the shim beside
  itself in `Coffer.app/Contents/MacOS/` and wrote that path (measured on the
  owner's Mac, 2026-10-07: both `~/.claude.json` and `~/.codex/config.toml`
  named the app bundle).
- **A daemon started from a terminal** through `~/.coffer/bin/coffer` found the
  public `~/.coffer/bin/coffer-mcp-shim`.
- **A daemon started by launchd** finds whatever `coffer-mcp-shim` comes first
  on its `PATH`, a leftover development venv or another install included.

The reconciler computes an entry's desired state from the command the running
daemon resolves and compares it parameter by parameter
([One Level-Triggered Reconciler](one-level-triggered-reconciler-compares-parameters.md)),
so two daemons that resolve differently rewrite each other's entries, and every
rewrite leaves a config backup. An entry naming the app bundle also breaks when
the app is moved out of `/Applications` or removed while the CLI stays. The shim
ADR already stated that an installed build writes `~/.coffer/bin/coffer-mcp-shim`.

The one-folder shim (PR #643) moved the app's shim to `Contents/Resources/`
and gave the resolver a last step that answers the deployed shim, so the app's
daemon now writes the public path. A daemon whose `PATH` holds some other shim
still writes something else.

Comparable products keep one stable name in front of versioned or bundled
binaries: Homebrew links `/opt/homebrew/bin/<tool>` into a versioned
`Cellar/<tool>/<version>/`, Docker Desktop links `~/.docker/bin` into the app
bundle, and VS Code's "Install 'code' command" links into the bundle. Clients
are always handed the stable name, never what it points to. Coffer's
`~/.coffer/bin/<name>` symlinks into `~/.coffer/bin/<version>/` are the same
pattern; the question is only whether the resolver honours it.

## Options Considered

### Option A — An installed build names the deployed shim first (chosen)

Right after the `COFFER_MCP_SHIM_PATH` override, a frozen (installed) build
returns `~/.coffer/bin/coffer-mcp-shim` whenever it exists. A source install
keeps the old search order.

- Pros: every installed daemon writes the same entry whatever started it, so the
  reconciler has nothing to flip; the entry survives moving or removing the app;
  it is what the shim ADR already promised. Every frozen daemon deploys its own
  binaries into `~/.coffer/bin` at start-up, so the public shim is the one that
  matches the running daemon.
- Cons: an installed daemon ignores a different shim a person put first on
  `PATH` on purpose; the override is the way to choose one.

### Option B — Keep the search order, rely on PR #643's last step

- Pros: no change.
- Cons: only the app's case is fixed. A launchd or terminal daemon with any other
  shim earlier on its `PATH` still answers it, and the flip-flop stays possible.

### Option C — Prefer the public name only when it is the same version as the hit

Keep the search; when the hit and the deployed shim report the same version,
answer the public name (the TODO's first suggestion).

- Pros: closer to the old behaviour.
- Cons: needs a version probe of each candidate (run it, or read a sentinel next
  to it); a stale shim of a different version on `PATH` still wins, which is
  exactly the case that breaks. More code for a narrower fix.

### Option D — Document that the app writes the bundle path

Change the ADR instead of the code.

- Pros: no code.
- Cons: leaves the flip-flop and the broken entry after moving or removing the
  app; contradicts how every other client of Coffer is told to reach the shim.

## Decision

The `coffer` entry's command is resolved as: the `COFFER_MCP_SHIM_PATH`
override; then, in an installed build, `~/.coffer/bin/coffer-mcp-shim` when it
exists; then, as before, `PATH`, the interpreter's scripts directory, the binary
beside the executable and the deployed shim, with a deployed hit always named by
its public path. A source install never takes the second step, so a development
daemon keeps the shim from its own checkout.

## Consequences

- The app's, a terminal's and launchd's daemons write the same entry, so the
  reconciler does not rewrite entries back and forth between them.
- An entry survives moving or deleting `Coffer.app` as long as `~/.coffer/bin`
  is there.
- `default_shim_resolver` in `backend/coffer/application/agent/mcp_service.py`
  holds the order; `tests/unit/application/test_shim_resolver.py` checks the
  three launch paths give the same answer.
