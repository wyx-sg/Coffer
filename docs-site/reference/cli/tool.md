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

This page matches what `coffer tool --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`tool list`](#tool-list) | List every custom-tool group, failing ones first. |
| [`tool show`](#tool-show) | Show one group: its definition, its last 24 hours and its tools. |
| [`tool add`](#tool-add) | Create a group, empty or imported from an OpenAPI document. |
| [`tool edit`](#tool-edit) | Change a group's description, base URL, headers or timeout (its name is fixed). |
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

<p class="cli-label">Synopsis</p>

```sh
coffer tool list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## tool show

Show one group: its definition, its last 24 hours and its tools.

<p class="cli-label">Synopsis</p>

```sh
coffer tool show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Group name |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## tool add

Create a group, empty or imported from an OpenAPI document.

With --openapi and no --operation, the GET operations are imported. Binding a stored secret waits for approval in the Coffer app; the command says so and exits 9, or waits with --wait.

<p class="cli-label">Synopsis</p>

```sh
coffer tool add [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Group name (the agents' prefix; fixed, ≤24 chars) |
| `--base-url` <span class="cli-chip">option</span> | text |  | Every tool's path is added to it |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--header` <span class="cli-chip">option</span> | text (repeatable) |  | Header NAME=VALUE (repeatable) |
| `--secret-header` <span class="cli-chip">option</span> | text (repeatable) |  | Header NAME=SECRET whose whole value is a Secrets-page secret (repeatable) |
| `--timeout` <span class="cli-chip">option</span> | integer | `30` | Per-request timeout in seconds (1-300) |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--openapi` <span class="cli-chip">option</span> | text |  | Import from an OpenAPI URL or file |
| `--operation` <span class="cli-chip">option</span> | text (repeatable) |  | With --openapi: an operation to import, as "POST /refunds" (repeatable) |
| `--all-operations` <span class="cli-chip">option</span> | flag |  | Import every operation |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## tool edit

Change a group's description, base URL, headers or timeout (its name is fixed).

Moving the base URL or binding another secret waits for approval in the Coffer app before the secret is sent there.

<p class="cli-label">Synopsis</p>

```sh
coffer tool edit [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Group name |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--base-url` <span class="cli-chip">option</span> | text |  |  |
| `--header` <span class="cli-chip">option</span> | text (repeatable) |  | Header NAME=VALUE (repeatable) |
| `--secret-header` <span class="cli-chip">option</span> | text (repeatable) |  | Header NAME=SECRET whose whole value is a Secrets-page secret (repeatable) |
| `--clear-headers` <span class="cli-chip">option</span> | flag |  | Drop every header first |
| `--timeout` <span class="cli-chip">option</span> | integer |  | Per-request timeout (1-300) |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## tool rm

Remove a group and all its tools. The bound secret stays on the Secrets page.

<p class="cli-label">Synopsis</p>

```sh
coffer tool rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Group name |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## tool reimport

Read the group's OpenAPI source again: preview what it adds and removes, then apply.

Kept tools keep their switch, changes-data flag and reach override.

<p class="cli-label">Synopsis</p>

```sh
coffer tool reimport [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Group name |
| `--file` <span class="cli-chip">option</span> | text |  | The document again (a file import) |
| `--add` <span class="cli-chip">option</span> | text (repeatable) |  | An added operation to import, as "POST /refunds" |
| `--add-all` <span class="cli-chip">option</span> | flag |  | Import every added operation |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Apply without asking |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the preview as JSON and stop |

## tool enable

Switch a custom-tool group on.

<p class="cli-label">Synopsis</p>

```sh
coffer tool enable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## tool disable

Switch a custom-tool group off: agents see none of its tools.

<p class="cli-label">Synopsis</p>

```sh
coffer tool disable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## tool scope

Show or set which agents a group reaches (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer tool scope [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Every agent |
| `--none` <span class="cli-chip">option</span> | flag |  | No agent (dormant) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## tool op

Add, change, switch, narrow and test one tool of a group

<p class="cli-label">Synopsis</p>

```sh
coffer tool op [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `add`, `edit`, `rm`, `enable`, `disable`, `scope`, `test`.

## tool op add

Add one request by hand to a group, using its base URL and auth.

<p class="cli-label">Synopsis</p>

```sh
coffer tool op add [OPTIONS] GROUP TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOL` <span class="cli-chip">argument</span> | text | required | Tool name (what follows &lt;group&gt;__) |
| `--method` <span class="cli-chip">option</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">option</span> | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` <span class="cli-chip">option</span> | text |  | What the agent reads to decide |
| `--header` <span class="cli-chip">option</span> | text (repeatable) |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` <span class="cli-chip">option</span> | text |  | JSON body template with {arg} holes |
| `--arg` <span class="cli-chip">option</span> | text (repeatable) |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` <span class="cli-chip">option</span> | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` <span class="cli-chip">option</span> | boolean |  | Mark the tool as changing data (or not) |
| `--off` <span class="cli-chip">option</span> | flag |  | Add it switched off |

## tool op edit

Change one tool's request; only the options given change (--arg replaces the arguments).

<p class="cli-label">Synopsis</p>

```sh
coffer tool op edit [OPTIONS] GROUP TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOL` <span class="cli-chip">argument</span> | text | required | Tool name |
| `--name` <span class="cli-chip">option</span> | text |  | A new tool name |
| `--method` <span class="cli-chip">option</span> | text |  | GET, POST, PUT, PATCH or DELETE |
| `--path` <span class="cli-chip">option</span> | text |  | Path template, e.g. /items/{id}?q={q} |
| `--description` <span class="cli-chip">option</span> | text |  | What the agent reads to decide |
| `--header` <span class="cli-chip">option</span> | text (repeatable) |  | Header KEY=VALUE, may hold {arg} (repeatable) |
| `--body` <span class="cli-chip">option</span> | text |  | JSON body template with {arg} holes |
| `--clear-body` <span class="cli-chip">option</span> | flag |  | Drop the body template |
| `--arg` <span class="cli-chip">option</span> | text (repeatable) |  | Argument name:type[:required][:description] (repeatable) |
| `--schema` <span class="cli-chip">option</span> | text |  | The whole argument schema as JSON |
| `--changes-data / --no-changes-data` <span class="cli-chip">option</span> | boolean |  | Mark the tool as changing data (or not) |

## tool op rm

Remove one tool from its group.

<p class="cli-label">Synopsis</p>

```sh
coffer tool op rm [OPTIONS] GROUP TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOL` <span class="cli-chip">argument</span> | text | required | Tool name |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## tool op enable

Switch tools on.

<p class="cli-label">Synopsis</p>

```sh
coffer tool op enable [OPTIONS] GROUP TOOLS...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOLS` <span class="cli-chip">argument</span> | text (variadic) | required | Tool names |

## tool op disable

Switch tools off: agents no longer see or call them.

<p class="cli-label">Synopsis</p>

```sh
coffer tool op disable [OPTIONS] GROUP TOOLS...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOLS` <span class="cli-chip">argument</span> | text (variadic) | required | Tool names |

## tool op scope

Show or narrow which agents one tool reaches (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer tool op scope [OPTIONS] GROUP TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOL` <span class="cli-chip">argument</span> | text | required | Tool name |
| `--agents` <span class="cli-chip">option</span> | text |  | Narrow to these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Reach every agent, later ones too |
| `--group` <span class="cli-chip">option</span> | flag |  | Clear the override |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## tool op test

Call one tool once with sample arguments and print the response. Exits 7 on failure.

<p class="cli-label">Synopsis</p>

```sh
coffer tool op test [OPTIONS] GROUP TOOL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `GROUP` <span class="cli-chip">argument</span> | text | required | Group name |
| `TOOL` <span class="cli-chip">argument</span> | text | required | Tool name |
| `--arg-value` <span class="cli-chip">option</span> | text (repeatable) |  | An argument KEY=VALUE, JSON when it parses (repeatable) |
| `--args` <span class="cli-chip">option</span> | text |  | All arguments as a JSON object |
