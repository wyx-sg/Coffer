---
title: coffer cli
description: "Add and check command-line tools, and read their interface"
---

# coffer cli

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

Add and check command-line tools, and read their interface

## cli list

```sh
coffer cli list [OPTIONS]
```

List every command-line tool — added by hand or required — problems first.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## cli add

```sh
coffer cli add [OPTIONS] COMMAND
```

Add a command-line tool by hand; no skill is needed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | A command name (jq) or the absolute path of an executable |
| `--title` | option | text |  | A display name |
| `--description` | option | text |  | What it is for |
| `--min-version` | option | text |  | Oldest wanted, like "2.40" |
| `--login-check` | option | text |  | A command line that exits 0 when logged in, like "gh auth status" |
| `--json` | option | flag |  | JSON output for scripts |

## cli edit

```sh
coffer cli edit [OPTIONS] COMMAND
```

Change a tool you added by hand (only the options you give change).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | A tool you added, e.g. jq |
| `--title` | option | text |  | A display name; '' clears it |
| `--description` | option | text |  | '' clears it |
| `--min-version` | option | text |  | '' clears it |
| `--login-check` | option | text |  | '' clears it |
| `--json` | option | flag |  | JSON output for scripts |

## cli rm

```sh
coffer cli rm [OPTIONS] COMMAND
```

Remove a tool you added by hand. A skill that requires it keeps it listed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | A tool you added, e.g. jq |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## cli show

```sh
coffer cli show [OPTIONS] COMMAND [SUBCOMMAND]...
```

Show one command-line tool: where it is, its version, login state and its interface — the options and subcommands its own --help lists.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | The command, e.g. gh |
| `[SUBCOMMAND]...` | argument | text (variadic) |  | Show one subcommand |
| `--tree` | option | flag |  | Every command of the tool, one per line |
| `--refresh` | option | flag |  | Read the tool's help again |
| `--json` | option | flag |  | JSON output for scripts |

## cli check

```sh
coffer cli check [OPTIONS] [COMMAND]
```

Probe the required commands again (or one of them).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `[COMMAND]` | argument | text |  | One command only |
| `--json` | option | flag |  | JSON output for scripts |

## cli prompt

```sh
coffer cli prompt [OPTIONS] COMMAND
```

Print the prompt to give your agent for a command that needs you.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | The command, e.g. jq |
| `--json` | option | flag |  | JSON output for scripts |
