# The User's PATH Is Read From an Interactive Login Shell

**Status**: Accepted
**Date**: 2026-11-23
**Deciders**: Yuxing Wu
**Related**: [Sessions of Cursor, OpenCode and DeepSeek Harness Are Read From Their Stores](sessions-of-cursor-opencode-and-deepseek-harness-are-read-from-their-stores.md), [The Daemon Is a Resident Login Service](daemon-is-a-resident-login-service.md), spec agent-registry "Detect an agent by its program and its config directory"

## Context

A daemon started from the Dock, by launchd or by an editor's MCP shim gets a
truncated `PATH`, so Coffer asks the user's shell for the real one. Until now
it ran `$SHELL -l -c` (the daemon) and `$SHELL -lc` (the desktop app). A login
shell that is not interactive reads `~/.zprofile` but not `~/.zshrc`, and nvm,
fnm, pyenv and most install scripts add their `PATH` lines to `~/.zshrc`. On
the owner's Mac (2026-11-23) OpenCode and DeepSeek Harness, installed with
`npm -g` under nvm, read "Config left behind · not on PATH" although both run
in any terminal.

How comparable tools do it: VS Code resolves the environment of a GUI launch
by running the user's shell as an interactive login shell (`-i -l -c`) with
markers around the output and a timeout; Cursor and Windsurf inherit that
code, and the `shell-env` / `fix-path` packages Electron apps use run the
same `-ilc` command.

## Options

### A. Keep the login-only shell (`-lc`)

- ✅ Fast, and a profile written for interactive use cannot interfere.
- ❌ Misses every tool whose `PATH` line lives in `~/.zshrc`, which is where
  nvm's installer puts it; the agents guide already promised that a Node
  version manager's install is found.

### B. Ask an interactive login shell, then fall back to a login-only one (chosen)

`$SHELL -ilc` with stdin closed and markers around `$PATH`; if it fails,
times out or prints no markers, `$SHELL -lc` as before.

- ✅ The `PATH` a terminal has, as the editors that face the same problem do.
- ✅ A profile that greets, prints a notice or asks a question cannot spoil
  the value (markers, no stdin), and one that fails interactively still gets
  the old answer.
- ❌ An interactive profile is slower (nvm's loader adds a fraction of a
  second); the probe runs once per process, under the same 3 s bound, so a
  profile that hangs costs up to 3 s more before the fallback.

### C. Add well-known version-manager directories by hand

Append `~/.nvm/versions/node/*/bin`, `~/.volta/bin` and the like.

- ✅ No shell is run.
- ❌ Guesses which Node version is current (nvm keeps several), and every
  new manager needs a new entry. It is a list Coffer would have to maintain
  for a fact the shell already knows.

## Decision

Option B, in both places that ask: the daemon's platform layer
(`login_shell_path`) and the desktop app's `env_path.rs`, which keep the same
order and markers.

## Consequences

- Agents, CLIs and launchers installed under nvm and similar managers are
  found, and the sessions Coffer starts get the same `PATH`.
- Detection asks the shell itself once per daemon process, so a restarted
  daemon finds them at once. The `PATH` the login service is installed with
  comes from the same probe, so the service carries the new value from its
  next install.
