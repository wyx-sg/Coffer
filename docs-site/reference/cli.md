---
title: CLI reference
description: Every coffer command, argument and option, generated from the CLI itself.
---

# CLI reference

This page lists the options every `coffer` command takes and each top-level command
group. Each group has its own page with every command, argument and option in it. The
pages are generated from the CLI's own command tree, so they match what
`coffer <command> --help` prints for the version on `main`.

::: info Generated pages
Do not edit these pages by hand. Regenerate them with `make docs-reference`
(which runs `docs-site/scripts/gen_cli_reference.py`); `make lint` fails when a
page and the CLI disagree.
:::

Most commands talk to the local daemon over its management API and start it if it is
not running. For the exit codes every command shares, see
[Error codes](/reference/error-codes#cli-exit-codes).

## Global options

```sh
coffer [OPTIONS] COMMAND [ARGS]...
```

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--verbose, -v` <span class="cli-chip">option</span> | flag |  | Show full tracebacks and HTTP request/response context on error. |
| `--version` <span class="cli-chip">option</span> | flag |  | Print Coffer's version and exit. |
| `--install-completion` <span class="cli-chip">option</span> | flag |  | Install completion for the current shell. |
| `--show-completion` <span class="cli-chip">option</span> | flag |  | Show completion for the current shell, to copy it or customize the installation. |

## Command groups

| Group | Description |
| --- | --- |
| [`coffer run`](/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer daemon`](/reference/cli/daemon) | Daemon lifecycle |
| [`coffer config`](/reference/cli/config) | Read and change Coffer's settings (the keys read before the daemon starts) |
| [`coffer log`](/reference/cli/log) | Read Coffer's records: the audit log, MCP calls and the daemon log |
| [`coffer path`](/reference/cli/path) | Where Coffer's log files live |
| [`coffer mcp`](/reference/cli/mcp) | Check an MCP server |
| [`coffer secret`](/reference/cli/secret) | Manage encrypted secrets. |
| [`coffer vault`](/reference/cli/vault) | Hand edits the vault refused |
