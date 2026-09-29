---
title: Platform port
description: How Coffer keeps the operating system out of its foundation — the one package that knows the host OS, the port the application asks through, where it is wired, the AST gate that holds the line, and how to add a new OS-dependent operation.
---

# Platform port

Coffer ships for macOS only, but its foundation is not allowed to assume macOS. This page explains how that is arranged: one package in `infrastructure/` is the only code that asks which operating system Coffer runs on, the application reaches it through a small port, and a build gate fails any OS check that appears anywhere else. Read it before writing code whose behaviour differs between operating systems. The decision and the options weighed are in the ADR [Platform Differences Live Behind One Platform Port](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/platform-differences-live-behind-one-platform-port.md).

## The problem it solves

A local tool that works with files, processes and desktop applications touches the operating system constantly. Opening a file in an editor is `open -t` on macOS, `xdg-open` on Linux and `cmd /c start` on Windows. Delivering a skill is a symlink on POSIX, but on Windows a symlink may need developer mode, so the fallback is an NTFS junction or a copy. Starting the daemon at login is a launchd agent on macOS and does not exist in that form elsewhere.

Left alone, those differences end up as `if sys.platform == "darwin":` wherever each one is first needed. Before this port there were such checks in ten modules, six of them in the application layer: the agent service decided which paths were privileged, the three file-action services built per-OS argv and probed for installed editors, the skill service inspected Windows reparse points itself, and the machine registry read the OS name. That has two costs:

- **Porting becomes an archaeology project.** Supporting a second OS means finding every scattered check, and a check that is missed fails silently on the new OS, usually by doing the macOS thing.
- **Use cases stop being testable in isolation.** A service that branches on `sys.platform` can only be tested by pretending to be each OS, and the test proves the branch, not the use case.

The rule Coffer adopted is that the release can stay macOS-only while the foundation stays portable: every OS difference lives behind one seam, so adding an OS is filling in that seam, not searching the tree.

## The shape

There are two halves, split along the layering rule that the application defines ports and infrastructure adapts to them.

| Piece | Where | Role |
| --- | --- | --- |
| `PlatformPort` and `PrivilegedPaths` | [`application/platform_port.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/platform_port.py) | The `Protocol` the application asks, and the value it gets back for privileged paths. |
| `coffer.infrastructure.platform` | [`infrastructure/platform/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/platform) | The only package that reads `sys.platform` or calls `platform.system()`. |
| `HostPlatform` | `infrastructure/platform/adapter.py` | The adapter that implements `PlatformPort` for the running host. Stateless. |

Inside the package, `host.py` identifies the OS (`host_os()` returns a `HostOs` of `MACOS`, `WINDOWS`, `LINUX` or `OTHER`), and every other module in it branches on that answer. It is read on every call rather than cached, so a test that sets `sys.platform` sees the adapter follow.

### What the application can ask

The port carries only what an existing use case needs. Each method answers a question; none of them runs anything. Spawning, validation and error mapping stay in the application, which keeps the port small and lets a test replace it with a fixed answer.

| Method | Answers | Used by |
| --- | --- | --- |
| `os_label()` | The OS name and release, such as `Darwin 24.6.0`. | The machine registry, which publishes it in this machine's sync descriptor. |
| `privileged_paths()` | A `PrivilegedPaths` value: the system prefixes, the carve-outs inside them, the path separator, and the firmlink root (`/private` on macOS, none elsewhere). | The agent service and the sync import gate, which refuse a skill directory inside a system location. The matching logic stays in the application; only the data is per-OS. |
| `open_command(target, with_app)` | The argv that opens a path in a chosen application or the default one. | `FsOpenService` |
| `reveal_command(target)` | The argv that selects a path in the file manager (Finder, Explorer; on Linux, opening the folder). | `FsOpenService` |
| `folder_picker_command(start)` | The argv of the native folder dialog, or `None` where the host has none. | `FsPickService` |
| `editor_launch_value(app_bundle, command)` | The value that launches an installed editor: the bundle name on macOS if `<name>.app` exists, the command elsewhere if it is on `PATH`, else `None`. | `EditorDetectService` |

### What infrastructure uses directly

Infrastructure modules are allowed to import infrastructure, so they call the platform package's modules without going through the port:

| Module | Provides | Used by |
| --- | --- | --- |
| `links.py` | `link_directory` (symlink; on Windows symlink, then junction, then copy), `is_junction`, `remove_junction`, `infer_dir_link_kind`. Results are a kind-agnostic `DirLinkKind`. | The skill delivery engine (`infrastructure/skill/sync_engine.py`), which maps them to the skill kind's `LinkMode` and adds its own rules: never overwrite, only delete a real directory it created as a copy. |
| `process.py` | `executable_name` (`.exe` on Windows), `detached_popen_kwargs` (a new session on POSIX, no console on Windows), `has_app_bundles`, `has_launchd`. | Daemon spawn resolution and the launchd login service. |
| `identity.py` | `os_machine_id()`: `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux, `None` elsewhere. | Machine identity for vault sync, which hashes it and falls back to a stored id. |
| `paths.py`, `desktop.py` | The data and argv behind the port methods above. | `HostPlatform` |

The skill kind's `SyncEnginePort` also gained `infer_link_mode`, so the skill service asks the delivery engine what kind of link is on disk instead of reading Windows file attributes itself.

The whole package is fenced as kind-agnostic in the import contracts: it may not import any kind, because every kind may use it.

## Where it is wired

`HostPlatform` is built once, in the lifespan in [`surfaces/http/app.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/app.py), and handed on explicitly, the same way every other dependency travels through the [composition root](/architecture/layering#the-composition-root):

- to `wire_resource_kinds`, which passes it to the agent and skill wiring, where `AgentService` and `AgentImportGate` receive it;
- to `start_background_workers`, which passes it through `start_sync` to `wire_sync`, where `MachineRegistry` receives it;
- to `set_platform` in `surfaces/http/dependencies.py`, so the file-action routes can build `FsOpenService`, `FsPickService` and `EditorDetectService` per request with `Depends(get_platform)`.

No application module imports the adapter. A test builds the service with `HostPlatform()` when it wants the real host's answers, or with a small fake when it wants to test the use case alone (`backend/tests/unit/application/fs/_fake_platform.py`).

## The gate

Import contracts cannot enforce this rule: `sys`, `os` and `platform` are importable everywhere, and the check is an attribute read, not an import. [`scripts/check_platform_calls.py`](https://github.com/wyx-sg/Coffer/blob/main/scripts/check_platform_calls.py), run by `make lint` and therefore by `make verify`, parses every module under `backend/coffer/` with Python's `ast` module and fails on any of these outside `infrastructure/platform/`:

- a read of `sys.platform`, in any expression;
- a call to an OS-identifying function of the `platform` module: `system`, `release`, `version`, `mac_ver`, `win32_ver`, `win32_edition`, `libc_ver`, `freedesktop_os_release`, `uname`, `platform`;
- a read of `os.name`, or a call to `os.uname` or `sys.getwindowsversion`;
- the same names imported directly, such as `from sys import platform`.

It resolves module aliases (`import platform as _p` is still caught), and it does not confuse a local variable called `platform` with the module, because it only looks at names bound by an `import` statement. The failure message names the file, the line and the expression. Tests are not scanned, since setting `sys.platform` is how a test simulates a host.

## Adding an OS-dependent operation

When new code needs to behave differently per OS:

1. **Put the OS knowledge in `infrastructure/platform/`.** Add a function to the module it belongs with (or a new module), branching on `host_os()`. Give Windows and Linux a real answer where one is cheap, and otherwise an explicit fallback (`None`, a copy instead of a link) that the caller can handle. Keep macOS behaviour exactly as the release needs it.
2. **If the caller is in `application/`, extend the port.** Add a method to `PlatformPort` that answers the question the use case asks, implement it in `HostPlatform` by delegating to the function from step 1, and update the fake in the unit tests. If the caller is in `infrastructure/`, import the function directly and skip this step.
3. **Hand it in, never import it.** An application service that needs the port takes it as a constructor argument; the composition root passes the one `HostPlatform` it built.
4. **Test both halves.** Unit-test the platform function per OS by setting `sys.platform` with `monkeypatch` (see `backend/tests/unit/infrastructure/platform/`), and test the use case with a fake port.

If the gate fails on code you did not intend as an OS check, the fix is still to move it: a value that depends on the OS is an OS check, whatever it is used for.

## Not behind the port yet

The port covers every place that *read* the platform when it was introduced. A few OS assumptions carry no check at all, so the gate cannot see them, and they still call the OS directly:

- **Atomic replace.** `os.replace` is called by several writers (agent config files, the skill master store, binary deploy, the daemon discovery file). On Windows it fails while another process holds the target open, so these need one shared replace-with-retry.
- **Process signals.** Stopping the daemon sends `SIGTERM`, and the shim installs `SIGTERM` / `SIGINT` handlers; Windows has no `SIGTERM` between processes.
- **Symlinks outside skill delivery.** Binary deploy creates and reads the `~/.coffer/bin` symlinks with `os.symlink` / `os.readlink`.
- **Shell syntax in a written hook.** The Codex memory guard Coffer installs is a POSIX shell command.

Moving these behind the platform package, and then extending the gate to reject the raw primitives (`os.replace`, `os.symlink`, `os.kill`) above `infrastructure/`, is Part 2 of the ADR. None of them changes behaviour on macOS, which is why they did not block the port.

## Where it lives in the code

| Path | Contents |
| --- | --- |
| [`backend/coffer/application/platform_port.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/platform_port.py) | `PlatformPort`, `PrivilegedPaths`. |
| [`backend/coffer/infrastructure/platform/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/platform) | `host`, `paths`, `desktop`, `links`, `process`, `identity`, and the `HostPlatform` adapter. |
| [`scripts/check_platform_calls.py`](https://github.com/wyx-sg/Coffer/blob/main/scripts/check_platform_calls.py) | The AST gate. |
| [`backend/tests/unit/infrastructure/platform/`](https://github.com/wyx-sg/Coffer/tree/main/backend/tests/unit/infrastructure/platform) | Per-OS tests of the platform package. |
| [`backend/tests/integration/harness/test_platform_calls_gate.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/tests/integration/harness/test_platform_calls_gate.py) | Tests of the gate. |
