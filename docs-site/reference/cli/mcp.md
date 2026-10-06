---
title: coffer mcp
description: "MCP servers: register, change, test, their tools and logs."
pageClass: cli-ref
---

# coffer mcp

MCP servers: register, change, test, their tools and logs.

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer mcp --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`mcp test`](#mcp-test) | Re-query a server's capabilities, then report whether it answers. |
| [`mcp list`](#mcp-list) | Every server. |
| [`mcp show`](#mcp-show) | One server: its config, reach and state. |
| [`mcp update`](#mcp-update) | Change a server. |
| [`mcp delete`](#mcp-delete) | Delete a server. |
| [`mcp enable`](#mcp-enable) | Switch a server on. |
| [`mcp disable`](#mcp-disable) | Switch a server off. |
| [`mcp reach`](#mcp-reach) | Set the agents a server reaches. |
| [`mcp add`](#mcp-add) | Register a server. |
| [`mcp test-config`](#mcp-test-config) | Test a config before adding it; nothing is saved. |
| [`mcp status`](#mcp-status) | Why a server is in its state, and what to do. |
| [`mcp tools`](#mcp-tools) | The server's tools, resources and prompts with their switches. |
| [`mcp tiering`](#mcp-tiering) | Which tools agents see listed and which they find by search. |
| [`mcp exposure`](#mcp-exposure) | Choose how one tool is exposed. |
| [`mcp exposure-all`](#mcp-exposure-all) | Choose how several tools are exposed. |
| [`mcp calls`](#mcp-calls) | One server's calls and errors since a moment, per agent and per tool. |
| [`mcp server-log`](#mcp-server-log) | The newest lines of the server's own log. |
| [`mcp builtin`](#mcp-builtin) | Coffer's own built-in tools. |
| [`mcp tool`](#mcp-tool) | Switch a server's tools, prompts and resources on or off. |
| [`mcp tool enable`](#mcp-tool-enable) | Switch capabilities on. |
| [`mcp tool disable`](#mcp-tool-disable) | Switch capabilities off. |
| [`mcp resource`](#mcp-resource) | Read one of a server's resources now. |
| [`mcp resource read`](#mcp-resource-read) | Read one resource now, as its row's details do. |
| [`mcp prompt`](#mcp-prompt) | Fill one of a server's prompts and show the messages it makes. |
| [`mcp prompt get`](#mcp-prompt-get) | Fill one prompt now, as its row's details do. |

## mcp test

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp test [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Server name |
| `--prompt` <span class="cli-chip">option</span> | flag |  | On a failure, also print the prompt to give your agent |

## mcp list

Every server.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp show

One server: its config, reach and state.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp update

Change a server. Body: name, title, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp delete

Delete a server.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp enable

Switch a server on.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp enable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp disable

Switch a server off.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp disable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp reach

Set the agents a server reaches. Body: scope ({agents: [uid…]} or null).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp reach [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp add

Register a server. Body: kind=mcp_server, name, description, config.transport (stdio: command, args, env, secret_refs, cwd; http: url, headers, secret_refs, auth_schemes).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp test-config

Test a config before adding it; nothing is saved. Body: transport, secret_values, spawn_timeout_seconds, request_timeout_seconds.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp test-config [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp status

Why a server is in its state, and what to do.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp status [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tools

The server's tools, resources and prompts with their switches.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp tools [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--saved` <span class="cli-chip">option</span> | flag |  | Read the saved list without connecting |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tiering

Which tools agents see listed and which they find by search.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp tiering [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp exposure

Choose how one tool is exposed. Body: mode (auto | always | search).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp exposure [OPTIONS] UID TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `TOOL` <span class="cli-chip">argument</span> | text | required | tool |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp exposure-all

Choose how several tools are exposed. Body: tools, mode.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp exposure-all [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp calls

One server's calls and errors since a moment, per agent and per tool.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp calls [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--since` <span class="cli-chip">option</span> | text |  | ISO time; 24 hours ago by default |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp server-log

The newest lines of the server's own log.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp server-log [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp builtin

Coffer's own built-in tools.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp builtin [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tool

Switch a server's tools, prompts and resources on or off.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp tool [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `enable`, `disable`.

## mcp tool enable

Switch capabilities on. Body: capability_key (a list of keys).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp tool enable [OPTIONS] UID CAPABILITY_TYPE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `CAPABILITY_TYPE` <span class="cli-chip">argument</span> | text | required | tool, prompt or resource |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp tool disable

Switch capabilities off. Body: capability_key (a list of keys).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp tool disable [OPTIONS] UID CAPABILITY_TYPE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `CAPABILITY_TYPE` <span class="cli-chip">argument</span> | text | required | tool, prompt or resource |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp resource

Read one of a server's resources now.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp resource [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `read`.

## mcp resource read

Read one resource now, as its row's details do. Body: uri.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp resource read [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## mcp prompt

Fill one of a server's prompts and show the messages it makes.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp prompt [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `get`.

## mcp prompt get

Fill one prompt now, as its row's details do. Body: name, arguments.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp prompt get [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The mcp_server's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
