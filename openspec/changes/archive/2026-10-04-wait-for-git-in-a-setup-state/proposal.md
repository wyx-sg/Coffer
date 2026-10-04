## Why

git is a hard dependency of Coffer: the vault is a git repository, every write
is a commit, and history, undo, sync, rename detection and knowledge history
are built on it. On a machine with no git, or one older than 2.40, the daemon
refused to start — so the desktop app and the browser only ever said "daemon
offline", and the CLI said it could not connect. Nobody was told why.

## What Changes

- The daemon looks for a usable git (2.40 or later) before it opens the vault:
  on its own `PATH`, then on the login shell's. A git found only on the login
  shell's `PATH` is put first on the daemon's and used.
- Without one, the daemon still starts, in a **setup state**: it serves the web
  UI and publishes its token and port, wires nothing that touches the vault,
  reports `status: "setup"` with what it waits for (reason, versions, message,
  hand-off) on `GET /api/v1/daemon/status`, and refuses every other API route
  and `/mcp` with 503 `GIT_NEEDED` carrying the same message and hand-off.
- `POST /api/v1/daemon/setup/check` looks for git again. Once git is there the
  page restarts the daemon (desktop shell from outside, a browser through
  `/daemon/restart`) and the successor starts normally.
- The web UI shows one setup screen in the workspace while the daemon waits:
  what is wrong, why Coffer needs git, the hand-off (Ask an agent ▾ / Copy
  prompt) and Check again.
- `coffer` commands that need the daemon print the same message and hand-off
  and exit 10; `coffer daemon status` and `coffer daemon start` report it.
- The agent's MCP shim passes the refusal's message and hand-off on whole.
- vault-storage's "Refuse to start on a git older than 2.40" is removed; the
  daemon's setup state replaces it.

## Impact

- Backend: `infrastructure/vault/git_requirement.py` (new),
  `surfaces/http/setup_state.py` and `setup_lifespan.py` (new), `app.py`,
  `middleware.py`, `routing.py`, `daemon_routes.py`, `daemon_schemas.py`,
  `daemon_restart_routes.py`, `vault_composition.py`, `domain/git_handoff.py`,
  the CLI client and `coffer daemon`, the shim's error forwarding.
- Frontend: `components/shell/GitSetupState.tsx` (new), `Layout.tsx`,
  `lib/daemonRestart.ts`, the generated daemon client, i18n.
- Specs: daemon, vault-storage, web-ui. Contract: `daemon` OpenAPI.
- Docs: install and troubleshooting (en + zh), architecture daemon page, the
  error-code reference, CLI exit codes, README requirements, `install.sh`.
- Canvas: Shell 1.1.22, "Daemon · Waiting for git".
