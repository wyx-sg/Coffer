---
title: coffer daemon
description: "Daemon lifecycle"
pageClass: cli-ref
---

# coffer daemon

Daemon lifecycle

```sh
coffer daemon [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer daemon --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`daemon start`](#daemon-start) | Spawn the daemon as a detached background process. |
| [`daemon stop`](#daemon-stop) | Send SIGTERM to the running daemon and wait for it to exit. |
| [`daemon restart`](#daemon-restart) | Stop the running daemon (if any) and start a fresh one. |
| [`daemon status`](#daemon-status) | Show whether the daemon is running, and the passes it is running right now. |
| [`daemon rotate-token`](#daemon-rotate-token) | Rotate the daemon API token and update daemon.json. |
| [`daemon service`](#daemon-service) | Run the daemon as a login service |
| [`daemon service install`](#daemon-service-install) | Start the daemon at login, and restart it if it crashes. |
| [`daemon service uninstall`](#daemon-service-uninstall) | Stop starting the daemon at login. |
| [`daemon service status`](#daemon-service-status) | Whether the login service is installed, and where. |

## daemon start

Spawn the daemon as a detached background process.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon start [OPTIONS]
```

## daemon stop

Send SIGTERM to the running daemon and wait for it to exit.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon stop [OPTIONS]
```

## daemon restart

Stop the running daemon (if any) and start a fresh one.

The way a changed setting — a fixed port above all — actually takes effect, since a running daemon owns its bound socket and cannot move without one.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon restart [OPTIONS]
```

## daemon status

Show whether the daemon is running, and the passes it is running right now.

Reports its version, port and pid, the event loop's lag (p99 and maximum over the last few minutes), how many background tasks are running and how many have crashed, and the long passes in flight (kind, target, start time), oldest first.

Read-only: when no daemon is running it says so and exits 3 instead of starting one.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## daemon rotate-token

Rotate the daemon API token and update daemon.json.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon rotate-token [OPTIONS]
```

## daemon service

Run the daemon as a login service

<p class="cli-label">Synopsis</p>

```sh
coffer daemon service [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `install`, `uninstall`, `status`.

## daemon service install

Start the daemon at login, and restart it if it crashes.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon service install [OPTIONS]
```

## daemon service uninstall

Stop starting the daemon at login. Leaves a running daemon running.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon service uninstall [OPTIONS]
```

## daemon service status

Whether the login service is installed, and where.

<p class="cli-label">Synopsis</p>

```sh
coffer daemon service status [OPTIONS]
```
