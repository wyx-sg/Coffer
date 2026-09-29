# Platform Differences Live Behind One Platform Port; Only macOS Ships

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Code Layout Is Layer-First, With One Subdirectory per Kind](code-layout-layer-first.md), [Kinds Are Wired Explicitly by One Composition Root](composition-root-explicit-wiring.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [The Daemon Is Resident: It Never Idles Out, and a Login Service Restarts Only a Crash](daemon-is-a-resident-login-service.md), [The Loopback Daemon Performs OS File Actions for the UI](daemon-proxies-os-file-actions.md), [Distribution — Three PyInstaller Binaries](distribution-pyinstaller.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md), spec skill-manager "Fall back to copying where links are unavailable", spec daemon "Run as a login service", spec agent-registry "Write config files atomically with a backup and an audit entry"

## Context

Coffer ships for macOS on Apple Silicon only: `.github/workflows/release.yml`
builds `aarch64-apple-darwin` and says Linux and Windows bundles "were never
validated". The test suite runs on `ubuntu-latest` only. Nobody runs Coffer
on Windows.

The code is nevertheless already written for three platforms, in whichever
layer happened to need an answer. `sys.platform` and `platform.system()` are
read at these sites in `backend/coffer/`:

| Layer | Site | What it decides |
| --- | --- | --- |
| application | `skill/lifecycle_ops.py:43` | whether a Windows directory link is a junction |
| application | `agent/service.py:64, 67, 79, 100` | path separator, privileged-prefix tables, the macOS `/private` firmlink |
| application | `fs/open_service.py:69, 82, 91, 93` | `open` / `open -a` / `open -R` vs `start` / `explorer` vs `xdg-open` |
| application | `fs/editor_service.py:80` | how an external editor is launched |
| application | `fs/pick_service.py:97, 101` | which native folder picker runs |
| application | `sync/machines.py:90` | the OS label on a machine descriptor |
| infrastructure | `skill/sync_engine.py:52, 91, 137, 158` | symlink vs junction vs copy |
| infrastructure | `daemon/login_service.py:71` | launchd is the only login service (`is_supported()`) |
| infrastructure | `daemon/spawn.py:62, 69, 103` | the daemon executable's name, the `.app` bundle path, detaching a child |
| infrastructure | `sync/machine_id.py:58` | where the host's machine id is read from |

Other platform assumptions carry no check at all:

- **Atomic replace.** `os.replace` is called directly in
  `surfaces/http/daemon_routes.py`, `application/binary_deploy.py`,
  `application/skill/file_ops.py`, `infrastructure/skill/master_store.py`,
  `infrastructure/agent/config_file_store.py` and
  `infrastructure/daemon/atomic_write.py`. On POSIX it replaces an open file
  freely; on Windows it raises `PermissionError` when another process holds
  the target open without delete sharing — which is exactly the state of an
  agent config file its own CLI has open. The fix is a bounded retry, and it
  has to be the same in every writer.
- **Process signals.** `surfaces/cli/daemon_cmd.py` and
  `surfaces/http/daemon_routes.py` stop the daemon with `os.kill(…, SIGTERM)`;
  `surfaces/shim/main.py` installs `SIGTERM` / `SIGINT` handlers. Windows has
  no `SIGTERM` delivery between processes.
- **Symlinks in `application/`.** `application/binary_deploy.py` creates and
  reads symlinks directly with `os.symlink` / `os.readlink`.
- **Shell syntax in a written hook.** `infrastructure/memory/delivery/codex.py`
  installs a guard that uses `${TMPDIR:-/tmp}`, `$PPID` and `[ -e … ]` — a
  POSIX shell command written into another program's config.

Two costs follow. The Windows branches in `application/` have never executed
in CI, so they are unverified code that reads as supported. And every one of
them is OS work done above `infrastructure/`, although the layering in
[Principles](../../docs-site/architecture/principles.md) gives adapter work
to `infrastructure`, which "adapts to ports defined in `application`";
`import-linter` cannot catch it, because `import sys` is
legitimate everywhere and the violation is an attribute access, not an import.

## Options Considered

### Option A — One platform port; an AST gate keeps checks out of the upper layers (chosen)

`infrastructure/platform/` implements a set of narrow ports, declared in
`application/`, and the composition root binds the implementation for the
running OS:

| Port | Covers |
| --- | --- |
| paths | Coffer's home, an agent's default config directory, privileged roots and carve-outs, path comparison rules (the `/private` firmlink) |
| login service | install / remove / status of the per-user service (launchd today) |
| file actions | open, open with an app, reveal, pick a folder, launch an editor |
| links | directory link with the platform's best mechanism — symlink, junction, or copy — and classifying an existing one |
| processes | spawn detached, stop gracefully, install shutdown handlers, the executable's file name |
| file watching | reserved; no implementation until a consumer exists |
| atomic replace | temp-file-plus-replace, with a bounded retry where the platform refuses to replace an open file |
| machine identity | the host id and OS label |

A module above `infrastructure/` asks the port and never the OS. An AST gate
in `make lint` rejects `sys.platform`, `platform.system()`, `os.name` and
direct `os.replace` / `os.symlink` / `os.kill` in `domain/`, `application/`
and `surfaces/`; inside `infrastructure/`, only `infrastructure/platform/`
may read the platform. Only the macOS implementation is complete and
shipped; where another OS has a known answer today (the junction and copy
paths, `xdg-open`, `explorer`), it moves into the port's implementation for
that OS rather than being deleted.

- **Pros.** Every OS difference is in one directory, visible as a list; the
  upper layers become testable with a fake platform, so the Windows and
  Linux branches can be exercised by unit tests on any CI runner; the retry
  rule for atomic replace is written once. The gate makes the rule
  mechanical rather than a review habit.
- **Cons.** Eight small ports and their fakes; every current site moves. A
  port for file watching exists before any consumer, which is a mild
  violation of "extract on the second use", accepted because the reconciler
  names it as a later hint source.
- **Why it wins.** It keeps the one-platform release honest (only macOS is
  claimed) while making sure the foundation does not have to be dug up to
  add a second.

### Option B — Declare macOS-only and delete the other branches

Remove the Windows and Linux paths, assume POSIX and macOS everywhere, and
revisit when there is demand.

- **Pros.** Least code; nothing unverified pretends to be supported.
- **Cons.** The assumptions would spread silently — `os.replace` on an open
  file, `SIGTERM`, `/private`, shell syntax — into places no grep for
  `sys.platform` would find, and a second platform later would mean auditing
  every writer. CI already runs on Linux, so deleting the Linux branches would
  make the test environment unlike any supported one. The junction and copy
  delivery modes are also specified behaviour (spec skill-manager "Fall back
  to copying where links are unavailable").
- **Why it loses.** It saves little now and makes the eventual port the
  expensive kind of change.

### Option C — Keep branching at each site, and add Windows and Linux CI

Leave the checks where they are and make them real by testing on
`windows-latest` and `macos-latest` too.

- **Pros.** Proves the existing branches without restructuring.
- **Cons.** Tripled CI time for platforms nobody ships; the branches stay
  spread across `application/`, so each new writer must remember every
  platform rule on its own. It tests the scatter rather than removing it.
- **Why it loses.** It spends CI on the symptom. CI on other runners can be
  added later against the port's implementations, where it is cheap to
  target.

### Option D — A cross-platform library for everything (`platformdirs`, `psutil`, `watchdog`)

Adopt libraries that abstract the OS and call them directly from any layer.

- **Pros.** Maintained, tested abstractions for paths, processes and
  watching.
- **Cons.** They cover only part of the list — none knows what an agent's
  config directory is, how launchd is configured for Coffer, or that a
  config file may be open in its CLI — and calling them from `application/`
  is the same layering problem with a nicer API.
- **Why it loses.** Libraries are welcome *inside* the port's implementations;
  they do not replace the port.

## Decision

The foundation does not assume macOS. Every platform-dependent operation —
path conventions, the login service, opening and picking files, directory
links (symlink / junction / copy), process spawning and signals, file
watching, atomic replace with a retry where the platform refuses an open
target, and machine identity — goes through ports implemented in
`infrastructure/platform/` and bound at the composition root. An AST gate
forbids reading the platform, and calling the raw OS primitives listed
above, anywhere else. Only the macOS implementation is released; other
implementations may exist and be unit-tested, but are not claimed as
supported.

## Consequences

- Nothing is superseded. [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md)
  keeps its link / junction / copy design; its mechanics move behind the
  links port. [The Daemon Is Resident](daemon-is-a-resident-login-service.md)
  keeps launchd as the one implemented login service.
- Hooks Coffer writes into agent config (the Codex guard above) are generated
  by the platform layer, so a non-POSIX shell is one implementation away
  rather than a string to find.
- The gate is a new script beside `scripts/check_response_models.py`, listed
  in `.agents/harness.md` and run by `make lint`; `import-linter` contracts are
  unchanged.
- **Follow-up work:** the port interfaces and fakes; moving every site in the
  Context table and the unchecked `os.replace` / `os.kill` / `os.symlink`
  calls behind them; the AST gate, first for `domain/`, `application/` and
  `surfaces/`, then for `infrastructure/` outside `platform/` once those
  sites have moved; unit tests that run the non-macOS implementations against
  a fake filesystem.
