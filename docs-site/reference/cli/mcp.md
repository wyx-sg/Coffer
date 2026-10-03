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

This page matches what `coffer mcp --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
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

<p class="cli-label">Synopsis</p>

```sh
coffer mcp add [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Server name (fixed once registered, ≤24 chars) |
| `--stdio` <span class="cli-chip">option</span> | text |  | Command line to launch, quoted as one string, e.g. 'npx -y my-server --flag' |
| `--http` <span class="cli-chip">option</span> | text |  | HTTP MCP server URL |
| `--secret` <span class="cli-chip">option</span> | text (repeatable) |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## mcp list

List every registered MCP server.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## mcp show

Show one MCP server, by name or uid.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## mcp edit

Change an MCP server's description, transport, env, headers, secret refs or timeouts (its name is fixed). Only the options given change.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp edit [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--name` <span class="cli-chip">option</span> | text |  | Refused: this kind's name is fixed once registered |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |
| `--stdio` <span class="cli-chip">option</span> | text |  | New command line, quoted as one string (stdio transport) |
| `--http` <span class="cli-chip">option</span> | text |  | New URL (http transport) |
| `--env` <span class="cli-chip">option</span> | text (repeatable) |  | Plain env var KEY=VALUE for a stdio server (repeatable) |
| `--clear-env` <span class="cli-chip">option</span> | flag |  | Drop every plain env var first |
| `--header` <span class="cli-chip">option</span> | text (repeatable) |  | Plain header KEY=VALUE for an http server (repeatable) |
| `--clear-headers` <span class="cli-chip">option</span> | flag |  | Drop every plain header first |
| `--cwd` <span class="cli-chip">option</span> | text |  | Working directory (stdio); empty clears it |
| `--secret` <span class="cli-chip">option</span> | text (repeatable) |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--clear-secrets` <span class="cli-chip">option</span> | flag |  | Drop every secret ref first |
| `--spawn-timeout-seconds` <span class="cli-chip">option</span> | integer |  | Start-up timeout (5-120) |
| `--request-timeout-seconds` <span class="cli-chip">option</span> | integer |  | Per-request timeout (5-1800) |

## mcp rm

Remove an MCP server registration.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## mcp enable

Enable a MCP server.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp enable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## mcp disable

Disable a MCP server.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp disable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## mcp scope

Show or set which agents a MCP server reaches (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp scope [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Every agent |
| `--none` <span class="cli-chip">option</span> | flag |  | No agent (dormant) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

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

## mcp handoff

Print the prompt to give your agent for a server that needs one.

A server whose launcher is not found on this machine, or that is failing, has one — the same text its page and the Overview offer. Exits 5 when the server needs nothing.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp handoff [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Server name |

## mcp cap

List and toggle a server's tools, prompts and resources

<p class="cli-label">Synopsis</p>

```sh
coffer mcp cap [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `enable`, `disable`, `expose`.

## mcp cap list

List a server's capabilities, each with the ref that toggles it.

A tool whose client-visible name (mcp__coffer__&lt;server&gt;__&lt;tool&gt;) is over 64 characters is flagged; it stays enabled and listed.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp cap list [OPTIONS] SERVER
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">argument</span> | text | required | Server name |
| `--type` <span class="cli-chip">option</span> | text |  | tool \| prompt \| resource |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## mcp cap enable

Enable capabilities, each named by a typed ref.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp cap enable [OPTIONS] SERVER REF...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">argument</span> | text | required | Server name |
| `REF...` <span class="cli-chip">argument</span> | text (variadic) | required | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap disable

Disable capabilities, each named by a typed ref.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp cap disable [OPTIONS] SERVER REF...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">argument</span> | text | required | Server name |
| `REF...` <span class="cli-chip">argument</span> | text (variadic) | required | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap expose

Set how tools are exposed: listed (pinned), search (search only) or auto (by usage).

<p class="cli-label">Synopsis</p>

```sh
coffer mcp cap expose [OPTIONS] SERVER MODE tool:<name>...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `SERVER` <span class="cli-chip">argument</span> | text | required | Server name |
| `MODE` <span class="cli-chip">argument</span> | text | required | auto \| listed \| search |
| `TOOL:<NAME>...` <span class="cli-chip">argument</span> | text (variadic) | required | Tools to set |
