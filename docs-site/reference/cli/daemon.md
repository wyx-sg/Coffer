---
title: coffer daemon
description: "Daemon lifecycle"
---

# coffer daemon

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer daemon [OPTIONS] COMMAND [ARGS]...
```

Daemon lifecycle

## daemon start

```sh
coffer daemon start [OPTIONS]
```

Spawn the daemon as a detached background process.

## daemon stop

```sh
coffer daemon stop [OPTIONS]
```

Send SIGTERM to the running daemon and wait for it to exit.

## daemon restart

```sh
coffer daemon restart [OPTIONS]
```

Stop the running daemon (if any) and start a fresh one.

The way a changed setting — a fixed port above all — actually takes effect, since a running daemon owns its bound socket and cannot move without one.

## daemon status

```sh
coffer daemon status [OPTIONS]
```

Show whether the daemon is running, and the passes it is running right now.

Reports its version, port and pid, the event loop's lag (p99 and maximum over the last few minutes), how many background tasks are running and how many have crashed, and the long passes in flight (kind, target, start time), oldest first.

Read-only: when no daemon is running it says so and exits 3 instead of starting one.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## daemon rotate-token

```sh
coffer daemon rotate-token [OPTIONS]
```

Rotate the daemon API token and update daemon.json.

## daemon service

```sh
coffer daemon service [OPTIONS] COMMAND [ARGS]...
```

Run the daemon as a login service

Subcommands: `install`, `uninstall`, `status`.

## daemon service install

```sh
coffer daemon service install [OPTIONS]
```

Start the daemon at login, and restart it if it crashes.

## daemon service uninstall

```sh
coffer daemon service uninstall [OPTIONS]
```

Stop starting the daemon at login. Leaves a running daemon running.

## daemon service status

```sh
coffer daemon service status [OPTIONS]
```

Whether the login service is installed, and where.
