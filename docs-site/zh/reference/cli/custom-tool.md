---
title: coffer custom-tool
description: "Custom tools: groups of HTTP API requests served as MCP tools."
pageClass: cli-ref
---

# coffer custom-tool

Custom tools: groups of HTTP API requests served as MCP tools.

```sh
coffer custom-tool [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer custom-tool --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`custom-tool group`](#custom-tool-group) | Custom-tool groups: create, show, change, delete, switch, reach. |
| [`custom-tool group list`](#custom-tool-group-list) | Every group, failing first, with its health, environments and tools. |
| [`custom-tool group show`](#custom-tool-group-show) | A group: its environments with their secrets' state, its tools and reach. |
| [`custom-tool group create`](#custom-tool-group-create) | Create a group. |
| [`custom-tool group update`](#custom-tool-group-update) | Change a group's description or timeout (environments: ``custom-tool env``). |
| [`custom-tool group delete`](#custom-tool-group-delete) | Delete a group and its tools; secrets it alone used are released. |
| [`custom-tool group enable`](#custom-tool-group-enable) | Switch a group on: its tools reach the agents in its reach again. |
| [`custom-tool group disable`](#custom-tool-group-disable) | Switch a group off: no agent sees or calls its tools. |
| [`custom-tool group reach`](#custom-tool-group-reach) | Choose which agents see the group's tools: ``--agent`` (repeat) or ``--all``. |
| [`custom-tool import`](#custom-tool-import) | Read an OpenAPI document into draft tools. |
| [`custom-tool import read`](#custom-tool-import-read) | Read an OpenAPI document into draft tools; saves nothing. |
| [`custom-tool reimport`](#custom-tool-reimport) | Preview and apply a re-import of a group's OpenAPI document. |
| [`custom-tool reimport preview`](#custom-tool-reimport-preview) | What a re-import would add, remove, keep and change; changes nothing. |
| [`custom-tool reimport apply`](#custom-tool-reimport-apply) | Apply a re-import: removed tools go, chosen additions arrive switched on, kept tools keep their switch, and every environment is kept as it is. |
| [`custom-tool tool`](#custom-tool-tool) | One custom tool: add, show, change, switch, test, delete. |
| [`custom-tool tool list`](#custom-tool-tool-list) | A group's tools with their request, switch and 24-hour calls. |
| [`custom-tool tool show`](#custom-tool-tool-show) | One tool's definition: request template, headers, body and argument schema. |
| [`custom-tool tool add`](#custom-tool-tool-add) | Add a tool. |
| [`custom-tool tool update`](#custom-tool-tool-update) | Change only the fields given (``--header`` replaces every header). |
| [`custom-tool tool enable`](#custom-tool-tool-enable) | Switch a tool on. |
| [`custom-tool tool disable`](#custom-tool-tool-disable) | Switch a tool off: hidden from agents, and a call is refused. |
| [`custom-tool tool delete`](#custom-tool-tool-delete) | Delete a tool. |
| [`custom-tool tool test`](#custom-tool-tool-test) | Run a saved tool once in one environment; saves and logs nothing. |
| [`custom-tool tool test-draft`](#custom-tool-tool-test-draft) | Run a tool that is not saved, in one of the group's environments. |
| [`custom-tool tool test-unsaved`](#custom-tool-tool-test-unsaved) | Run a request of a group not saved yet: no secret, the URL SSRF-checked. |
| [`custom-tool env`](#custom-tool-env) | A group's environments: base URL, headers, secrets, variables. |
| [`custom-tool env list`](#custom-tool-env-list) | A group's environments: base URL, switch and the state of their secrets. |
| [`custom-tool env add`](#custom-tool-env-add) | Add an environment to a group; its tools are not copied. |
| [`custom-tool env update`](#custom-tool-env-update) | Change an environment. |
| [`custom-tool env enable`](#custom-tool-env-enable) | Switch an environment on: callers may choose it again. |
| [`custom-tool env disable`](#custom-tool-env-disable) | Switch an environment off: a call naming it is refused. |
| [`custom-tool env delete`](#custom-tool-env-delete) | Delete an environment (a group keeps at least one). |
| [`custom-tool env set-header`](#custom-tool-env-set-header) | Set one header row of an environment: a plain ``--value``, or ``--secret`` bound to it (which waits for approval before any request carries it). |
| [`custom-tool env unset-header`](#custom-tool-env-unset-header) | Remove one header row from an environment. |
| [`custom-tool env set-var`](#custom-tool-env-set-var) | Set one non-sensitive variable of an environment. |
| [`custom-tool env unset-var`](#custom-tool-env-unset-var) | Remove one variable from an environment. |

## custom-tool group

Custom-tool groups: create, show, change, delete, switch, reach.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group [OPTIONS] COMMAND [ARGS]...
```

子命令：`list`, `show`, `create`, `update`, `delete`, `enable`, `disable`, `reach`。

## custom-tool group list

Every group, failing first, with its health, environments and tools.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group show

A group: its environments with their secrets' state, its tools and reach.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group's name |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group create

Create a group. A secret binding that waits for approval exits 9 with the command that approves it.

Example: coffer custom-tool group create billing --env test=https://test.example --env live=https://api.example --secret-header Authorization=billing-token:Bearer

<p class="cli-label">概要</p>

```sh
coffer custom-tool group create [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group's name (fixed; prefixes its tools) |
| `--env` <span class="cli-chip">选项</span> | text（可重复） |  | An environment as name=base-URL; repeat for several |
| `--base-url` <span class="cli-chip">选项</span> | text |  | One environment named 'default' at this URL |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=value on every --env (plain, non-secret) |
| `--secret-header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=secret[:Scheme] on every --env |
| `--description` <span class="cli-chip">选项</span> | text |  | What the API is for |
| `--timeout` <span class="cli-chip">选项</span> | integer |  | Seconds per request (1-300) |
| `--agent` <span class="cli-chip">选项</span> | text（可重复） |  | Reach only this agent (name or uid); repeat. Default: every agent |
| `--from-openapi` <span class="cli-chip">选项</span> | text |  | An OpenAPI file or URL to draft the tools from |
| `--operation` <span class="cli-chip">选项</span> | text（可重复） |  | With --from-openapi: an operation key to import; repeat |
| `--response` <span class="cli-chip">选项</span> | text |  | Response settings as JSON {"diagnostic_headers": [...], "rules": [...]}: text, @file or - |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | The whole group as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group update

Change a group's description or timeout (environments: ``custom-tool env``).

<p class="cli-label">概要</p>

```sh
coffer custom-tool group update [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group's name |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--timeout` <span class="cli-chip">选项</span> | integer |  | The group's seconds per request |
| `--response` <span class="cli-chip">选项</span> | text |  | Response settings as JSON {"diagnostic_headers": [...], "rules": [...]}: text, @file or - |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group delete

Delete a group and its tools; secrets it alone used are released.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group delete [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group enable

Switch a group on: its tools reach the agents in its reach again.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group enable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group disable

Switch a group off: no agent sees or calls its tools.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group disable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool group reach

Choose which agents see the group's tools: ``--agent`` (repeat) or ``--all``.

<p class="cli-label">概要</p>

```sh
coffer custom-tool group reach [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--agent` <span class="cli-chip">选项</span> | text（可重复） |  | An agent (name or uid); repeat |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Reach every agent |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool import

Read an OpenAPI document into draft tools.

<p class="cli-label">概要</p>

```sh
coffer custom-tool import [OPTIONS] COMMAND [ARGS]...
```

子命令：`read`。

## custom-tool import read

Read an OpenAPI document into draft tools; saves nothing.

<p class="cli-label">概要</p>

```sh
coffer custom-tool import read [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--url` <span class="cli-chip">选项</span> | text |  | The document's URL |
| `--file` <span class="cli-chip">选项</span> | text |  | The document's path |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool reimport

Preview and apply a re-import of a group's OpenAPI document.

<p class="cli-label">概要</p>

```sh
coffer custom-tool reimport [OPTIONS] COMMAND [ARGS]...
```

子命令：`preview`, `apply`。

## custom-tool reimport preview

What a re-import would add, remove, keep and change; changes nothing.

<p class="cli-label">概要</p>

```sh
coffer custom-tool reimport preview [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--file` <span class="cli-chip">选项</span> | text |  | The document again (a file-imported group) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool reimport apply

Apply a re-import: removed tools go, chosen additions arrive switched on, kept tools keep their switch, and every environment is kept as it is.

<p class="cli-label">概要</p>

```sh
coffer custom-tool reimport apply [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--file` <span class="cli-chip">选项</span> | text |  |  |
| `--add` <span class="cli-chip">选项</span> | text（可重复） |  | An added operation's key to import; repeat |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool

One custom tool: add, show, change, switch, test, delete.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool [OPTIONS] COMMAND [ARGS]...
```

子命令：`list`, `show`, `add`, `update`, `enable`, `disable`, `delete`, `test`, `test-draft`, `test-unsaved`。

## custom-tool tool list

A group's tools with their request, switch and 24-hour calls.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool list [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool show

One tool's definition: request template, headers, body and argument schema.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool show [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool add

Add a tool. A read-only POST: ``--method POST --read-only``.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool add [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group |
| `--name` <span class="cli-chip">选项</span> | text |  | The tool's name |
| `--method` <span class="cli-chip">选项</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">选项</span> | text |  | Path template: /items/{id}?q={q}; {env:NAME} for a variable |
| `--description` <span class="cli-chip">选项</span> | text |  | What the tool does (agents read it) |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=value header; {argument} holes allowed; repeat |
| `--body-template` <span class="cli-chip">选项</span> | text |  | JSON body with {argument} holes: text, @file or - |
| `--schema` <span class="cli-chip">选项</span> | text |  | The arguments' JSON Schema: text, @file or - |
| `--changes-data / --read-only` <span class="cli-chip">选项</span> | boolean |  | Whether the tool changes data (default: on for every method but GET) |
| `--response-rules` <span class="cli-chip">选项</span> | text |  | Own response rules, a JSON array (text, @file or -); 'group' follows the group's |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | The tool as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool update

Change only the fields given (``--header`` replaces every header).

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool update [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--rename` <span class="cli-chip">选项</span> | text |  | A new name for the tool |
| `--method` <span class="cli-chip">选项</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">选项</span> | text |  | Path template: /items/{id}?q={q}; {env:NAME} for a variable |
| `--description` <span class="cli-chip">选项</span> | text |  | What the tool does (agents read it) |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=value header; {argument} holes allowed; repeat |
| `--body-template` <span class="cli-chip">选项</span> | text |  | JSON body with {argument} holes: text, @file or - |
| `--schema` <span class="cli-chip">选项</span> | text |  | The arguments' JSON Schema: text, @file or - |
| `--changes-data / --read-only` <span class="cli-chip">选项</span> | boolean |  | Whether the tool changes data (default: on for every method but GET) |
| `--response-rules` <span class="cli-chip">选项</span> | text |  | Own response rules, a JSON array (text, @file or -); 'group' follows the group's |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Fields to change, as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool enable

Switch a tool on.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool enable [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool disable

Switch a tool off: hidden from agents, and a call is refused.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool disable [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool delete

Delete a tool.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool delete [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool test

Run a saved tool once in one environment; saves and logs nothing.

Invalid arguments are refused before any request (exit 6, one error per field); a request the API answers with an error status exits 7. ``--dry-run`` prints the request instead of sending it.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool test [OPTIONS] NAME TOOL
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `TOOL` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--env` <span class="cli-chip">选项</span> | text |  | The environment to run it in (needed when several are on) |
| `--args` <span class="cli-chip">选项</span> | text |  | The arguments as a JSON object: text, @file or - |
| `--dry-run` <span class="cli-chip">选项</span> | 开关 |  | Print the request a call would send — URL, headers, body, timeout — and send nothing; secret headers show their secret's name, not its value |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool test-draft

Run a tool that is not saved, in one of the group's environments.

``--dry-run`` prints the request instead of sending it.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool test-draft [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group |
| `--env` <span class="cli-chip">选项</span> | text |  | The environment to run it in (needed when several are on) |
| `--args` <span class="cli-chip">选项</span> | text |  | The arguments as a JSON object: text, @file or - |
| `--dry-run` <span class="cli-chip">选项</span> | 开关 |  | Print the request a call would send — URL, headers, body, timeout — and send nothing; secret headers show their secret's name, not its value |
| `--response-rules` <span class="cli-chip">选项</span> | text |  | Own response rules, a JSON array (text, @file or -); 'group' follows the group's |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | The draft tool as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool tool test-unsaved

Run a request of a group not saved yet: no secret, the URL SSRF-checked.

<p class="cli-label">概要</p>

```sh
coffer custom-tool tool test-unsaved [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--base-url` <span class="cli-chip">选项</span> | text | 必填 | The draft environment's base URL |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=value; repeat (no secrets are sent) |
| `--var` <span class="cli-chip">选项</span> | text（可重复） |  | NAME=value for {env:NAME}; repeat |
| `--timeout` <span class="cli-chip">选项</span> | integer | `30` |  |
| `--response` <span class="cli-chip">选项</span> | text |  | The draft group's response settings as JSON: text, @file or - |
| `--args` <span class="cli-chip">选项</span> | text |  | The arguments as a JSON object: text, @file or - |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | The draft tool as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env

A group's environments: base URL, headers, secrets, variables.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env [OPTIONS] COMMAND [ARGS]...
```

子命令：`list`, `add`, `update`, `enable`, `disable`, `delete`, `set-header`, `unset-header`, `set-var`, `unset-var`。

## custom-tool env list

A group's environments: base URL, switch and the state of their secrets.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env list [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env add

Add an environment to a group; its tools are not copied.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env add [OPTIONS] NAME ENV
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | The group |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 | The new environment's name (any name you choose) |
| `--base-url` <span class="cli-chip">选项</span> | text | 必填 | Where this environment's requests go |
| `--header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=value (plain); repeat |
| `--secret-header` <span class="cli-chip">选项</span> | text（可重复） |  | Name=secret[:Scheme]: a stored secret's name; repeat |
| `--var` <span class="cli-chip">选项</span> | text（可重复） |  | NAME=value for {env:NAME}; repeat |
| `--timeout` <span class="cli-chip">选项</span> | integer |  | Seconds per request (default: the group's) |
| `--description` <span class="cli-chip">选项</span> | text | `""` |  |
| `--disabled` <span class="cli-chip">选项</span> | 开关 |  | Add it switched off |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env update

Change an environment. A new base URL asks again for its secrets' approval.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env update [OPTIONS] NAME ENV
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--base-url` <span class="cli-chip">选项</span> | text |  |  |
| `--rename` <span class="cli-chip">选项</span> | text |  | A new name (its approvals are kept) |
| `--timeout` <span class="cli-chip">选项</span> | integer |  | Its own seconds per request |
| `--group-timeout` <span class="cli-chip">选项</span> | 开关 |  | Use the group's timeout |
| `--description` <span class="cli-chip">选项</span> | text |  |  |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Fields to change as JSON (text, @file or -) |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env enable

Switch an environment on: callers may choose it again.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env enable [OPTIONS] NAME ENV
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env disable

Switch an environment off: a call naming it is refused.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env disable [OPTIONS] NAME ENV
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env delete

Delete an environment (a group keeps at least one).

<p class="cli-label">概要</p>

```sh
coffer custom-tool env delete [OPTIONS] NAME ENV
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env set-header

Set one header row of an environment: a plain ``--value``, or ``--secret`` bound to it (which waits for approval before any request carries it).

<p class="cli-label">概要</p>

```sh
coffer custom-tool env set-header [OPTIONS] NAME ENV HEADER
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `HEADER` <span class="cli-chip">参数</span> | text | 必填 | The header's name |
| `--value` <span class="cli-chip">选项</span> | text |  | A plain value |
| `--secret` <span class="cli-chip">选项</span> | text |  | A stored secret's name (its value stays in Coffer) |
| `--scheme` <span class="cli-chip">选项</span> | text |  | Sent before the secret: Bearer, Basic, Token… |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env unset-header

Remove one header row from an environment.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env unset-header [OPTIONS] NAME ENV HEADER
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `HEADER` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env set-var

Set one non-sensitive variable of an environment.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env set-var [OPTIONS] NAME ENV VAR VALUE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `VAR` <span class="cli-chip">参数</span> | text | 必填 | The variable's name ({env:NAME} in a tool) |
| `VALUE` <span class="cli-chip">参数</span> | text | 必填 | Its value: plain text, never a secret |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## custom-tool env unset-var

Remove one variable from an environment.

<p class="cli-label">概要</p>

```sh
coffer custom-tool env unset-var [OPTIONS] NAME ENV VAR
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 |  |
| `ENV` <span class="cli-chip">参数</span> | text | 必填 |  |
| `VAR` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
