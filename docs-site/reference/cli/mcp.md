---
title: coffer mcp
description: "Manage MCP servers and their capabilities"
---

# coffer mcp

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

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

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Server name (fixed once registered, ≤24 chars) |
| `--stdio` | option | text |  | Command line to launch, quoted as one string, e.g. 'npx -y my-server --flag' |
| `--http` | option | text |  | HTTP MCP server URL |
| `--secret` | option | text (repeatable) |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--description` | option | text |  |  |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## mcp list

```sh
coffer mcp list [OPTIONS]
```

List every registered MCP server.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## mcp show

```sh
coffer mcp show [OPTIONS] NAME
```

Show one MCP server, by name or uid.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--json` | option | flag |  | JSON output for scripts |

## mcp edit

```sh
coffer mcp edit [OPTIONS] NAME
```

Change an MCP server's description, transport, env, headers, secret refs or timeouts (its name is fixed). Only the options given change.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--name` | option | text |  | Refused: this kind's name is fixed once registered |
| `--description` | option | text |  |  |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |
| `--stdio` | option | text |  | New command line, quoted as one string (stdio transport) |
| `--http` | option | text |  | New URL (http transport) |
| `--env` | option | text (repeatable) |  | Plain env var KEY=VALUE for a stdio server (repeatable) |
| `--clear-env` | option | flag |  | Drop every plain env var first |
| `--header` | option | text (repeatable) |  | Plain header KEY=VALUE for an http server (repeatable) |
| `--clear-headers` | option | flag |  | Drop every plain header first |
| `--cwd` | option | text |  | Working directory (stdio); empty clears it |
| `--secret` | option | text (repeatable) |  | ENV_OR_HEADER=SECRET_REF (repeatable) |
| `--clear-secrets` | option | flag |  | Drop every secret ref first |
| `--spawn-timeout-seconds` | option | integer |  | Start-up timeout (5-120) |
| `--request-timeout-seconds` | option | integer |  | Per-request timeout (5-1800) |

## mcp rm

```sh
coffer mcp rm [OPTIONS] NAME
```

Remove an MCP server registration.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## mcp enable

```sh
coffer mcp enable [OPTIONS] NAME
```

Enable a MCP server.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## mcp disable

```sh
coffer mcp disable [OPTIONS] NAME
```

Disable a MCP server.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## mcp scope

```sh
coffer mcp scope [OPTIONS] NAME
```

Show or set which agents a MCP server reaches (this machine only).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--agents` | option | text |  | Only these agents (a,b) |
| `--all` | option | flag |  | Every agent |
| `--none` | option | flag |  | No agent (dormant) |
| `--json` | option | flag |  | JSON output for scripts |

## mcp test

```sh
coffer mcp test [OPTIONS] NAME
```

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Server name |
| `--prompt` | option | flag |  | On a failure, also print the prompt to give your agent |

## mcp handoff

```sh
coffer mcp handoff [OPTIONS] NAME
```

Print the prompt to give your agent for a server that needs one.

A server whose launcher is not found on this machine, or that is failing, has one — the same text its page and the Overview offer. Exits 5 when the server needs nothing.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Server name |

## mcp cap

```sh
coffer mcp cap [OPTIONS] COMMAND [ARGS]...
```

List and toggle a server's tools, prompts and resources

Subcommands: `list`, `enable`, `disable`, `expose`.

## mcp cap list

```sh
coffer mcp cap list [OPTIONS] SERVER
```

List a server's capabilities, each with the ref that toggles it.

A tool whose client-visible name (mcp__coffer__&lt;server&gt;__&lt;tool&gt;) is over 64 characters is flagged; it stays enabled and listed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `SERVER` | argument | text | required | Server name |
| `--type` | option | text |  | tool \| prompt \| resource |
| `--json` | option | flag |  | JSON output for scripts |

## mcp cap enable

```sh
coffer mcp cap enable [OPTIONS] SERVER REF...
```

Enable capabilities, each named by a typed ref.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `SERVER` | argument | text | required | Server name |
| `REF...` | argument | text (variadic) | required | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap disable

```sh
coffer mcp cap disable [OPTIONS] SERVER REF...
```

Disable capabilities, each named by a typed ref.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `SERVER` | argument | text | required | Server name |
| `REF...` | argument | text (variadic) | required | tool:&lt;name&gt; \| prompt:&lt;name&gt; \| resource:&lt;uri&gt; |

## mcp cap expose

```sh
coffer mcp cap expose [OPTIONS] SERVER MODE tool:<name>...
```

Set how tools are exposed: listed (pinned), search (search only) or auto (by usage).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `SERVER` | argument | text | required | Server name |
| `MODE` | argument | text | required | auto \| listed \| search |
| `TOOL:<NAME>...` | argument | text (variadic) | required | Tools to set |
