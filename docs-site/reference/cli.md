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
| `--verbose, -v` <span class="cli-chip">option</span> | flag |  | On an error, also show the request behind it (method, path, status) and, for an unexpected one, the traceback. |
| `--version` <span class="cli-chip">option</span> | flag |  | Print Coffer's version and exit. |
| `--install-completion` <span class="cli-chip">option</span> | flag |  | Install completion for the current shell. |
| `--show-completion` <span class="cli-chip">option</span> | flag |  | Show completion for the current shell, to copy it or customize the installation. |

## Command groups

| Group | Description |
| --- | --- |
| [`coffer run`](/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer update`](/reference/cli/update) | Upgrade Coffer to the newest release and restart the daemon on it. |
| [`coffer uninstall`](/reference/cli/uninstall) | Remove Coffer from this Mac: disconnect the agents, remove the skill links, start at login, the binaries and the installer's PATH lines, then stop the daemon. |
| [`coffer daemon`](/reference/cli/daemon) | The Coffer daemon: start, stop, status, and its settings. |
| [`coffer config`](/reference/cli/config) | Daemon settings read before it binds (work while it is down). |
| [`coffer log`](/reference/cli/log) | Read Coffer's audit, MCP and daemon logs. |
| [`coffer path`](/reference/cli/path) | Where Coffer keeps files you read directly. |
| [`coffer mcp`](/reference/cli/mcp) | MCP servers: register, change, test, their tools and logs. |
| [`coffer secret`](/reference/cli/secret) | Secrets: list, store, delete, reveal in the app, import, approvals. |
| [`coffer cli`](/reference/cli/cli) | Command-line tools Coffer manages for skills. |
| [`coffer proxy`](/reference/cli/proxy) | The local model proxy. |
| [`coffer vault`](/reference/cli/vault) | The vault's history and the hand edits it refused. |
| [`coffer custom-tool`](/reference/cli/custom-tool) | Custom tools: groups of HTTP API requests served as MCP tools. |
| [`coffer approval`](/reference/cli/approval) | Secret approvals: list, show, approve with Touch ID, reject, ask again. |
| [`coffer app`](/reference/cli/app) | The Coffer desktop app. |
| [`coffer resource`](/reference/cli/resource) | Any resource by uid: show, rename, switch on or off, reach, delete. |
| [`coffer channel`](/reference/cli/channel) | Messaging channels: status, pairing, people, notify, restart. |
| [`coffer knowledge`](/reference/cli/knowledge) | Knowledge collections (documents are plain files you edit directly). |
| [`coffer skill`](/reference/cli/skill) | Skills: import, update, delivery to agents, sources. |
| [`coffer agent`](/reference/cli/agent) | Manage coding agents: add, connect, their MCP entries, plugins and sessions. |
| [`coffer provider`](/reference/cli/provider) | Model providers: connections, prices, switching agents' models. |
| [`coffer model`](/reference/cli/model) | Ask a model endpoint which models it serves, or test it. |
| [`coffer conversation`](/reference/cli/conversation) | Conversations: rename, stop a turn, delete (list: agent session all). |
| [`coffer memory`](/reference/cli/memory) | Memory sync into each agent's own memory: state, sync now, preview, undo, curate. |
| [`coffer settings`](/reference/cli/settings) | Settings: approvals, secret storage, features, data, upkeep. |
| [`coffer attention`](/reference/cli/attention) | What needs you (the Overview list): list, ignore, un-ignore. |
| [`coffer usage`](/reference/cli/usage) | Model usage and cost. |
| [`coffer sync`](/reference/cli/sync) | Vault sync: remote, rounds, machines, conflicts. |
