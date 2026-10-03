---
title: coffer mcp
description: "Manage MCP servers and their capabilities"
pageClass: cli-ref
---

# coffer mcp

Manage MCP servers and their capabilities

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer mcp --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`mcp add`](#mcp-add) | Register a new MCP server (stdio OR http; pick one). |
| [`mcp list`](#mcp-list) | List every registered MCP server. |
| [`mcp show`](#mcp-show) | Show one MCP server, by name or uid. |
| [`mcp edit`](#mcp-edit) | Change an MCP server's description, transport, env, headers, secret refs or timeouts (its name is fixed). |
| [`mcp rm`](#mcp-rm) | Remove an MCP server registration. |
| [`mcp enable`](#mcp-enable) | Enable a MCP server. |
| [`mcp disable`](#mcp-disable) | Disable a MCP server. |
| [`mcp scope`](#mcp-scope) | Show or set which agents a MCP server reaches (this machine only). |
| [`mcp test`](#mcp-test) | Re-query a server's capabilities, then report whether it answers. |
| [`mcp handoff`](#mcp-handoff) | Print the prompt to give your agent for a server that needs one. |
| [`mcp cap`](#mcp-cap) | List and toggle a server's tools, prompts and resources |
| [`mcp cap list`](#mcp-cap-list) | List a server's capabilities, each with the ref that toggles it. |
| [`mcp cap enable`](#mcp-cap-enable) | Enable capabilities, each named by a typed ref. |
| [`mcp cap disable`](#mcp-cap-disable) | Disable capabilities, each named by a typed ref. |
| [`mcp cap expose`](#mcp-cap-expose) | Set how tools are exposed: listed (pinned), search (search only) or auto (by usage). |

## mcp add

Register a new MCP server (stdio OR http; pick one).

A --secret citing a secret that already goes somewhere else waits for approval in the Coffer app before the server receives it; the command says so and exits 9, or waits with --wait.

<p class="cli-label">概要</p>

```sh
coffer mcp add [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Server name (fixed once registered, ≤24 chars) |
| `--stdio` <span class="cli-chip">选项</span> | text |  | Command line to launch, quoted as one string, e.g. 'npx -y my-server --flag' |
| `--http` <span class="cli-chip">选项</span> | text |  | HTTP MCP server URL |
| `--secret` <span class="cli-chip">选项</span> | text（可重复） |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--wait` <span class="cli-chip">选项</span> | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## mcp list

List every registered MCP server.

<p class="cli-label">概要</p>

```sh
coffer mcp list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## mcp show

Show one MCP server, by name or uid.

<p class="cli-label">概要</p>

```sh
coffer mcp show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## mcp edit

Change an MCP server's description, transport, env, headers, secret refs or timeouts (its name is fixed). Only the options given change.

<p class="cli-label">概要</p>

```sh
coffer mcp edit [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--name` <span class="cli-chip">选项</span> | text |  | Refused: this kind's name is fixed once registered |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--wait` <span class="cli-chip">选项</span> | 开关 |  | Wait for approval in the Coffer app instead of exiting |
| `--stdio` <span class="cli-chip">选项</span> | text |  | New command line, quoted as one string (stdio transport) |
| `--http` <span class="cli-chip">选项</span> | text |  | New URL (http transport) |
| `--env` <span class="cli-chip">选项</span> | text（可重复） |  | Plain env var KEY=VALUE for a stdio server (repeatable) |
| `--clear-env` <span class="cli-chip">选项</span> | 开关 |  | Drop every plain env var first |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Plain header KEY=VALUE for an http server (repeatable) |
| `--clear-headers` <span class="cli-chip">选项</span> | 开关 |  | Drop every plain header first |
| `--cwd` <span class="cli-chip">选项</span> | text |  | Working directory (stdio); empty clears it |
| `--secret` <span class="cli-chip">选项</span> | text（可重复） |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--clear-secrets` <span class="cli-chip">选项</span> | 开关 |  | Drop every secret ref first |
| `--spawn-timeout-seconds` <span class="cli-chip">选项</span> | integer |  | Start-up timeout (5-120) |
| `--request-timeout-seconds` <span class="cli-chip">选项</span> | integer |  | Per-request timeout (5-1800) |

## mcp rm

Remove an MCP server registration.

<p class="cli-label">概要</p>

```sh
coffer mcp rm [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## mcp enable

Enable a MCP server.

<p class="cli-label">概要</p>

```sh
coffer mcp enable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## mcp disable

Disable a MCP server.

<p class="cli-label">概要</p>

```sh
coffer mcp disable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## mcp scope

Show or set which agents a MCP server reaches (this machine only).

<p class="cli-label">概要</p>

```sh
coffer mcp scope [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--agents` <span class="cli-chip">选项</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Every agent |
| `--none` <span class="cli-chip">选项</span> | 开关 |  | No agent (dormant) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## mcp test

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

<p class="cli-label">概要</p>

```sh
coffer mcp test [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | On a failure, also print the prompt to give your agent |

## mcp handoff

Print the prompt to give your agent for a server that needs one.

A server whose launcher is not found on this machine, or that is failing, has one — the same text its page and the Overview offer. Exits 5 when the server needs nothing.

<p class="cli-label">概要</p>

```sh
coffer mcp handoff [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Server name |

## mcp cap

List and toggle a server's tools, prompts and resources

<p class="cli-label">概要</p>

```sh
coffer mcp cap [OPTIONS] COMMAND [ARGS]...
```

子命令：`list`, `enable`, `disable`, `expose`。

## mcp cap list

List a server's capabilities, each with the ref that toggles it.

A tool whose client-visible name (mcp__coffer__&lt;server&gt;__&lt;tool&gt;) is over 64 characters is flagged; it stays enabled and listed.

<p class="cli-label">概要</p>

```sh
coffer mcp cap list [OPTIONS] SERVER
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `--type` <span class="cli-chip">选项</span> | text |  | tool \| prompt \| resource |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## mcp cap enable

Enable capabilities, each named by a typed ref.

<p class="cli-label">概要</p>

```sh
coffer mcp cap enable [OPTIONS] SERVER REF...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `REF...` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap disable

Disable capabilities, each named by a typed ref.

<p class="cli-label">概要</p>

```sh
coffer mcp cap disable [OPTIONS] SERVER REF...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `REF...` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap expose

Set how tools are exposed: listed (pinned), search (search only) or auto (by usage).

<p class="cli-label">概要</p>

```sh
coffer mcp cap expose [OPTIONS] SERVER MODE tool:<name>...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `MODE` <span class="cli-chip">参数</span> | text | 必填 | auto \| listed \| search |
| `TOOL:<NAME>...` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | Tools to set |
