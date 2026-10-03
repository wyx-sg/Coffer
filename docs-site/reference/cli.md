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
| [`coffer scan`](/reference/cli/scan) | List what agents hold that Coffer does not manage: agents, skills, MCP entries. |
| [`coffer run`](/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer attention`](/reference/cli/attention) | What needs you now, across every kind, with the route that acts on each. |
| [`coffer migrate`](/reference/cli/migrate) | Move this home out of coffer.db into the vault layout (once, daemon stopped). |
| [`coffer daemon`](/reference/cli/daemon) | Daemon lifecycle |
| [`coffer open`](/reference/cli/open) | Open Coffer's web UI in your browser. |
| [`coffer config`](/reference/cli/config) | Read and change Coffer's settings (coffer config list shows every key) |
| [`coffer log`](/reference/cli/log) | Read Coffer's records: the audit log, MCP calls and the daemon log |
| [`coffer path`](/reference/cli/path) | Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault) |
| [`coffer adopt`](/reference/cli/adopt) | Bring one scanned item under Coffer's management |
| [`coffer discard`](/reference/cli/discard) | Remove one scanned item from the agent that holds it |
| [`coffer mcp`](/reference/cli/mcp) | Manage MCP servers and their capabilities |
| [`coffer tool`](/reference/cli/tool) | Manage custom tools: HTTP API requests your agents call as tools |
| [`coffer secret`](/reference/cli/secret) | Manage encrypted secrets. |
| [`coffer agent`](/reference/cli/agent) | Manage registered AI agents |
| [`coffer channel`](/reference/cli/channel) | Manage messaging channels (Telegram, SeaTalk) |
| [`coffer skill`](/reference/cli/skill) | Manage skills (AgentSkills standard) |
| [`coffer cli`](/reference/cli/cli) | Add and check command-line tools |
| [`coffer knowledge`](/reference/cli/knowledge) | Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). |
| [`coffer memory`](/reference/cli/memory) | Browse and manage Coffer's memory layer |
| [`coffer provider`](/reference/cli/provider) | Manage LLM connections and switch agents onto them |
| [`coffer proxy`](/reference/cli/proxy) | Inspect the local model proxy and its per-agent tokens |
| [`coffer usage`](/reference/cli/usage) | Model usage through Coffer's proxy, and subscription quota |
| [`coffer sync`](/reference/cli/sync) | Keep this vault in step with a git remote you own |
| [`coffer vault`](/reference/cli/vault) | The vault's history: versions, diffs, restore, and hand edits that were refused. |
| [`coffer drift`](/reference/cli/drift) | See and repair drift between Coffer and the agents' own files |
