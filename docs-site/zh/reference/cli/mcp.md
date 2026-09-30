---
title: coffer mcp
description: "Manage MCP servers and their capabilities"
---

# coffer mcp

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

Manage MCP servers and their capabilities

## mcp add

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

## mcp list

```sh
coffer mcp list [OPTIONS]
```

List every registered MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## mcp show

```sh
coffer mcp show [OPTIONS] NAME
```

Show one MCP server, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## mcp edit

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

## mcp rm

```sh
coffer mcp rm [OPTIONS] NAME
```

Remove an MCP server registration.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## mcp enable

```sh
coffer mcp enable [OPTIONS] NAME
```

Enable a MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## mcp disable

```sh
coffer mcp disable [OPTIONS] NAME
```

Disable a MCP server.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## mcp scope

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

## mcp test

```sh
coffer mcp test [OPTIONS] NAME
```

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Server name |
| `--prompt` | 选项 | 开关 |  | On a failure, also print the prompt to give your agent |

## mcp handoff

```sh
coffer mcp handoff [OPTIONS] NAME
```

Print the prompt to give your agent for a server that needs one.

A server whose launcher is not found on this machine, or that is failing, has one — the same text its page and the Overview offer. Exits 5 when the server needs nothing.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Server name |

## mcp cap

```sh
coffer mcp cap [OPTIONS] COMMAND [ARGS]...
```

List and toggle a server's tools, prompts and resources

子命令：`list`, `enable`, `disable`。

## mcp cap list

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

## mcp cap enable

```sh
coffer mcp cap enable [OPTIONS] SERVER REF...
```

Enable capabilities, each named by a typed ref.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SERVER` | 参数 | text | 必填 | Server name |
| `REF...` | 参数 | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap disable

```sh
coffer mcp cap disable [OPTIONS] SERVER REF...
```

Disable capabilities, each named by a typed ref.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SERVER` | 参数 | text | 必填 | Server name |
| `REF...` | 参数 | text（可变个数） | 必填 | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |
