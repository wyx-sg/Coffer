## Context

The composition root (`surfaces/http/app.py`) builds the whole daemon in one
FastAPI lifespan: migrations, the vault's stores (`build_vault_stores`), the
vault scanner, every kind, the reconciler's boot pass, the workers. uvicorn
serves only after that startup half returns, and the desktop shell's
handshake (`desktop/src/ready.rs`) waits until `GET /api/v1/daemon/status`
answers 200. `build_vault_stores` raised on a missing git and on a git older
than 2.40, so the lifespan failed, uvicorn exited and nothing ever answered:
the shell timed out into its offline screen, the CLI said the daemon did not
start, the shim said nothing useful.

## Goals / Non-Goals

**Goals:** the daemon always comes up far enough to say why it cannot open the
vault, on every surface, with the existing install/update hand-off; a git
installed afterwards is picked up without the person restarting anything by
hand; a git that only the login shell can see is used.

**Non-Goals:** running without git (git stays a hard dependency); installing
git (the hand-off gives that chore to the person's agent, Principle IV).

## Decisions

### Decide before the lifespan, and run nothing of it in the setup state

`setup_lifespan.guarded(_lifespan)` wraps the composition root's lifespan. Its
first step is `git_requirement.check_git()`. With a usable git it puts the
login shell's git first on `PATH` when that is where it was found, then runs
the full lifespan unchanged. Without one it runs **none** of it — no
migrations, no vault, no kinds, no workers, no MCP sessions — publishes the
token, port and start time from `daemon.json` (so the page, the CLI and the
shell can authenticate), sets the phase to `setup` and yields.

The alternative — wiring "the parts that do not need the vault" — was
rejected: almost every kind reads the resource store, which is the vault, and
a half-initialised daemon is a set of routes that fail in ways nobody
designed. All or nothing keeps the setup state small enough to reason about.

### Refuse at the edge, not in every route

Every router is included by `create_app` before the lifespan runs, so the
routes exist in the setup state but their dependencies are not wired. A raw
ASGI middleware (`setup_state.SetupGuardMiddleware`, innermost, inside CORS)
answers every `/api/` and `/mcp` request with 503 `GIT_NEEDED` while the
phase is `setup`, except four: the status, Check again, restart and shutdown.
The refusal carries the setup message and the hand-off in `details`, so the
CLI's existing error rendering and the shim print them without knowing about
the setup state. The served web UI (every other path) is untouched. The guard
reads one module variable when not in setup, so it costs nothing on a normal
daemon and stays out of the SSE streams' way like the host guard.

### Recover by restarting, not by re-wiring in process

When Check again finds git, the daemon is restarted and the successor runs the
normal lifespan. Re-wiring in process was rejected:

- the lifespan is one async context manager whose order is the dependency
  order and whose teardown is its `finally`; running it later from a request
  would need a second, background lifecycle with its own teardown and its own
  "ready" moment, which every phase reader would have to learn;
- uvicorn already reports the app as started, so the "no request before
  ready" invariant the status probe and the shell rely on would no longer
  hold.

A restart reuses machinery that already handles the token and the port:

- **Desktop shell** — the page calls the shell's `restart_daemon` (as Settings
  › Daemon does): it asks the daemon to shut down (`/daemon/shutdown` stays
  open), waits for the port, spawns a new daemon with the login shell's
  `PATH` merged in, waits for its status and hands the page the new
  connection. No shell change is needed: the setup-state daemon answers the
  status probe with 200, so the launch handshake succeeds and loads the page.
- **Browser** — the page calls `POST /daemon/restart` (open in the setup
  state; its audit record is skipped, as no audit store is wired), waits for a
  different `started_at` and reloads from the successor, which carries the new
  token (`lib/daemonRestart.ts`).

Check again (`POST /daemon/setup/check`) itself only looks: it answers
`ready: true` or the setup state's current answer. Keeping the restart a
separate call keeps one restart path per host instead of a second one hidden
inside a check.

### Which git, and the login shell's `PATH`

`check_git` takes the git on the daemon's own `PATH` when it is 2.40 or later,
else the login shell's (`login_shell_path`, asked afresh each time, never the
cached `UserPath`). A daemon spawned by a GUI app or an editor's MCP shim gets
a truncated `PATH`; the CLIs page already looks commands up on the login
shell's `PATH` for the same reason. A git good enough only there is used:
`use_git_dir` puts its directory first on `os.environ["PATH"]`, which the
vault's git calls read (`git._executable` is keyed by `PATH`), and which a
self-restart's successor inherits. When neither is good enough, the reason is
`git_missing` (no git anywhere) or `git_too_old`, naming the newest version
found.

### One set of words

`domain/git_handoff.py` holds the message (`git_setup_message`) and the
details with the hand-off (`git_setup_details`, reusing
`git_install_handoff` / `git_update_handoff`). The status, every refusal, the
CLI and the shim carry those words; the web page renders its own localised
title and reason from `reason`, `found` and `needed`, and the daemon's prompt
as given. `MIN_GIT` moves from `vault/merge.py` to `vault/git_requirement.py`,
its only user, and `git_too_old_message` is removed.

### The hand-off in the setup state

The screen uses the shared `AgentHandoff` split button. Ask an agent opens a
Coffer conversation, which needs the daemon fully started; in the setup state
the managed-agent list is refused, so the component's own fallback applies and
the screen offers Copy prompt, for the person's agent outside Coffer. This is
the component's documented behaviour with no managed agent available, not a
special case.

### The CLI

`client_or_exit` already probes the status for version skew; it now also
reads `status: "setup"` and prints the message and the hand-off, exiting 10
(`GIT_NEEDED`), before the command sends its own request. `coffer daemon
status` reports the state instead of exiting, and `coffer daemon start` says
why right after the daemon comes up.

## Risks / Trade-offs

- A machine whose login shell is slow to start pays up to the probe's 3 s
  timeout at boot, only when the daemon's own `PATH` has no usable git.
- Putting a directory first on the daemon's `PATH` also puts the other
  programs in it first. It is the directory the person's own terminal
  already puts first, so agents and MCP servers the daemon starts see the
  same programs the person does.
