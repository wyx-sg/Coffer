---
title: CLI 参考
description: 每一个 coffer 命令、参数和选项，由 CLI 自身生成。
---

# CLI 参考 {#cli-reference}

本页列出 `coffer` 的每个命令组、命令、参数和选项。它由 CLI 自己的命令树生成，所以和
`main` 上的版本执行 `coffer <command> --help` 打印的内容一致。命令说明直接取自 CLI，
因此保持英文。

::: info 生成的页面
不要手工编辑这个文件。用 `make docs-reference` 重新生成（它会运行
`docs-site/scripts/gen_cli_reference.py`）；页面和 CLI 不一致时 `make lint` 会失败。
:::

大多数命令通过管理 API 与本机的守护进程通信，守护进程没在运行时会先把它启动。所有命令
共用的退出码见[错误码](/zh/reference/error-codes#cli-exit-codes)。

## 全局选项 {#global-options}

```sh
coffer [OPTIONS] COMMAND [ARGS]...
```

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--verbose, -v` | 选项 | 开关 |  | Show full tracebacks and HTTP request/response context on error. |
| `--install-completion` | 选项 | 开关 |  | Install completion for the current shell. |
| `--show-completion` | 选项 | 开关 |  | Show completion for the current shell, to copy it or customize the installation. |

## 命令组 {#command-groups}

| 命令组 | 说明 |
| --- | --- |
| [`coffer scan`](#coffer-scan) | List what agents hold that Coffer does not manage: agents, skills, MCP entries. |
| [`coffer run`](#coffer-run) | Run a command with secrets set only in its environment. |
| [`coffer attention`](#coffer-attention) | What needs you now, across every kind, with the route that acts on each. |
| [`coffer migrate`](#coffer-migrate) | Move this home out of coffer.db into the vault layout (once, daemon stopped). |
| [`coffer daemon`](#coffer-daemon) | Daemon lifecycle |
| [`coffer open`](#coffer-open) | Open Coffer's web UI in your browser. |
| [`coffer config`](#coffer-config) | Read and change Coffer's settings (coffer config list shows every key) |
| [`coffer log`](#coffer-log) | Read Coffer's records: the audit log, MCP calls and the daemon log |
| [`coffer path`](#coffer-path) | Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault) |
| [`coffer adopt`](#coffer-adopt) | Bring one scanned item under Coffer's management |
| [`coffer discard`](#coffer-discard) | Remove one scanned item from the agent that holds it |
| [`coffer mcp`](#coffer-mcp) | Manage MCP servers and their capabilities |
| [`coffer tool`](#coffer-tool) | Manage custom tools: HTTP API requests your agents call as tools |
| [`coffer secret`](#coffer-secret) | Manage encrypted secrets. |
| [`coffer agent`](#coffer-agent) | Manage registered AI agents |
| [`coffer channel`](#coffer-channel) | Manage messaging channels (Telegram, SeaTalk) |
| [`coffer skill`](#coffer-skill) | Manage skills (AgentSkills standard) |
| [`coffer cli`](#coffer-cli) | Check the command-line tools skills and MCP servers require |
| [`coffer knowledge`](#coffer-knowledge) | Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). |
| [`coffer memory`](#coffer-memory) | Browse and manage Coffer's memory layer |
| [`coffer provider`](#coffer-provider) | Manage LLM connections and switch agents onto them |
| [`coffer proxy`](#coffer-proxy) | Inspect the local model proxy and its per-agent tokens |
| [`coffer usage`](#coffer-usage) | Model usage through Coffer's proxy, and subscription quota |
| [`coffer sync`](#coffer-sync) | Keep this vault in step with a git remote you own |
| [`coffer vault`](#coffer-vault) | The vault's history: versions, diffs, restore, and hand edits that were refused. |
| [`coffer drift`](#coffer-drift) | See and repair drift between Coffer and the agents' own files |

## coffer scan

```sh
coffer scan [OPTIONS]
```

List what agents hold that Coffer does not manage: agents, skills, MCP entries.

With --ref, show that one row in full: an MCP entry's whole configuration (secret values withheld) or an unmanaged skill's metadata.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent` | 选项 | text |  | Only what this agent holds |
| `--ref` | 选项 | text |  | Show one row in full: a type, a folder path or &lt;agent&gt;:&lt;entry&gt; |
| `--source` | 选项 | text |  | With --ref on an mcp row: the config-file key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## coffer run

```sh
coffer run [OPTIONS]
```

Run a command with secrets set only in its environment.

Each resolution is audited. Output is masked: exact secret values print as \*\*\*. This guards against accidents — a value landing in a transcript, a file or git — and does not hide a secret from an agent that runs the command: the agent is the command's parent and can read its environment.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--secret` | 选项 | text（可重复） |  | NAME or ENV=NAME of a standalone secret (repeatable) |
| `--env-file` | 选项 | path |  | KEY=VALUE file; coffer://secret/&lt;name&gt; values are resolved |
| `--no-masking` | 选项 | 开关 |  | Pass the child's output through unfiltered |

## coffer attention

```sh
coffer attention [OPTIONS]
```

What needs you now, across every kind, with the route that acts on each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | text |  | Print the hand-off prompt of the item with this key, to give an agent |

## coffer migrate

```sh
coffer migrate [OPTIONS]
```

Move this home out of coffer.db into the vault layout (once, daemon stopped).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--rollback` | 选项 | 开关 |  | Put this home back as it was before the upgrade. |
| `--resume` | 选项 | 开关 |  | Lift the hold a rollback left, so the upgrade can run again. |
| `--rehearse` | 选项 | 开关 |  | Run the upgrade and its rollback on a copy; the home itself is only read. |
| `--home` | 选项 | path |  | With --rehearse: the home to copy (default: $HOME). |

## coffer daemon

```sh
coffer daemon [OPTIONS] COMMAND [ARGS]...
```

Daemon lifecycle

### daemon start

```sh
coffer daemon start [OPTIONS]
```

Spawn the daemon as a detached background process.

### daemon stop

```sh
coffer daemon stop [OPTIONS]
```

Send SIGTERM to the running daemon and wait for it to exit.

### daemon restart

```sh
coffer daemon restart [OPTIONS]
```

Stop the running daemon (if any) and start a fresh one.

The way a changed setting — a fixed port above all — actually takes effect, since a running daemon owns its bound socket and cannot move without one.

### daemon status

```sh
coffer daemon status [OPTIONS]
```

Show whether the daemon is running, and the passes it is running right now.

Reports its version, channel, port and pid, and the long passes in flight (kind, target, start time), oldest first.

Read-only: when no daemon is running it says so and exits 3 instead of starting one.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### daemon rotate-token

```sh
coffer daemon rotate-token [OPTIONS]
```

Rotate the daemon API token and update daemon.json.

### daemon service

```sh
coffer daemon service [OPTIONS] COMMAND [ARGS]...
```

Run the daemon as a login service

子命令：`install`, `uninstall`, `status`。

### daemon service install

```sh
coffer daemon service install [OPTIONS]
```

Start the daemon at login, and restart it if it crashes.

### daemon service uninstall

```sh
coffer daemon service uninstall [OPTIONS]
```

Stop starting the daemon at login. Leaves a running daemon running.

### daemon service status

```sh
coffer daemon service status [OPTIONS]
```

Whether the login service is installed, and where.

## coffer open

```sh
coffer open [OPTIONS] COMMAND [ARGS]...
```

Open Coffer's web UI in your browser.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  |  |
| `--no-browser` | 选项 | 开关 |  | Print the URL instead of launching a browser. |

## coffer config

```sh
coffer config [OPTIONS] COMMAND [ARGS]...
```

Read and change Coffer's settings (coffer config list shows every key)

### config list

```sh
coffer config list [OPTIONS] [PREFIX]
```

List every key with its value, its default, its type and its help.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PREFIX` | 参数 | text | `""` | Only keys starting with this, e.g. engine. |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### config get

```sh
coffer config get [OPTIONS] KEY
```

Print a setting's current value.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### config set

```sh
coffer config set [OPTIONS] KEY VALUE
```

Change a setting; the value is checked against the key's type first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |
| `VALUE` | 参数 | text | 必填 | New value (see the key's type in config list) |

### config unset

```sh
coffer config unset [OPTIONS] KEY
```

Return a setting to its default.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |

## coffer log

```sh
coffer log [OPTIONS] COMMAND [ARGS]...
```

Read Coffer's records: the audit log, MCP calls and the daemon log

### log audit

```sh
coffer log audit [OPTIONS]
```

Read the audit log, newest first, one page at a time.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--kind` | 选项 | text |  | Only this resource kind |
| `--name` | 选项 | text |  | Only this resource (needs --kind) |
| `--event-type` | 选项 | text |  | Only this event type |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | 选项 | integer (1-500) | `50` | Most entries to print |
| `--cursor` | 选项 | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### log mcp

```sh
coffer log mcp [OPTIONS]
```

Read the MCP invocation log, newest first.

Without --server this is the log the Activity page shows, Coffer's own calls (server ``coffer``) and deleted servers' rows (``deleted:<name>``) included.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--server` | 选项 | text |  | One server; omit for every server |
| `--status` | 选项 | text |  | ok \| error |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--limit` | 选项 | integer (1-500) | `20` | Most calls to print |
| `--cursor` | 选项 | text |  | Read the page after this one: the next_cursor a previous read printed |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### log daemon

```sh
coffer log daemon [OPTIONS]
```

Read the tail of the daemon log, newest first, normalised as the Activity page shows it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--since` | 选项 | text |  | ISO 8601 instant, or an age such as 30m, 1h, 2d |
| `--errors` | 选项 | 开关 |  | Only errors |
| `--limit` | 选项 | integer (1-500) | `100` | Most records to print |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### log prune

```sh
coffer log prune [OPTIONS]
```

Prune every registered log table now (or only --table), by its retention period.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--table` | 选项 | text |  | Prune only this table |

## coffer path

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault)

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path knowledge

```sh
coffer path knowledge [OPTIONS] [COLLECTION]
```

The knowledge root, or one collection's directory of Markdown documents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COLLECTION` | 参数 | text |  | A collection; omit for the knowledge root |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path memory

```sh
coffer path memory [OPTIONS] [PARTITION]
```

The memory root, or one partition's directory (MEMORY.md, notes/, RETIRED.md).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PARTITION` | 参数 | text |  | A partition; omit for the memory root |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path skill

```sh
coffer path skill [OPTIONS] NAME
```

A skill's master folder, which a person edits in place.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Skill name |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path agent

```sh
coffer path agent [OPTIONS] NAME config|memory|transcripts
```

An agent's own files: its config files, native memory stores, or transcript folders.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `CONFIG|MEMORY|TRANSCRIPTS` | 参数 | text | 必填 |  |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path logs

```sh
coffer path logs [OPTIONS]
```

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

### path vault

```sh
coffer path vault [OPTIONS]
```

The vault repository: configuration, knowledge and skill masters, in git.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON object keyed by what each path is |

## coffer adopt

```sh
coffer adopt [OPTIONS] COMMAND [ARGS]...
```

Bring one scanned item under Coffer's management

### adopt skill

```sh
coffer adopt skill [OPTIONS] PATH
```

Move an unmanaged skill folder into Coffer's master store and link it back.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The folder path the scan printed |

### adopt mcp

```sh
coffer adopt mcp [OPTIONS] AGENT:ENTRY
```

Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | 参数 | text | 必填 | The ref the scan printed |
| `--name` | 选项 | text |  | Register the server under this name |
| `--source` | 选项 | text |  | Config-file key when the entry is in several files |
| `--secret` | 选项 | text（可重复） |  | KEY=SECRET_REF for a secret-like env/header key (repeatable) |

## coffer discard

```sh
coffer discard [OPTIONS] COMMAND [ARGS]...
```

Remove one scanned item from the agent that holds it

### discard skill

```sh
coffer discard skill [OPTIONS] PATH
```

Delete an unmanaged skill folder from the agent's skill location (from disk).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The folder path the scan printed |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### discard mcp

```sh
coffer discard mcp [OPTIONS] AGENT:ENTRY
```

Remove an MCP entry from the agent's own config file (a .bak is kept).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | 参数 | text | 必填 | The ref the scan printed |
| `--source` | 选项 | text |  | Config-file key when the entry is in several files |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## coffer mcp

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

Manage MCP servers and their capabilities

### mcp add

```sh
coffer mcp add [OPTIONS] NAME
```

Register a new MCP server (stdio OR http; pick one).

A --secret citing a secret that already goes somewhere else waits for approval in the Coffer app before the server receives it; the command says so and exits 9, or waits with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Server name (fixed once registered, ≤24 chars) |
| `--stdio` | 选项 | text |  | Command line to launch, quoted as one string, e.g. 'npx -y my-server --flag' |
| `--http` | 选项 | text |  | HTTP MCP server URL |
| `--secret` | 选项 | text（可重复） |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### mcp list

```sh
coffer mcp list [OPTIONS]
```

List every registered MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### mcp show

```sh
coffer mcp show [OPTIONS] NAME
```

Show one MCP server, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### mcp edit

```sh
coffer mcp edit [OPTIONS] NAME
```

Change an MCP server's description, transport, env, headers, secret refs or timeouts (its name is fixed). Only the options given change.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | Refused: this kind's name is fixed once registered |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |
| `--stdio` | 选项 | text |  | New command line, quoted as one string (stdio transport) |
| `--http` | 选项 | text |  | New URL (http transport) |
| `--env` | 选项 | text（可重复） |  | Plain env var KEY=VALUE for a stdio server (repeatable) |
| `--clear-env` | 选项 | 开关 |  | Drop every plain env var first |
| `--header` | 选项 | text（可重复） |  | Plain header KEY=VALUE for an http server (repeatable) |
| `--clear-headers` | 选项 | 开关 |  | Drop every plain header first |
| `--cwd` | 选项 | text |  | Working directory (stdio); empty clears it |
| `--secret` | 选项 | text（可重复） |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--clear-secrets` | 选项 | 开关 |  | Drop every secret ref first |
| `--spawn-timeout-seconds` | 选项 | integer |  | Start-up timeout (5-120) |
| `--request-timeout-seconds` | 选项 | integer |  | Per-request timeout (5-1800) |

### mcp rm

```sh
coffer mcp rm [OPTIONS] NAME
```

Remove an MCP server registration.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### mcp enable

```sh
coffer mcp enable [OPTIONS] NAME
```

Enable a MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### mcp disable

```sh
coffer mcp disable [OPTIONS] NAME
```

Disable a MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### mcp scope

```sh
coffer mcp scope [OPTIONS] NAME
```

Show or set which agents a MCP server reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### mcp test

```sh
coffer mcp test [OPTIONS] NAME
```

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Server name |
| `--prompt` | 选项 | 开关 |  | On a failure, also print the prompt to give your agent |

### mcp handoff

```sh
coffer mcp handoff [OPTIONS] NAME
```

Print the prompt to give your agent for a server that needs one.

A server whose launcher is not found on this machine, or that is failing, has one — the same text its page and the Overview offer. Exits 5 when the server needs nothing.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Server name |

### mcp cap

```sh
coffer mcp cap [OPTIONS] COMMAND [ARGS]...
```

List and toggle a server's tools, prompts and resources

子命令：`list`, `enable`, `disable`。

### mcp cap list

```sh
coffer mcp cap list [OPTIONS] SERVER
```

List a server's capabilities, each with the ref that toggles it.

A tool whose client-visible name (mcp__coffer__&lt;server&gt;__&lt;tool&gt;) is over 64 characters is flagged; it stays enabled and listed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SERVER` | 参数 | text | 必填 | Server name |
| `--type` | 选项 | text |  | tool \| prompt \| resource |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### mcp cap enable

```sh
coffer mcp cap enable [OPTIONS] SERVER REF...
```

Enable capabilities, each named by a typed ref.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SERVER` | 参数 | text | 必填 | Server name |
| `REF...` | 参数 | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

### mcp cap disable

```sh
coffer mcp cap disable [OPTIONS] SERVER REF...
```

Disable capabilities, each named by a typed ref.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SERVER` | 参数 | text | 必填 | Server name |
| `REF...` | 参数 | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## coffer tool

```sh
coffer tool [OPTIONS] COMMAND [ARGS]...
```

Manage custom tools: HTTP API requests your agents call as tools

### tool list

```sh
coffer tool list [OPTIONS]
```

List every custom-tool group, failing ones first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### tool show

```sh
coffer tool show [OPTIONS] NAME
```

Show one group: its definition, its last 24 hours and its tools.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### tool add

```sh
coffer tool add [OPTIONS] NAME
```

Create a group, empty or imported from an OpenAPI document.

With --openapi and no --operation, the GET operations are imported. Binding a stored secret waits for approval in the Coffer app; the command says so and exits 9, or waits with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name (the agents' prefix; fixed, ≤24 chars) |
| `--base-url` | 选项 | text |  | Every tool's path is added to it |
| `--description` | 选项 | text |  |  |
| `--header` | 选项 | text（可重复） |  | Static header KEY=VALUE (repeatable) |
| `--auth-header` | 选项 | text |  | e.g. Authorization |
| `--auth-prefix` | 选项 | text |  | e.g. "Bearer " |
| `--secret` | 选项 | text |  | Secrets-page name for the auth header |
| `--timeout` | 选项 | integer | `30` | Per-request timeout in seconds (1-300) |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--openapi` | 选项 | text |  | Import from an OpenAPI URL or file |
| `--operation` | 选项 | text（可重复） |  | With --openapi: an operation to import, as "POST /refunds" (repeatable) |
| `--all-operations` | 选项 | 开关 |  | Import every operation |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### tool edit

```sh
coffer tool edit [OPTIONS] NAME
```

Change a group's description, base URL, headers, auth or timeout (its name is fixed).

Moving the base URL or binding another secret waits for approval in the Coffer app before the secret is sent there.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--description` | 选项 | text |  |  |
| `--base-url` | 选项 | text |  |  |
| `--header` | 选项 | text（可重复） |  | Static header KEY=VALUE (repeatable) |
| `--clear-headers` | 选项 | 开关 |  | Drop every static header first |
| `--auth-header` | 选项 | text |  |  |
| `--auth-prefix` | 选项 | text |  |  |
| `--secret` | 选项 | text |  | Secrets-page name for the auth header |
| `--clear-auth` | 选项 | 开关 |  | Remove the auth header |
| `--timeout` | 选项 | integer |  | Per-request timeout (1-300) |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### tool rm

```sh
coffer tool rm [OPTIONS] NAME
```

Remove a group and all its tools. The bound secret stays on the Secrets page.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### tool reimport

```sh
coffer tool reimport [OPTIONS] NAME
```

Read the group's OpenAPI source again: preview what it adds and removes, then apply.

Kept tools keep their switch, changes-data flag and reach override.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--file` | 选项 | text |  | The document again (a file import) |
| `--add` | 选项 | text（可重复） |  | An added operation to import, as "POST /refunds" |
| `--add-all` | 选项 | 开关 |  | Import every added operation |
| `--yes, -y` | 选项 | 开关 |  | Apply without asking |
| `--json` | 选项 | 开关 |  | Print the preview as JSON and stop |

### tool enable

```sh
coffer tool enable [OPTIONS] NAME
```

Switch a custom-tool group on.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### tool disable

```sh
coffer tool disable [OPTIONS] NAME
```

Switch a custom-tool group off: agents see none of its tools.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### tool scope

```sh
coffer tool scope [OPTIONS] NAME
```

Show or set which agents a group reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### tool op

```sh
coffer tool op [OPTIONS] COMMAND [ARGS]...
```

Add, change, switch, narrow and test one tool of a group

子命令：`add`, `edit`, `rm`, `enable`, `disable`, `scope`, `test`。

### tool op add

```sh
coffer tool op add [OPTIONS] GROUP TOOL
```

Add one request by hand to a group, using its base URL and auth.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name (what follows &lt;group&gt;__) |
| `--method` | 选项 | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` | 选项 | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` | 选项 | text |  | What the agent reads to decide |
| `--header` | 选项 | text（可重复） |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` | 选项 | text |  | JSON body template with {arg} holes |
| `--arg` | 选项 | text（可重复） |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` | 选项 | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` | 选项 | boolean |  | Mark the tool as changing data (or not) |
| `--off` | 选项 | 开关 |  | Add it switched off |

### tool op edit

```sh
coffer tool op edit [OPTIONS] GROUP TOOL
```

Change one tool's request; only the options given change (--arg replaces the arguments).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name |
| `--name` | 选项 | text |  | A new tool name |
| `--method` | 选项 | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` | 选项 | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` | 选项 | text |  | What the agent reads to decide |
| `--header` | 选项 | text（可重复） |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` | 选项 | text |  | JSON body template with {arg} holes |
| `--clear-body` | 选项 | 开关 |  | Drop the body template |
| `--arg` | 选项 | text（可重复） |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` | 选项 | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` | 选项 | boolean |  | Mark the tool as changing data (or not) |

### tool op rm

```sh
coffer tool op rm [OPTIONS] GROUP TOOL
```

Remove one tool from its group.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### tool op enable

```sh
coffer tool op enable [OPTIONS] GROUP TOOLS...
```

Switch tools on.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOLS` | 参数 | text（可变个数） | 必填 | Tool names |

### tool op disable

```sh
coffer tool op disable [OPTIONS] GROUP TOOLS...
```

Switch tools off: agents no longer see or call them.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOLS` | 参数 | text（可变个数） | 必填 | Tool names |

### tool op scope

```sh
coffer tool op scope [OPTIONS] GROUP TOOL
```

Show or narrow which agents one tool reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name |
| `--agents` | 选项 | text |  | Narrow to these agents (a,b) |
| `--group` | 选项 | 开关 |  | Clear the override |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### tool op test

```sh
coffer tool op test [OPTIONS] GROUP TOOL
```

Call one tool once with sample arguments and print the response. Exits 7 on failure.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name |
| `--arg-value` | 选项 | text（可重复） |  | An argument KEY=VALUE, JSON when it parses (repeatable) |
| `--args` | 选项 | text |  | All arguments as a JSON object |

## coffer secret

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

Manage encrypted secrets.

### secret set

```sh
coffer secret set [OPTIONS] REF
```

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--value` | 选项 | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### secret get

```sh
coffer secret get [OPTIONS] REF
```

Check that a secret is stored, without its value.

Prints [redacted] when it is, exits 4 when it is not. No value leaves the daemon and nothing is audited. To see a value, open the Coffer desktop app: it asks for Touch ID or your password each time.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### secret list

```sh
coffer secret list [OPTIONS]
```

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### secret rm

```sh
coffer secret rm [OPTIONS] REF
```

Delete a secret from the encrypted secret store (via the daemon).

Asks first unless --force is given.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--force, -f` | 选项 | 开关 |  | Skip confirmation prompt |

### secret approvals

```sh
coffer secret approvals [OPTIONS]
```

List what waits for approval in the Coffer app.

Approving takes Touch ID or your password in the desktop app; the terminal can only list and reject.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--all` | 选项 | 开关 |  | Include decided approvals |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### secret reject

```sh
coffer secret reject [OPTIONS] APPROVAL_ID
```

Refuse a pending approval. Refusing needs no presence check.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `APPROVAL_ID` | 参数 | text | 必填 | Approval id (see `coffer secret approvals`) |

### secret scan

```sh
coffer secret scan [OPTIONS]
```

Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

Prints where each one is and the name it would get — never the value. Move them into the encrypted store with `coffer secret import`.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ to an agent |

### secret import

```sh
coffer secret import [OPTIONS]
```

Move plaintext secrets into the encrypted store, leaving references.

Each value is stored as coffer://secret/&lt;name&gt;, read back and compared, and only then replaced in its file by the reference. No plaintext backup is kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--id` | 选项 | text（可重复） |  | Only this finding (repeatable; default: every finding) |
| `--dry-run` | 选项 | 开关 |  | Print the plan and write nothing |
| `--yes, -y` | 选项 | 开关 |  | Skip the confirmation prompt |

## coffer agent

```sh
coffer agent [OPTIONS] COMMAND [ARGS]...
```

Manage registered AI agents

### agent list

```sh
coffer agent list [OPTIONS]
```

List registered agents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### agent add

```sh
coffer agent add [OPTIONS] TYPE
```

Register the agent of TYPE — one per type, named by it.

Without ``--config-dir`` it is registered at the type's standard directory; an agent installed but never run gets that directory created. To move a registered agent, use ``coffer agent edit TYPE --config-dir``.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | claude-code \| codex |
| `--config-dir` | 选项 | text |  | Config directory other than the standard one (~/.claude etc.). |

### agent show

```sh
coffer agent show [OPTIONS] TYPE
```

Show one agent, with its Coffer connection part by part.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | Agent type (claude-code \| codex) or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### agent prompt

```sh
coffer agent prompt [OPTIONS] TYPE
```

Print the prompt to give your agent to install TYPE's program.

Offered while the program is not found, added or not — the same words the Agents page copies (spec agent-registry "Hand installing an agent's program to an agent").

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | claude-code \| codex |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### agent edit

```sh
coffer agent edit [OPTIONS] TYPE
```

Change an agent's config directory or model binding.

An agent's name is its type and it carries no title or description, so these are the whole of what can change. The model binding lives on the agent, not on the connection: an unbound agent projects no model and runs on its own default. A change here takes effect on disk the next time that agent's connection is activated (`coffer provider switch <name>`), which is what re-projects the config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | Agent type (claude-code \| codex) or uid |
| `--config-dir` | 选项 | text |  | Use a different config directory |
| `--model` | 选项 | text |  | Model this agent answers with |
| `--effort` | 选项 | text |  | Reasoning effort level |
| `--clear-effort` | 选项 | 开关 |  | Unbind the effort |
| `--tier` | 选项 | text（可重复） |  | Claude Code tier pin &lt;tier&gt;=&lt;model&gt; (opus, sonnet, haiku, fable); repeatable |
| `--clear-tiers` | 选项 | 开关 |  | Unbind every tier pin |
| `--wire-api` | 选项 | text |  | Codex wire api; `responses` is the only value it still loads |

### agent rm

```sh
coffer agent rm [OPTIONS] NAME
```

Remove an agent (re-discoverable by `coffer scan` — removal isn't permanent).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### agent enable

```sh
coffer agent enable [OPTIONS] NAME
```

Switch an agent back on: Coffer writes into and reads from it again.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### agent disable

```sh
coffer agent disable [OPTIONS] NAME
```

Switch an agent off: its delivered skills are reclaimed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### agent connect

```sh
coffer agent connect [OPTIONS] NAME
```

Connect this agent to Coffer: install every part that applies to it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |

### agent disconnect

```sh
coffer agent disconnect [OPTIONS] NAME
```

Disconnect this agent from Coffer: remove every part Coffer wrote into it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |

### agent transcript

```sh
coffer agent transcript [OPTIONS] NAME [ID]
```

List this agent's conversations on this machine, or print one of them.

The listing pages by cursor: a page with more after it ends with the --cursor value that reads the next one. With an ID, what comes back is a window — --limit turns from --offset, each cut at the server's per-turn cap and secret-scrubbed — and the header says how many turns the whole session holds.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `[ID]` | 参数 | text |  | A session id from the listing; omit to list sessions |
| `--limit` | 选项 | integer |  | Sessions to list (default 20) or turns to show (default 200) |
| `--offset` | 选项 | integer | `0` | With an ID: skip this many turns. |
| `--cursor` | 选项 | text |  | Listing: read the page after the one that printed this cursor. |
| `--query, -q` | 选项 | text |  | Search title or project path. |
| `--project` | 选项 | text |  | Only this exact project path. |
| `--sort` | 选项 | text |  | started_at \| last_activity_at (default) \| message_count |
| `--order` | 选项 | text |  | asc \| desc (default) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### agent models

```sh
coffer agent models [OPTIONS] AGENT_KEY
```

List the models a picker offers for this agent, with their effort levels.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT_KEY` | 参数 | text | 必填 | Agent type, e.g. claude_code or codex |
| `--json` | 选项 | 开关 |  | JSON output |

### agent hooks

```sh
coffer agent hooks [OPTIONS] NAME
```

List every hook the agent will run; Coffer's own is marked with \*.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `--json` | 选项 | 开关 |  | JSON output |

### agent config

```sh
coffer agent config [OPTIONS] COMMAND [ARGS]...
```

Write and delete an agent's config files (read them via `coffer path`)

子命令：`edit`, `rm`。

### agent config edit

```sh
coffer agent config edit [OPTIONS] NAME KEY[/CHILD]
```

Edit one config file, or one file inside a directory entry.

Opens $EDITOR on the current content, or takes it from --from-file. Coffer validates the content against the file's format (malformed JSON/TOML is rejected, exit 2, and the file is left unchanged), writes it atomically and keeps a `<path>.bak` of the prior version. A change made on disk since the read is refused (exit 5) instead of overwritten.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `KEY[/CHILD]` | 参数 | text | 必填 | Config-file key (e.g. settings, config, instructions), or KEY/CHILD for one file inside a directory entry (e.g. subagents/reviewer.md) |
| `--from-file` | 选项 | text |  | Take the new content from PATH ('-' for stdin) instead of opening $EDITOR. |

### agent config rm

```sh
coffer agent config rm [OPTIONS] NAME KEY/CHILD
```

Delete one file inside a directory entry (its content is kept as .bak).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `KEY/CHILD` | 参数 | text | 必填 | One file inside a directory entry (e.g. subagents/x.md) |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### agent plugin

```sh
coffer agent plugin [OPTIONS] COMMAND [ARGS]...
```

View and manage an agent's installed plugins

子命令：`list`, `show`, `enable`, `disable`, `rm`。

### agent plugin list

```sh
coffer agent plugin list [OPTIONS] NAME
```

List the agent's installed plugins and known marketplaces.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### agent plugin show

```sh
coffer agent plugin show [OPTIONS] NAME PLUGIN_ID
```

Show one plugin: its metadata, install dir and everything it contributes.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |
| `--json` | 选项 | 开关 |  | JSON output |

### agent plugin enable

```sh
coffer agent plugin enable [OPTIONS] NAME PLUGIN_ID
```

Enable a plugin in the agent's config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |

### agent plugin disable

```sh
coffer agent plugin disable [OPTIONS] NAME PLUGIN_ID
```

Disable a plugin in the agent's config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |

### agent plugin rm

```sh
coffer agent plugin rm [OPTIONS] NAME PLUGIN_ID
```

Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## coffer channel

```sh
coffer channel [OPTIONS] COMMAND [ARGS]...
```

Manage messaging channels (Telegram, SeaTalk)

### channel list

```sh
coffer channel list [OPTIONS]
```

List registered channels.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### channel show

```sh
coffer channel show [OPTIONS] NAME
```

Show a channel's configuration and status (runtime, binding, pairing, inbound).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output |

### channel add

```sh
coffer channel add [OPTIONS] NAME
```

Register a channel.

Its secrets are secret refs: store each secret first with `coffer secret set`, then pass the ref here.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `--type` | 选项 | text | 必填 | telegram \| seatalk |
| `--bot-token-ref` | 选项 | text |  | Secret ref of the Telegram bot token (store it with `coffer secret set`) |
| `--app-id` | 选项 | text |  | SeaTalk App ID |
| `--app-secret-ref` | 选项 | text |  | Secret ref of the SeaTalk app secret (store it with `coffer secret set`) |
| `--agent` | 选项 | text | 必填 | Name of the agent this channel drives by default (required) |
| `--agent-config` | 选项 | text |  | Default agent config as JSON |
| `--runs-on` | 选项 | text |  | machine_id of the machine that runs this channel (default: this one) |
| `--require-mention / --no-require-mention` | 选项 | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | 选项 | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | 选项 | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | 选项 | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | 选项 | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | 选项 | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--dir` | 选项 | text（可重复） |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--default-dir` | 选项 | text |  | The directory new conversations start in (default: the agent's own) |
| `--title` | 选项 | text |  | Display title (≤80 chars) |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### channel edit

```sh
coffer channel edit [OPTIONS] NAME
```

Change a channel's name, title, description, group gating, quiet windows, live status, completion ping, default directory or `/dir` directories.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |
| `--require-mention / --no-require-mention` | 选项 | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | 选项 | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | 选项 | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | 选项 | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | 选项 | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | 选项 | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--dir` | 选项 | text（可重复） |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--no-dirs` | 选项 | 开关 |  | Allow no directories for `/dir` (clears the list) |
| `--default-dir` | 选项 | text |  | The directory new conversations start in (default: the agent's own) |
| `--no-default-dir` | 选项 | 开关 |  | Clear the default directory (the agent's own applies) |

### channel rm

```sh
coffer channel rm [OPTIONS] NAME
```

Remove a channel and its pairings.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### channel enable

```sh
coffer channel enable [OPTIONS] NAME
```

Enable a channel (its adapter starts on the machine it is bound to).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### channel disable

```sh
coffer channel disable [OPTIONS] NAME
```

Disable a channel (its adapter stops).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### channel scope

```sh
coffer channel scope [OPTIONS] NAME
```

Show or set which agents a channel may drive (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### channel pair

```sh
coffer channel pair [OPTIONS] NAME
```

Issue a pairing code; send it to the bot from your own account.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |

### channel bind

```sh
coffer channel bind [OPTIONS] NAME [MACHINE_ID]
```

Bind a channel to the machine that should run its adapter.

Takes effect without a restart: the binding is config, and both daemons reconcile config on their own loop. The machine LOSING the channel stops its adapter within a tick of seeing the change; the machine gaining it starts one within a tick of the converge round that brings the change over. Run it from the machine that currently holds the channel and the handover has no overlap at all.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `MACHINE_ID` | 参数 | text |  | machine_id to bind to (default: this machine) |

### channel notify

```sh
coffer channel notify [OPTIONS] NAME TEXT
```

Push a message to one of the channel's paired chats.

Without ``--chat`` it goes to the owner chat — the channel's earliest pairing, which is the owner's DM. Naming a chat the channel is not paired to is refused rather than delivered somewhere else.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `TEXT` | 参数 | text | 必填 | Message text |
| `--chat` | 选项 | text |  | Paired chat id to push to (default: the owner's DM) |

## coffer skill

```sh
coffer skill [OPTIONS] COMMAND [ARGS]...
```

Manage skills (AgentSkills standard)

### skill list

```sh
coffer skill list [OPTIONS]
```

List managed skills.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### skill show

```sh
coffer skill show [OPTIONS] NAME
```

Show one skill, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### skill add

```sh
coffer skill add [OPTIONS] SOURCE
```

Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md.

A folder is imported at once. An archive or a repository is staged first: the command prints what it found and asks before adding anything.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SOURCE` | 参数 | text | 必填 | A skill folder, a .zip / .skill archive, or a Git URL |
| `--force, -f` | 选项 | 开关 |  | Replace an existing skill of the same name |
| `--ref` | 选项 | text |  | Git: branch, tag or commit |
| `--path` | 选项 | text |  | Git: folder inside the repository |
| `--skill` | 选项 | text（可重复） |  | Which skill to add when there are several (repeatable) |
| `--all` | 选项 | 开关 |  | Add every valid skill found |
| `--yes, -y` | 选项 | 开关 |  | Add without asking |

### skill update

```sh
coffer skill update [OPTIONS] NAME
```

Check a Git-imported skill for updates, preview one and apply it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--check` | 选项 | 开关 |  | Only check the source for newer commits |
| `--yes, -y` | 选项 | 开关 |  | Apply without asking |
| `--take-theirs` | 选项 | 开关 |  | Apply over local edits, discarding them |
| `--keep-mine` | 选项 | 开关 |  | Keep local edits and stop offering this update |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands merging the update into your edits to an agent |
| `--merged` | 选项 | text |  | Record that your edits were merged with the update at COMMIT: the pin moves there and the files stay as they are |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### skill rm

```sh
coffer skill rm [OPTIONS] NAME
```

Remove a skill and tear down all its agent deliveries. A skill Coffer generates itself is refused (exit 5).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### skill enable

```sh
coffer skill enable [OPTIONS] NAME
```

Enable a skill: it is delivered to every agent in its scope.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### skill disable

```sh
coffer skill disable [OPTIONS] NAME
```

Disable a skill: its delivered links are withdrawn.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### skill scope

```sh
coffer skill scope [OPTIONS] NAME
```

Show or set which agents a skill reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### skill verify

```sh
coffer skill verify [OPTIONS]
```

Report drift between bindings and on-disk symlinks.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--fix` | 选项 | 开关 |  | Re-deliver repairable drift (missing/tampered links) from master; leaves foreign content untouched. |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands each finding no repair settles to an agent |

## coffer cli

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

Check the command-line tools skills and MCP servers require

### cli list

```sh
coffer cli list [OPTIONS]
```

List every command a skill or MCP server requires, problems first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### cli show

```sh
coffer cli show [OPTIONS] COMMAND
```

Show one required command: where it is, its version and login state.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | The command, e.g. gh |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### cli check

```sh
coffer cli check [OPTIONS] [COMMAND]
```

Probe the required commands again (or one of them).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `[COMMAND]` | 参数 | text |  | One command only |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### cli prompt

```sh
coffer cli prompt [OPTIONS] COMMAND
```

Print the prompt to give your agent for a command that needs you.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | The command, e.g. jq |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## coffer knowledge

```sh
coffer knowledge [OPTIONS] COMMAND [ARGS]...
```

Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). Each collection is one tree of documents you and Coffer write together: read, grep and edit them with your own tools, and add new knowledge with `write` or `upload`: it waits as an item until Coffer curates it into the documents. `history`, `changes` and `undo` show and reverse what changed.

### knowledge list

```sh
coffer knowledge list [OPTIONS]
```

List every collection, with its documents and the items waiting to be curated.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### knowledge show

```sh
coffer knowledge show [OPTIONS] NAME
```

Show one collection, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### knowledge add

```sh
coffer knowledge add [OPTIONS] NAME
```

Create a collection. Nothing else creates one.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Collection name (one path segment) |
| `--description, -d` | 选项 | text | `""` | Written as the opening paragraph of its README.md |

### knowledge edit

```sh
coffer knowledge edit [OPTIONS] NAME
```

Rename a collection (its directory moves with it) or rewrite its description.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name (the folder moves) |
| `--description, -d` | 选项 | text |  | Rewrite the opening paragraph of its README.md |

### knowledge rm

```sh
coffer knowledge rm [OPTIONS] NAME
```

Remove a collection and its directory (`restore --deleted` brings it back).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### knowledge write

```sh
coffer knowledge write [OPTIONS]
```

Add new knowledge as an item. Coffer curates it into the documents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--title, -t` | 选项 | text | 必填 |  |
| `--description, -d` | 选项 | text | 必填 | What it is about |
| `--body, -b` | 选项 | text | `""` |  |
| `--in` | 选项 | text | 必填 | Collection to add it to |

### knowledge upload

```sh
coffer knowledge upload [OPTIONS] FILE
```

Convert a document to Markdown and add what it says to a collection.

The extracted text becomes an item that curation folds into the documents; neither the original nor the extracted file is kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `FILE` | 参数 | path | 必填 | Document to ingest |
| `--collection` | 选项 | text | 必填 | Collection to ingest it into |

### knowledge curate

```sh
coffer knowledge curate [OPTIONS] COLLECTION
```

Curate a collection now: one pass per pending item until none is left.

Items waiting in the inbox go first, oldest first, then documents edited since curation last saw them. Each pass is bounded and reports its status — ok, truncated (cut off; its item stays pending), too_large, failed — and the run stops at the first failed pass, leaving the rest pending. With no model configured, the inbox becomes documents as it stands (no_model). A run already curating the same collection is refused rather than queued.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COLLECTION` | 参数 | text | 必填 | Collection to curate |
| `--document` | 选项 | text | `""` | Curate just this document (a path under the collection) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### knowledge history

```sh
coffer knowledge history [OPTIONS] PATH
```

List a document's versions, newest first, with who wrote each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A document, e.g. shopee/infra/cache.md |
| `--version` | 选项 | text | `""` | Print this version's diff |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### knowledge restore

```sh
coffer knowledge restore [OPTIONS] [PATH] [VERSION]
```

Put one version of a document back, as a new version — or, with `--deleted`, bring back a deleted document or collection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | `""` | The document to restore |
| `VERSION` | 参数 | text | `""` | The version to put back (from `history`) |
| `--deleted` | 选项 | text | `""` | Bring back what this delete removed, a document or a whole collection (the delete's version, from `changes`) |

### knowledge changes

```sh
coffer knowledge changes [OPTIONS] [VERSION]
```

Recent changes to knowledge across collections, and the items waiting.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `VERSION` | 参数 | text | `""` | Show this change in full, with each document's diff |
| `--in` | 选项 | text | `""` | Only this collection |
| `--limit` | 选项 | integer | `20` | How many changes |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### knowledge undo

```sh
coffer knowledge undo [OPTIONS] VERSION
```

Undo a curation pass as a whole: every document it wrote or retired goes back to how it was. Refused, naming the document, if one has changed since.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `VERSION` | 参数 | text | 必填 | The curation pass to undo (from `changes`) |

## coffer memory

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

Browse and manage Coffer's memory layer

### memory list

```sh
coffer memory list [OPTIONS]
```

List every partition, with its note count and repository.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### memory show

```sh
coffer memory show [OPTIONS] NAME
```

Show one partition, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### memory edit

```sh
coffer memory edit [OPTIONS] NAME
```

Change a partition's title, description or settings.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### memory rm

```sh
coffer memory rm [OPTIONS] NAME
```

Remove a partition.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### memory sync

```sh
coffer memory sync [OPTIONS]
```

Update memory: read every registered agent's native memory, then distil.

Every partition left holding undistilled entries is distilled in the same call; one whose distil pass is already running is reported as skipped.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  |  |

### memory hook

```sh
coffer memory hook [OPTIONS]
```

Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

Every installed memory hook entry runs this; you rarely need to. It prints nothing, and exits 0, when the daemon is not running.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent-uid` | 选项 | text | 必填 | The uid of the agent whose hook is firing |
| `--cwd` | 选项 | text | `""` | Fallback working directory |

### memory delivered

```sh
coffer memory delivered [OPTIONS] [PARTITION]
```

What memory delivered in the last seven days, per agent — or, for one partition, the exact session-start text each agent is given.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PARTITION` | 参数 | text |  | A partition: print what each agent is given at session start |
| `--agent` | 选项 | text | `""` | Only this agent's text |
| `--json` | 选项 | 开关 |  | JSON output |

### memory trigger

```sh
coffer memory trigger [OPTIONS] COMMAND [ARGS]...
```

List, write, arm, disarm and delete memory triggers

子命令：`list`, `add`, `arm`, `disarm`, `delete`。

### memory trigger list

```sh
coffer memory trigger list [OPTIONS]
```

List every trigger, armed or proposed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output |

### memory trigger add

```sh
coffer memory trigger add [OPTIONS]
```

Write a trigger; it is armed by you as it is written.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--note` | 选项 | text | 必填 | &lt;partition&gt;/&lt;slug&gt; of the note |
| `--kind` | 选项 | text | `block` | block or context |
| `--command` | 选项 | text | `""` | Regex over the executing command |
| `--unless` | 选项 | text | `""` | Regex that keeps the trigger quiet |
| `--error` | 选项 | text | `""` | Regex over the command's output |
| `--body` | 选项 | text | `""` | Reason to show when the note is gone |
| `--json` | 选项 | 开关 |  | JSON output |

### memory trigger arm

```sh
coffer memory trigger arm [OPTIONS] TRIGGER_ID
```

Arm a trigger — a proposal takes effect only once a person arms it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |

### memory trigger disarm

```sh
coffer memory trigger disarm [OPTIONS] TRIGGER_ID
```

Disarm a trigger; it stays, as a proposal.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |

### memory trigger delete

```sh
coffer memory trigger delete [OPTIONS] TRIGGER_ID
```

Delete a trigger's file.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |

## coffer provider

```sh
coffer provider [OPTIONS] COMMAND [ARGS]...
```

Manage LLM connections and switch agents onto them

### provider list

```sh
coffer provider list [OPTIONS]
```

List every LLM connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### provider show

```sh
coffer provider show [OPTIONS] NAME
```

Show one connection, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### provider add

```sh
coffer provider add [OPTIONS] NAME
```

Create an LLM connection.

With --local the base URL must be a loopback address; Coffer detects the runtime there read-only (nothing is pulled or loaded) and records the wires it serves and each model's served context window.

For anthropic/openai/unknown supply exactly one of --secret / --secret-ref; an ollama connection needs neither. The new connection starts on the wire's own default reach; route it to specific agents (e.g. an openai gateway to Claude Code) with `coffer provider scope <name> --agents claude-code`. The model is chosen at the point of use, not on the connection.

A --secret-ref key that already goes somewhere else waits for approval in the Coffer app before this connection may send it: the command says so and exits 9, or waits for the answer with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Connection name |
| `--protocol` | 选项 | text | 必填 | Protocol: anthropic \| openai \| ollama \| unknown |
| `--base-url` | 选项 | text | 必填 | Upstream endpoint base URL |
| `--secret` | 选项 | text |  | API key (stored encrypted) |
| `--secret-ref` | 选项 | text |  | Reuse an existing secret ref instead of --secret |
| `--title` | 选项 | text |  | Display title (≤80 chars) |
| `--description` | 选项 | text |  |  |
| `--local` | 选项 | 开关 |  | A model runtime on this machine (Ollama, LM Studio, vLLM, llama-server): detect it, curate its tool-capable models, no key needed |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### provider edit

```sh
coffer provider edit [OPTIONS] NAME
```

Rename a connection, or change its title, description, endpoint, wire, key or fallback.

A rename changes the label and nothing else: the uid, the stored key and any projection into an agent stay where they are.

A wire change is refused while the connection is switched on, because the wire decides whether a connection can cover any agent at all. Run `coffer provider builtin <agent_type>` first, edit, then `coffer provider switch <name>` again.

A new --base-url for a connection whose key is already sent somewhere, or a new --secret for a key in use, waits for approval in the Coffer app: the change is saved, the command says what waits and exits 9, or waits for the answer with --wait.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--protocol` | 选项 | text |  | Correct the wire format: anthropic \| openai \| ollama \| unknown |
| `--base-url` | 选项 | text |  |  |
| `--secret` | 选项 | text |  | Rotate the stored API key |
| `--fallback / --no-fallback` | 选项 | boolean |  | Whether other providers' requests may fail over to this one |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### provider rm

```sh
coffer provider rm [OPTIONS] NAME
```

Remove a connection (its stored key goes with it when nothing else cites it).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

### provider enable

```sh
coffer provider enable [OPTIONS] NAME
```

Enable a connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### provider disable

```sh
coffer provider disable [OPTIONS] NAME
```

Disable a connection.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

### provider scope

```sh
coffer provider scope [OPTIONS] NAME
```

Show or set which agents a connection reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### provider switch

```sh
coffer provider switch [OPTIONS] NAME
```

Switch the agents this connection reaches onto it and write their native config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Connection to activate |

### provider builtin

```sh
coffer provider builtin [OPTIONS] AGENT_TYPE
```

Switch's other half: put every agent of this type back on its OWN login.

Removes Coffer's projection from the native config and clears the active connection covering it. Idempotent — a no-op when the agent already runs built-in.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT_TYPE` | 参数 | text | 必填 | Agent type: claude_code \| codex |

### provider detect-local

```sh
coffer provider detect-local [OPTIONS]
```

Find local model runtimes (read-only: nothing is pulled or loaded).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--base-url` | 选项 | text |  | A loopback URL to probe; default: each runtime's default port |
| `--json` | 选项 | 开关 |  | Machine-readable output |

### provider order

```sh
coffer provider order [OPTIONS] NAME...
```

Put providers in this order; the rest keep theirs, after them.

The order is fallback priority: when an agent's model is offered by more than one enabled provider, the proxy tries the agent's own provider first, then the others in this order, before the first byte of the answer.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME...` | 参数 | text（可变个数） | 必填 | Providers, first to last |

### provider price

```sh
coffer provider price [OPTIONS] NAME [MODEL]
```

Show each model's price on a provider and its source, or set one.

Without MODEL: every model the provider offers, with its price per 1M tokens (input · output) and where it came from — You set, From &lt;provider&gt; (its own API reported it), Bundled (the price list shipped with this release) or — when nothing prices it. With MODEL and --input/--output: record your own price, which wins over every other source. --reset removes it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Provider name or uid |
| `[MODEL]` | 参数 | text |  | Model to set or reset |
| `--input` | 选项 | float |  | USD per 1M input tokens |
| `--output` | 选项 | float |  | USD per 1M output tokens |
| `--cache-read` | 选项 | float |  | USD per 1M cache reads |
| `--cache-write` | 选项 | float |  | USD per 1M cache writes (5-minute) |
| `--reset` | 选项 | 开关 |  | Remove the price you set on MODEL |
| `--json` | 选项 | 开关 |  | Machine-readable output |

## coffer proxy

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

Inspect the local model proxy and its per-agent tokens

### proxy token

```sh
coffer proxy token [OPTIONS]
```

Print an agent's local proxy token (what its key helper runs).

The token unlocks only this machine's loopback model proxy; it is never a provider key. Exits 4 with nothing on stdout for an agent this machine does not have, so a stale helper fails instead of printing a token.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent-uid` | 选项 | text | 必填 | The agent whose token to print |

### proxy rotate

```sh
coffer proxy rotate [OPTIONS] REF
```

Replace an agent's local proxy token; the old one stops working at once.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Agent name or uid |

### proxy status

```sh
coffer proxy status [OPTIONS]
```

Show whether the model proxy is running, where, and how often it restarted.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | Machine-readable output |

## coffer usage

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

Model usage through Coffer's proxy, and subscription quota

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--range` | 选项 | text | `today` | today \| 7d \| 30d \| month \| custom |
| `--from` | 选项 | text |  | First day of a custom range |
| `--to` | 选项 | text |  | Last day of a custom range, inclusive |
| `--by` | 选项 | text | `model` | model \| agent \| day |
| `--agent` | 选项 | text |  | Only requests this agent type sent (claude_code \| codex) |
| `--provider` | 选项 | text |  | Only requests this provider (by name) served |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--csv` | 选项 | 开关 |  | CSV output |

### usage requests

```sh
coffer usage requests [OPTIONS]
```

List recent metered requests, newest first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--limit` | 选项 | integer (1-500) | `20` | Most requests to print |
| `--cursor` | 选项 | text |  | The next_cursor a read printed |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### usage quota

```sh
coffer usage quota [OPTIONS]
```

Show each subscription agent's official remaining quota.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--refresh` | 选项 | 开关 |  | Read Codex's windows now |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that has your agent set up the statusline wrapper |

### usage statusline

```sh
coffer usage statusline [OPTIONS] [COMMAND]...
```

Opt-in Claude Code statusLine wrapper: forward rate limits, then chain.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text（可变个数） |  | The original statusLine command to run after forwarding |

## coffer sync

```sh
coffer sync [OPTIONS] COMMAND [ARGS]...
```

Keep this vault in step with a git remote you own

### sync now

```sh
coffer sync now [OPTIONS]
```

Run one round with the remote, right now.

### sync status

```sh
coffer sync status [OPTIONS]
```

The remote, the last round, and anything waiting for you.

Exits 1 while a round waits for a person — stopped on conflicts, held, unable to reach or sign in to the remote, or paused because the vault is inside a synchronised folder — so a prompt or a monitor notices without reading the text. A paused remote exits 0.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands the current problem (a refused push or sign-in, an unreachable remote, git missing) to your agent |

### sync history

```sh
coffer sync history [OPTIONS]
```

Every round this machine has run, newest first, one line each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--limit` | 选项 | integer | `20` | How many rounds to show, newest first |

### sync rollback

```sh
coffer sync rollback [OPTIONS] RUN_ID
```

Put back what one round changed, from its snapshot.

The plan is printed first. Rolling back is a new commit on this machine, which the next round pushes; files edited since the round are kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `RUN_ID` | 参数 | integer | 必填 | The round to roll back (see coffer sync history) |
| `--yes, -y` | 选项 | 开关 |  | Do not ask before rolling back |

### sync join

```sh
coffer sync join [OPTIONS]
```

Join the configured remote. What joining would do is printed first; joining never deletes a file on either side.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--yes, -y` | 选项 | 开关 |  | Do not ask before joining |

### sync conflicts

```sh
coffer sync conflicts [OPTIONS]
```

The files the stopped round waits on (or the held deletions).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands merging the conflicting files to your agent |

### sync resolve

```sh
coffer sync resolve [OPTIONS] [PATH]
```

Answer one conflicting file, or record an agent's merge of them all with --merged. Nothing is written until 'continue'.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text |  | Vault-relative path of a conflicting file (not with --merged) |
| `--mine` | 选项 | 开关 |  | Keep this machine's version |
| `--theirs` | 选项 | 开关 |  | Take the other machine's version |
| `--edited` | 选项 | 开关 |  | Take the hand-merged copy 'coffer sync edit' opened |
| `--merged` | 选项 | 开关 |  | Record an agent's merge: every file handed to it takes its merged copy |

### sync edit

```sh
coffer sync edit [OPTIONS] PATH
```

Print the path of a marked-up copy of the file to hand-merge; then 'coffer sync resolve PATH --edited'. The vault's file is untouched.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | Vault-relative path of a conflicting file |

### sync continue

```sh
coffer sync continue [OPTIONS]
```

Continue the stopped round once every file has an answer.

### sync hold

```sh
coffer sync hold [OPTIONS]
```

Show a held round, or answer it: --confirm deletes the files, --restore keeps them. Either continues the round.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--confirm` | 选项 | 开关 |  | Delete the held files |
| `--restore` | 选项 | 开关 |  | Keep the held files |

### sync choose

```sh
coffer sync choose [OPTIONS] [PATH]
```

Settle a file a join found different on both sides.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text |  | A file that differs (omit to list them) |
| `--mine` | 选项 | 开关 |  | Keep this machine's version |
| `--theirs` | 选项 | 开关 |  | Take the remote's version |

### sync remote

```sh
coffer sync remote [OPTIONS] COMMAND [ARGS]...
```

The one git remote this vault syncs with

子命令：`set`, `clear`, `pause`, `resume`, `check`。

### sync remote set

```sh
coffer sync remote set [OPTIONS] URL
```

Configure the remote ('coffer sync remote check' looks at it first).

On a configured remote an option not given keeps its stored value, and a paused remote stays paused (`coffer sync remote resume` resumes it). A remote set for the first time takes the defaults and starts enabled.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `URL` | 参数 | text | 必填 | Git remote URL you own (https, ssh, or file://) |
| `--branch` | 选项 | text |  | Default main |
| `--interval` | 选项 | integer |  | Seconds between automatic rounds (default 3600) |
| `--with-secret / --without-secret` | 选项 | boolean |  | Carry the encrypted secrets (ciphertext, never the master key); default off |
| `--secret-ref` | 选项 | text |  | Name of the push token in the secret store ('' removes it) |
| `--username` | 选项 | text |  | User name an HTTPS token is sent with, for a host that does not imply it (default coffer; GitLab: oauth2 or your user name; Bitbucket and Azure DevOps need a real one) |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

### sync remote clear

```sh
coffer sync remote clear [OPTIONS]
```

Stop syncing: forget the remote. The vault is left exactly as it is.

### sync remote pause

```sh
coffer sync remote pause [OPTIONS]
```

Pause sync. The remote, its settings and the history are all kept.

### sync remote resume

```sh
coffer sync remote resume [OPTIONS]
```

Resume a paused remote where the vault left off.

### sync remote check

```sh
coffer sync remote check [OPTIONS] [URL]
```

Look at a remote without keeping it: empty, a Coffer vault (and its layout), another repository, unreachable, or refusing the token.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `URL` | 参数 | text |  | A remote to look at (default: the stored one) |
| `--branch` | 选项 | text |  | Default main |
| `--secret-ref` | 选项 | text |  | Push token to use |
| `--username` | 选项 | text |  | User name the token is sent with (default: the stored one, else coffer; GitLab: oauth2 or your user name) |

### sync machine

```sh
coffer sync machine [OPTIONS] COMMAND [ARGS]...
```

The machines sharing this vault

子命令：`list`, `rename`, `rm`。

### sync machine list

```sh
coffer sync machine list [OPTIONS]
```

Every machine sharing this vault.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### sync machine rename

```sh
coffer sync machine rename [OPTIONS] NAME
```

Rename this machine. Free: nothing keys on the label; the next round carries the new one.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 |  |

### sync machine rm

```sh
coffer sync machine rm [OPTIONS] MACHINE_ID
```

Retire another machine: its descriptor goes, in a commit of yours that the next round pushes. A machine that syncs again comes back.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `MACHINE_ID` | 参数 | text | 必填 |  |

### sync key

```sh
coffer sync key [OPTIONS] COMMAND [ARGS]...
```

Install a master key brought from another machine, or compare fingerprints. Exporting a key backup is done in the Coffer desktop app.

子命令：`import`, `fingerprint`。

### sync key import

```sh
coffer sync key import [OPTIONS] PATH
```

Install a master key brought from another machine.

A ``.cfk`` backup asks for the passphrase it was exported with, without echoing it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The key backup (coffer-master-key.cfk) exported from another machine, or a bare key |

### sync key fingerprint

```sh
coffer sync key fingerprint [OPTIONS]
```

This machine's key fingerprint, to compare with another machine's.

## coffer vault

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

The vault's history: versions, diffs, restore, and hand edits that were refused.

### vault history

```sh
coffer vault history [OPTIONS] PATH
```

List a file's or folder's versions, newest first, with who wrote each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file, or a folder ending in / |
| `--limit` | 选项 | integer | `20` | How many versions |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### vault diff

```sh
coffer vault diff [OPTIONS] PATH VERSION
```

Print what one version did to a file, as a unified diff.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file |
| `VERSION` | 参数 | text | 必填 | The version (from `history`) |

### vault show

```sh
coffer vault show [OPTIONS] PATH VERSION
```

Print a file's content as one version left it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file |
| `VERSION` | 参数 | text | 必填 | The version (from `history`) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### vault restore

```sh
coffer vault restore [OPTIONS] PATH VERSION
```

Put one version back, as a new version. A folder is restored whole: files the version did not have are removed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file, or a folder ending in / |
| `VERSION` | 参数 | text | 必填 | The version to put back (from `history`) |
| `--yes, -y` | 选项 | 开关 |  | Do not ask |

### vault problems

```sh
coffer vault problems [OPTIONS]
```

List hand edits that were refused: still on disk, not in effect until fixed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## coffer drift

```sh
coffer drift [OPTIONS] COMMAND [ARGS]...
```

See and repair drift between Coffer and the agents' own files

### drift list

```sh
coffer drift list [OPTIONS]
```

List every difference a reconcile pass would find now. Writes nothing.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--target` | 选项 | text |  | One target only |
| `--kind` | 选项 | text |  | Only items about this kind |
| `--uid` | 选项 | text |  | Only items about this resource |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

### drift repair

```sh
coffer drift repair [OPTIONS] [IDS]...
```

Apply drift items now. Each repair is audited with you as the actor.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `IDS` | 参数 | text（可变个数） |  | Item ids from `coffer drift list` |
| `--all` | 选项 | 开关 |  | Every item a request would repair |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
