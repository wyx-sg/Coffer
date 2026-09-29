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
- **Shell syntax in a written hook.** `domain/memory/delivery.py` writes a
  command that begins with the POSIX no-op `: coffer-memory;` and reads
  `"$PWD"` — a POSIX shell command written into another program's config.

Two costs follow. The Windows branches in `application/` have never executed
in CI, so they are unverified code that reads as supported. And every one of
them is OS work done above `infrastructure/`, although the layering in
[Principles](../../docs-site/architecture/principles.md) gives adapter work
to `infrastructure`, which "adapts to ports defined in `application`";
`import-linter` cannot catch it, because `import sys` is
legitimate everywhere and the violation is an attribute access, not an import.

## Options Considered

### Option A — One platform port; an AST gate keeps checks out of the upper layers (chosen)

`infrastructure/platform/` holds every OS difference, in one themed module
per area below. The application reaches the areas it needs through one port
it declares, and the composition root binds the implementation for the
running OS:

| Area | Covers |
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
- **Cons.** Every current site moves, and the application's port and its
  fake grow a method each time a use case needs a new OS answer. An area
  for file watching is reserved before any consumer, which is a mild
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

The foundation does not assume macOS. Every platform-dependent operation
goes through `backend/coffer/infrastructure/platform/`, the only package that
reads which OS Coffer runs on. Only the macOS implementation is released;
the Windows and Linux branches that exist are unit-tested but not claimed as
supported.

- **One application-facing port.** `application/platform_port.py` declares
  `PlatformPort`: the OS label, the privileged-path rules (a
  `PrivilegedPaths` value — prefixes, carve-outs, separator, firmlink root),
  and the argv for open, reveal and the folder picker, plus how an installed
  editor is launched. Each method answers a question and runs nothing;
  spawning, validation and error mapping stay in the application. Its
  adapter, `HostPlatform`, is built once in the composition root and passed
  to the services that need it (`AgentService`, `AgentImportGate`,
  `MachineRegistry`, the three `fs` services). The port grows a method when
  a use case needs a new answer, not before.
- **Themed modules inside the package.** `host` (the `HostOs` answer and the
  OS label), `paths`, `desktop`, `links` (symlink, junction, copy, and
  classifying an existing link), `process` (executable name, detach flags,
  app bundles, launchd) and `identity` (the OS-kept machine id).
  Infrastructure imports these modules directly; the skill delivery engine
  exposes link inspection to the application through its own
  `SyncEnginePort.infer_link_mode`. The package is fenced as kind-agnostic.
- **The gate.** `scripts/check_platform_calls.py`, run by `make lint`, parses
  every module under `backend/coffer/` and fails on a read of
  `sys.platform` or `os.name`, a call to an OS-identifying `platform`
  function (`system`, `release`, `mac_ver`, …), `os.uname`,
  `sys.getwindowsversion`, or a direct import of those names — in every
  layer, infrastructure included, outside `infrastructure/platform/`. Tests
  are not scanned.

**Part 2** — not behind the port yet, and to be moved into the package in a
later change:

- atomic replace with a bounded retry where the platform refuses an open
  target, shared by every `os.replace` writer;
- process signals: stopping the daemon (`SIGTERM`) and the shim's shutdown
  handlers;
- the `~/.coffer/bin` symlinks `application/binary_deploy.py` creates and
  reads;
- the POSIX shell snippet in the Codex memory guard
  (`infrastructure/memory/delivery/codex.py`);
- file watching, when a consumer exists;
- path conventions: Coffer's home and an agent's default config directory;
- extending the gate to reject the raw primitives `os.replace`,
  `os.symlink` and `os.kill` above `infrastructure/`, once those sites have
  moved.

## Consequences

- Nothing is superseded. [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md)
  keeps its link / junction / copy design; its OS mechanics now live in
  `infrastructure/platform/links.py`. [The Daemon Is Resident](daemon-is-a-resident-login-service.md)
  keeps launchd as the one implemented login service.
- The application layer contains no OS check, so its use cases are tested
  with a fixed-answer fake port, and the platform package is tested per OS
  by pinning `sys.platform`.
- The gate is a script beside `scripts/check_response_models.py`, listed in
  `.agents/harness.md` and run by `make lint`; the import-linter contracts
  gain only the kind-agnostic fence for the two new modules.
- The Part 2 items are the remaining OS assumptions; each is invisible to
  the gate today because it carries no platform check, which is why the gate
  is extended only after they move.
- The architecture page [Platform port](../../docs-site/architecture/platform.md)
  explains the port, the wiring and how to add an OS-dependent operation.
