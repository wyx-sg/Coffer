---
title: coffer tool
description: "Manage custom tools: HTTP API requests your agents call as tools"
pageClass: cli-ref
---

# coffer tool

Manage custom tools: HTTP API requests your agents call as tools

```sh
coffer tool [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer tool --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`tool list`](#tool-list) | List every custom-tool group, failing ones first. |
| [`tool show`](#tool-show) | Show one group: its definition, its last 24 hours and its tools. |
| [`tool add`](#tool-add) | Create a group, empty or imported from an OpenAPI document. |
| [`tool edit`](#tool-edit) | Change a group's description, base URL, headers, auth or timeout (its name is fixed). |
| [`tool rm`](#tool-rm) | Remove a group and all its tools. |
| [`tool reimport`](#tool-reimport) | Read the group's OpenAPI source again: preview what it adds and removes, then apply. |
| [`tool enable`](#tool-enable) | Switch a custom-tool group on. |
| [`tool disable`](#tool-disable) | Switch a custom-tool group off: agents see none of its tools. |
| [`tool scope`](#tool-scope) | Show or set which agents a group reaches (this machine only). |
| [`tool op`](#tool-op) | Add, change, switch, narrow and test one tool of a group |
| [`tool op add`](#tool-op-add) | Add one request by hand to a group, using its base URL and auth. |
| [`tool op edit`](#tool-op-edit) | Change one tool's request; only the options given change (--arg replaces the arguments). |
| [`tool op rm`](#tool-op-rm) | Remove one tool from its group. |
| [`tool op enable`](#tool-op-enable) | Switch tools on. |
| [`tool op disable`](#tool-op-disable) | Switch tools off: agents no longer see or call them. |
| [`tool op scope`](#tool-op-scope) | Show or narrow which agents one tool reaches (this machine only). |
| [`tool op test`](#tool-op-test) | Call one tool once with sample arguments and print the response. |

## tool list

List every custom-tool group, failing ones first.

<p class="cli-label">概要</p>

```sh
coffer tool list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## tool show

Show one group: its definition, its last 24 hours and its tools.

<p class="cli-label">概要</p>

```sh
coffer tool show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## tool add

Create a group, empty or imported from an OpenAPI document.

With --openapi and no --operation, the GET operations are imported. Binding a stored secret waits for approval in the Coffer app; the command says so and exits 9, or waits with --wait.

<p class="cli-label">概要</p>

```sh
coffer tool add [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Group name (the agents' prefix; fixed, ≤24 chars) |
| `--base-url` <span class="cli-chip">选项</span> | text |  | Every tool's path is added to it |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Static header KEY=VALUE (repeatable) |
| `--auth-header` <span class="cli-chip">选项</span> | text |  | e.g. Authorization |
| `--auth-prefix` <span class="cli-chip">选项</span> | text |  | e.g. "Bearer " |
| `--secret` <span class="cli-chip">选项</span> | text |  | Secrets-page name for the auth header |
| `--timeout` <span class="cli-chip">选项</span> | integer | `30` | Per-request timeout in seconds (1-300) |
| `--agents` <span class="cli-chip">选项</span> | text |  | Only these agents (a,b) |
| `--openapi` <span class="cli-chip">选项</span> | text |  | Import from an OpenAPI URL or file |
| `--operation` <span class="cli-chip">选项</span> | text（可重复） |  | With --openapi: an operation to import, as "POST /refunds" (repeatable) |
| `--all-operations` <span class="cli-chip">选项</span> | 开关 |  | Import every operation |
| `--wait` <span class="cli-chip">选项</span> | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## tool edit

Change a group's description, base URL, headers, auth or timeout (its name is fixed).

Moving the base URL or binding another secret waits for approval in the Coffer app before the secret is sent there.

<p class="cli-label">概要</p>

```sh
coffer tool edit [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--base-url` <span class="cli-chip">选项</span> | text |  |  |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Static header KEY=VALUE (repeatable) |
| `--clear-headers` <span class="cli-chip">选项</span> | 开关 |  | Drop every static header first |
| `--auth-header` <span class="cli-chip">选项</span> | text |  |  |
| `--auth-prefix` <span class="cli-chip">选项</span> | text |  |  |
| `--secret` <span class="cli-chip">选项</span> | text |  | Secrets-page name for the auth header |
| `--clear-auth` <span class="cli-chip">选项</span> | 开关 |  | Remove the auth header |
| `--timeout` <span class="cli-chip">选项</span> | integer |  | Per-request timeout (1-300) |
| `--wait` <span class="cli-chip">选项</span> | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## tool rm

Remove a group and all its tools. The bound secret stays on the Secrets page.

<p class="cli-label">概要</p>

```sh
coffer tool rm [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## tool reimport

Read the group's OpenAPI source again: preview what it adds and removes, then apply.

Kept tools keep their switch, changes-data flag and reach override.

<p class="cli-label">概要</p>

```sh
coffer tool reimport [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `--file` <span class="cli-chip">选项</span> | text |  | The document again (a file import) |
| `--add` <span class="cli-chip">选项</span> | text（可重复） |  | An added operation to import, as "POST /refunds" |
| `--add-all` <span class="cli-chip">选项</span> | 开关 |  | Import every added operation |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Apply without asking |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the preview as JSON and stop |

## tool enable

Switch a custom-tool group on.

<p class="cli-label">概要</p>

```sh
coffer tool enable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## tool disable

Switch a custom-tool group off: agents see none of its tools.

<p class="cli-label">概要</p>

```sh
coffer tool disable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## tool scope

Show or set which agents a group reaches (this machine only).

<p class="cli-label">概要</p>

```sh
coffer tool scope [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--agents` <span class="cli-chip">选项</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Every agent |
| `--none` <span class="cli-chip">选项</span> | 开关 |  | No agent (dormant) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## tool op

Add, change, switch, narrow and test one tool of a group

<p class="cli-label">概要</p>

```sh
coffer tool op [OPTIONS] COMMAND [ARGS]...
```

子命令：`add`, `edit`, `rm`, `enable`, `disable`, `scope`, `test`。

## tool op add

Add one request by hand to a group, using its base URL and auth.

<p class="cli-label">概要</p>

```sh
coffer tool op add [OPTIONS] GROUP TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | Tool name (what follows &lt;group&gt;__) |
| `--method` <span class="cli-chip">选项</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">选项</span> | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` <span class="cli-chip">选项</span> | text |  | What the agent reads to decide |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` <span class="cli-chip">选项</span> | text |  | JSON body template with {arg} holes |
| `--arg` <span class="cli-chip">选项</span> | text（可重复） |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` <span class="cli-chip">选项</span> | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` <span class="cli-chip">选项</span> | boolean |  | Mark the tool as changing data (or not) |
| `--off` <span class="cli-chip">选项</span> | 开关 |  | Add it switched off |

## tool op edit

Change one tool's request; only the options given change (--arg replaces the arguments).

<p class="cli-label">概要</p>

```sh
coffer tool op edit [OPTIONS] GROUP TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | Tool name |
| `--name` <span class="cli-chip">选项</span> | text |  | A new tool name |
| `--method` <span class="cli-chip">选项</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">选项</span> | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` <span class="cli-chip">选项</span> | text |  | What the agent reads to decide |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` <span class="cli-chip">选项</span> | text |  | JSON body template with {arg} holes |
| `--clear-body` <span class="cli-chip">选项</span> | 开关 |  | Drop the body template |
| `--arg` <span class="cli-chip">选项</span> | text（可重复） |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` <span class="cli-chip">选项</span> | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` <span class="cli-chip">选项</span> | boolean |  | Mark the tool as changing data (or not) |

## tool op rm

Remove one tool from its group.

<p class="cli-label">概要</p>

```sh
coffer tool op rm [OPTIONS] GROUP TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | Tool name |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## tool op enable

Switch tools on.

<p class="cli-label">概要</p>

```sh
coffer tool op enable [OPTIONS] GROUP TOOLS...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOLS` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | Tool names |

## tool op disable

Switch tools off: agents no longer see or call them.

<p class="cli-label">概要</p>

```sh
coffer tool op disable [OPTIONS] GROUP TOOLS...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOLS` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | Tool names |

## tool op scope

Show or narrow which agents one tool reaches (this machine only).

<p class="cli-label">概要</p>

```sh
coffer tool op scope [OPTIONS] GROUP TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | Tool name |
| `--agents` <span class="cli-chip">选项</span> | text |  | Narrow to these agents (a,b) |
| `--group` <span class="cli-chip">选项</span> | 开关 |  | Clear the override |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## tool op test

Call one tool once with sample arguments and print the response. Exits 7 on failure.

<p class="cli-label">概要</p>

```sh
coffer tool op test [OPTIONS] GROUP TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">参数</span> | text | 必填 | Group name |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 | Tool name |
| `--arg-value` <span class="cli-chip">选项</span> | text（可重复） |  | An argument KEY=VALUE, JSON when it parses (repeatable) |
| `--args` <span class="cli-chip">选项</span> | text |  | All arguments as a JSON object |
