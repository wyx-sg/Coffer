---
title: coffer tool
description: "Manage custom tools: HTTP API requests your agents call as tools"
---

# coffer tool

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer tool [OPTIONS] COMMAND [ARGS]...
```

Manage custom tools: HTTP API requests your agents call as tools

## tool list

```sh
coffer tool list [OPTIONS]
```

List every custom-tool group, failing ones first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## tool show

```sh
coffer tool show [OPTIONS] NAME
```

Show one group: its definition, its last 24 hours and its tools.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## tool add

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

## tool edit

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

## tool rm

```sh
coffer tool rm [OPTIONS] NAME
```

Remove a group and all its tools. The bound secret stays on the Secrets page.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Group name |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## tool reimport

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

## tool enable

```sh
coffer tool enable [OPTIONS] NAME
```

Switch a custom-tool group on.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## tool disable

```sh
coffer tool disable [OPTIONS] NAME
```

Switch a custom-tool group off: agents see none of its tools.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## tool scope

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

## tool op

```sh
coffer tool op [OPTIONS] COMMAND [ARGS]...
```

Add, change, switch, narrow and test one tool of a group

子命令：`add`, `edit`, `rm`, `enable`, `disable`, `scope`, `test`。

## tool op add

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

## tool op edit

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

## tool op rm

```sh
coffer tool op rm [OPTIONS] GROUP TOOL
```

Remove one tool from its group.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOL` | 参数 | text | 必填 | Tool name |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## tool op enable

```sh
coffer tool op enable [OPTIONS] GROUP TOOLS...
```

Switch tools on.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOLS` | 参数 | text（可变个数） | 必填 | Tool names |

## tool op disable

```sh
coffer tool op disable [OPTIONS] GROUP TOOLS...
```

Switch tools off: agents no longer see or call them.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `GROUP` | 参数 | text | 必填 | Group name |
| `TOOLS` | 参数 | text（可变个数） | 必填 | Tool names |

## tool op scope

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

## tool op test

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
