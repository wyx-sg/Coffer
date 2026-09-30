---
title: coffer tool
description: "Manage custom tools: HTTP API requests your agents call as tools"
---

# coffer tool

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer tool [OPTIONS] COMMAND [ARGS]...
```

Manage custom tools: HTTP API requests your agents call as tools

## tool list

```sh
coffer tool list [OPTIONS]
```

List every custom-tool group, failing ones first.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## tool show

```sh
coffer tool show [OPTIONS] NAME
```

Show one group: its definition, its last 24 hours and its tools.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Group name |
| `--json` | option | flag |  | JSON output for scripts |

## tool add

```sh
coffer tool add [OPTIONS] NAME
```

Create a group, empty or imported from an OpenAPI document.

With --openapi and no --operation, the GET operations are imported. Binding a stored secret waits for approval in the Coffer app; the command says so and exits 9, or waits with --wait.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Group name (the agents' prefix; fixed, ≤24 chars) |
| `--base-url` | option | text |  | Every tool's path is added to it |
| `--description` | option | text |  |  |
| `--header` | option | text (repeatable) |  | Static header KEY=VALUE (repeatable) |
| `--auth-header` | option | text |  | e.g. Authorization |
| `--auth-prefix` | option | text |  | e.g. "Bearer " |
| `--secret` | option | text |  | Secrets-page name for the auth header |
| `--timeout` | option | integer | `30` | Per-request timeout in seconds (1-300) |
| `--agents` | option | text |  | Only these agents (a,b) |
| `--openapi` | option | text |  | Import from an OpenAPI URL or file |
| `--operation` | option | text (repeatable) |  | With --openapi: an operation to import, as "POST /refunds" (repeatable) |
| `--all-operations` | option | flag |  | Import every operation |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## tool edit

```sh
coffer tool edit [OPTIONS] NAME
```

Change a group's description, base URL, headers, auth or timeout (its name is fixed).

Moving the base URL or binding another secret waits for approval in the Coffer app before the secret is sent there.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Group name |
| `--description` | option | text |  |  |
| `--base-url` | option | text |  |  |
| `--header` | option | text (repeatable) |  | Static header KEY=VALUE (repeatable) |
| `--clear-headers` | option | flag |  | Drop every static header first |
| `--auth-header` | option | text |  |  |
| `--auth-prefix` | option | text |  |  |
| `--secret` | option | text |  | Secrets-page name for the auth header |
| `--clear-auth` | option | flag |  | Remove the auth header |
| `--timeout` | option | integer |  | Per-request timeout (1-300) |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## tool rm

```sh
coffer tool rm [OPTIONS] NAME
```

Remove a group and all its tools. The bound secret stays on the Secrets page.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Group name |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## tool reimport

```sh
coffer tool reimport [OPTIONS] NAME
```

Read the group's OpenAPI source again: preview what it adds and removes, then apply.

Kept tools keep their switch, changes-data flag and reach override.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Group name |
| `--file` | option | text |  | The document again (a file import) |
| `--add` | option | text (repeatable) |  | An added operation to import, as "POST /refunds" |
| `--add-all` | option | flag |  | Import every added operation |
| `--yes, -y` | option | flag |  | Apply without asking |
| `--json` | option | flag |  | Print the preview as JSON and stop |

## tool enable

```sh
coffer tool enable [OPTIONS] NAME
```

Switch a custom-tool group on.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## tool disable

```sh
coffer tool disable [OPTIONS] NAME
```

Switch a custom-tool group off: agents see none of its tools.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## tool scope

```sh
coffer tool scope [OPTIONS] NAME
```

Show or set which agents a group reaches (this machine only).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--agents` | option | text |  | Only these agents (a,b) |
| `--all` | option | flag |  | Every agent |
| `--none` | option | flag |  | No agent (dormant) |
| `--json` | option | flag |  | JSON output for scripts |

## tool op

```sh
coffer tool op [OPTIONS] COMMAND [ARGS]...
```

Add, change, switch, narrow and test one tool of a group

Subcommands: `add`, `edit`, `rm`, `enable`, `disable`, `scope`, `test`.

## tool op add

```sh
coffer tool op add [OPTIONS] GROUP TOOL
```

Add one request by hand to a group, using its base URL and auth.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOL` | argument | text | required | Tool name (what follows &lt;group&gt;__) |
| `--method` | option | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` | option | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` | option | text |  | What the agent reads to decide |
| `--header` | option | text (repeatable) |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` | option | text |  | JSON body template with {arg} holes |
| `--arg` | option | text (repeatable) |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` | option | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` | option | boolean |  | Mark the tool as changing data (or not) |
| `--off` | option | flag |  | Add it switched off |

## tool op edit

```sh
coffer tool op edit [OPTIONS] GROUP TOOL
```

Change one tool's request; only the options given change (--arg replaces the arguments).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOL` | argument | text | required | Tool name |
| `--name` | option | text |  | A new tool name |
| `--method` | option | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` | option | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` | option | text |  | What the agent reads to decide |
| `--header` | option | text (repeatable) |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` | option | text |  | JSON body template with {arg} holes |
| `--clear-body` | option | flag |  | Drop the body template |
| `--arg` | option | text (repeatable) |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` | option | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` | option | boolean |  | Mark the tool as changing data (or not) |

## tool op rm

```sh
coffer tool op rm [OPTIONS] GROUP TOOL
```

Remove one tool from its group.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOL` | argument | text | required | Tool name |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## tool op enable

```sh
coffer tool op enable [OPTIONS] GROUP TOOLS...
```

Switch tools on.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOLS` | argument | text (variadic) | required | Tool names |

## tool op disable

```sh
coffer tool op disable [OPTIONS] GROUP TOOLS...
```

Switch tools off: agents no longer see or call them.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOLS` | argument | text (variadic) | required | Tool names |

## tool op scope

```sh
coffer tool op scope [OPTIONS] GROUP TOOL
```

Show or narrow which agents one tool reaches (this machine only).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOL` | argument | text | required | Tool name |
| `--agents` | option | text |  | Narrow to these agents (a,b) |
| `--group` | option | flag |  | Clear the override |
| `--json` | option | flag |  | JSON output for scripts |

## tool op test

```sh
coffer tool op test [OPTIONS] GROUP TOOL
```

Call one tool once with sample arguments and print the response. Exits 7 on failure.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `GROUP` | argument | text | required | Group name |
| `TOOL` | argument | text | required | Tool name |
| `--arg-value` | option | text (repeatable) |  | An argument KEY=VALUE, JSON when it parses (repeatable) |
| `--args` | option | text |  | All arguments as a JSON object |
