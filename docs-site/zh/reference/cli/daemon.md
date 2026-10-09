---
title: coffer daemon
description: "The Coffer daemon: start, stop, status, and its settings."
pageClass: cli-ref
---

# coffer daemon

The Coffer daemon: start, stop, status, and its settings.

```sh
coffer daemon [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer daemon --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`daemon start`](#daemon-start) | Spawn the daemon as a detached background process. |
| [`daemon stop`](#daemon-stop) | Send SIGTERM to the running daemon and wait for it to exit. |
| [`daemon restart`](#daemon-restart) | Stop the running daemon (if any) and start a fresh one. |
| [`daemon status`](#daemon-status) | Show whether the daemon is running, and the passes it is running right now. |
| [`daemon reload`](#daemon-reload) | Ask the running daemon to restart itself. |
| [`daemon rotate-token`](#daemon-rotate-token) | Mint a new daemon token (clients re-read daemon.json). |
| [`daemon upgrade`](#daemon-upgrade) | Whether this daemon is older than the installed Coffer, and the hand-off. |
| [`daemon upgrade-check`](#daemon-upgrade-check) | Check for a newer release of the installer's binaries now. |
| [`daemon upgrade-auto-check`](#daemon-upgrade-auto-check) | Switch the daemon's daily release check on or off. |
| [`daemon setup-check`](#daemon-setup-check) | Look for git again while the daemon waits in its setup state. |
| [`daemon upkeep`](#daemon-upkeep) | The rewriting passes running now. |
| [`daemon port`](#daemon-port) | The port the daemon's next start uses. |
| [`daemon port show`](#daemon-port-show) | The port the daemon serves and the one its next start uses. |
| [`daemon port set`](#daemon-port-set) | Set the port of the next start. |
| [`daemon residency`](#daemon-residency) | Whether the daemon starts at login. |
| [`daemon residency show`](#daemon-residency-show) | Whether the daemon starts at login. |
| [`daemon residency set`](#daemon-residency-set) | Install or remove the login service. |

## daemon start

Spawn the daemon as a detached background process.

<p class="cli-label">概要</p>

```sh
coffer daemon start [OPTIONS]
```

## daemon stop

Send SIGTERM to the running daemon and wait for it to exit.

<p class="cli-label">概要</p>

```sh
coffer daemon stop [OPTIONS]
```

## daemon restart

Stop the running daemon (if any) and start a fresh one.

The way a changed setting — a fixed port above all — actually takes effect, since a running daemon owns its bound socket and cannot move without one.

<p class="cli-label">概要</p>

```sh
coffer daemon restart [OPTIONS]
```

## daemon status

Show whether the daemon is running, and the passes it is running right now.

Reports its version, port and pid, the event loop's lag (p99 and maximum over the last few minutes), how many background tasks are running and how many have crashed, and the long passes in flight (kind, target, start time), oldest first.

Read-only: when no daemon is running it says so and exits 3 instead of starting one.

<p class="cli-label">概要</p>

```sh
coffer daemon status [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## daemon reload

Ask the running daemon to restart itself.

<p class="cli-label">概要</p>

```sh
coffer daemon reload [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon rotate-token

Mint a new daemon token (clients re-read daemon.json).

<p class="cli-label">概要</p>

```sh
coffer daemon rotate-token [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon upgrade

Whether this daemon is older than the installed Coffer, and the hand-off.

<p class="cli-label">概要</p>

```sh
coffer daemon upgrade [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon upgrade-check

Check for a newer release of the installer's binaries now.

<p class="cli-label">概要</p>

```sh
coffer daemon upgrade-check [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon upgrade-auto-check

Switch the daemon's daily release check on or off. Body: enabled.

<p class="cli-label">概要</p>

```sh
coffer daemon upgrade-auto-check [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon setup-check

Look for git again while the daemon waits in its setup state.

<p class="cli-label">概要</p>

```sh
coffer daemon setup-check [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon upkeep

The rewriting passes running now.

<p class="cli-label">概要</p>

```sh
coffer daemon upkeep [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon port

The port the daemon's next start uses.

<p class="cli-label">概要</p>

```sh
coffer daemon port [OPTIONS] COMMAND [ARGS]...
```

子命令：`show`, `set`。

## daemon port show

The port the daemon serves and the one its next start uses.

<p class="cli-label">概要</p>

```sh
coffer daemon port show [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon port set

Set the port of the next start. Body: port.

<p class="cli-label">概要</p>

```sh
coffer daemon port set [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon residency

Whether the daemon starts at login.

<p class="cli-label">概要</p>

```sh
coffer daemon residency [OPTIONS] COMMAND [ARGS]...
```

子命令：`show`, `set`。

## daemon residency show

Whether the daemon starts at login.

<p class="cli-label">概要</p>

```sh
coffer daemon residency show [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## daemon residency set

Install or remove the login service. Body: login_service_installed.

<p class="cli-label">概要</p>

```sh
coffer daemon residency set [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
