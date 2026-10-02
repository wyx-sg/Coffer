---
title: coffer agent
description: "Manage registered AI agents"
---

# coffer agent

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer agent [OPTIONS] COMMAND [ARGS]...
```

Manage registered AI agents

## agent list

```sh
coffer agent list [OPTIONS]
```

List registered agents.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## agent add

```sh
coffer agent add [OPTIONS] TYPE
```

Register the agent of TYPE — one per type, named by it.

Without ``--config-dir`` it is registered at the type's standard directory; an agent installed but never run gets that directory created. To move a registered agent, use ``coffer agent edit NAME --config-dir``.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TYPE` | argument | text | required | claude-code \| codex |
| `--config-dir` | option | text |  | Config directory other than the standard one (~/.claude etc.). |

## agent show

```sh
coffer agent show [OPTIONS] NAME
```

Show one agent, with its Coffer connection part by part.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name (claude-code \| codex) or uid |
| `--json` | option | flag |  | JSON output for scripts |

## agent prompt

```sh
coffer agent prompt [OPTIONS] TYPE
```

Print the prompt to give your agent to install TYPE's program.

Offered while the program is not found, added or not — the same words the Agents page copies (spec agent-registry "Hand installing an agent's program to an agent").

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TYPE` | argument | text | required | claude-code \| codex |
| `--json` | option | flag |  | JSON output for scripts |

## agent edit

```sh
coffer agent edit [OPTIONS] NAME
```

Change an agent's config directory or model binding.

An agent's name is its type and it carries no title or description, so these are the whole of what can change. The model binding lives on the agent, not on the connection: an unbound agent projects no model and runs on its own default. A change here takes effect on disk the next time that agent is switched onto its connection (`coffer provider switch <name> --agent <type>`), which is what re-projects the config.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name (claude-code \| codex) or uid |
| `--config-dir` | option | text |  | Use a different config directory |
| `--model` | option | text |  | Model this agent answers with |
| `--effort` | option | text |  | Reasoning effort level |
| `--clear-effort` | option | flag |  | Unbind the effort |
| `--tier` | option | text (repeatable) |  | Claude Code tier pin &lt;tier&gt;=&lt;model&gt; (opus, sonnet, haiku, fable); repeatable |
| `--clear-tiers` | option | flag |  | Unbind every tier pin |

## agent rm

```sh
coffer agent rm [OPTIONS] NAME
```

Remove an agent (re-discoverable by `coffer scan` — removal isn't permanent).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## agent enable

```sh
coffer agent enable [OPTIONS] NAME
```

Switch an agent back on: Coffer writes into and reads from it again.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## agent disable

```sh
coffer agent disable [OPTIONS] NAME
```

Switch an agent off: its delivered skills are reclaimed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## agent connect

```sh
coffer agent connect [OPTIONS] NAME
```

Connect this agent to Coffer: install every part that applies to it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |

## agent disconnect

```sh
coffer agent disconnect [OPTIONS] NAME
```

Disconnect this agent from Coffer: remove every part Coffer wrote into it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |

## agent transcript

```sh
coffer agent transcript [OPTIONS] NAME [ID]
```

List this agent's conversations on this machine, or print one of them.

The listing pages by cursor: a page with more after it ends with the --cursor value that reads the next one. With an ID, what comes back is a window — --limit turns from --offset, each cut at the server's per-turn cap and secret-scrubbed — and the header says how many turns the whole session holds.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `[ID]` | argument | text |  | A session id from the listing; omit to list sessions |
| `--limit` | option | integer |  | Sessions to list (default 20) or turns to show (default 200) |
| `--offset` | option | integer | `0` | With an ID: skip this many turns. |
| `--cursor` | option | text |  | Listing: read the page after the one that printed this cursor. |
| `--query, -q` | option | text |  | Search title or project path. |
| `--project` | option | text |  | Only this exact project path. |
| `--sort` | option | text |  | started_at \| last_activity_at (default) \| message_count |
| `--order` | option | text |  | asc \| desc (default) |
| `--json` | option | flag |  | JSON output for scripts |

## agent models

```sh
coffer agent models [OPTIONS] TYPE
```

List the models a picker offers for this agent, with their effort levels.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TYPE` | argument | text | required | Agent type, e.g. claude_code or codex |
| `--json` | option | flag |  | JSON output |

## agent hooks

```sh
coffer agent hooks [OPTIONS] NAME
```

List every hook the agent will run; Coffer's own is marked with \*.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `--json` | option | flag |  | JSON output |

## agent config

```sh
coffer agent config [OPTIONS] COMMAND [ARGS]...
```

Write and delete an agent's config files (read them via `coffer path`)

Subcommands: `edit`, `rm`.

## agent config edit

```sh
coffer agent config edit [OPTIONS] NAME KEY[/CHILD]
```

Edit one config file, or one file inside a directory entry.

Opens $EDITOR on the current content, or takes it from --from-file. Coffer validates the content against the file's format (malformed JSON/TOML is rejected, exit 2, and the file is left unchanged), writes it atomically and keeps a `<path>.bak` of the prior version. A change made on disk since the read is refused (exit 5) instead of overwritten.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `KEY[/CHILD]` | argument | text | required | Config-file key (e.g. settings, config, instructions), or KEY/CHILD for one file inside a directory entry (e.g. subagents/reviewer.md) |
| `--from-file` | option | text |  | Take the new content from PATH ('-' for stdin) instead of opening $EDITOR. |

## agent config rm

```sh
coffer agent config rm [OPTIONS] NAME KEY/CHILD
```

Delete one file inside a directory entry (its content is kept as .bak).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `KEY/CHILD` | argument | text | required | One file inside a directory entry (e.g. subagents/x.md) |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## agent plugin

```sh
coffer agent plugin [OPTIONS] COMMAND [ARGS]...
```

View and manage an agent's installed plugins

Subcommands: `list`, `show`, `enable`, `disable`, `rm`.

## agent plugin list

```sh
coffer agent plugin list [OPTIONS] NAME
```

List the agent's installed plugins and known marketplaces.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `--json` | option | flag |  | JSON output for scripts |

## agent plugin show

```sh
coffer agent plugin show [OPTIONS] NAME PLUGIN_ID
```

Show one plugin: its metadata, install dir and everything it contributes.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `PLUGIN_ID` | argument | text | required | Plugin id (name@marketplace) |
| `--json` | option | flag |  | JSON output |

## agent plugin enable

```sh
coffer agent plugin enable [OPTIONS] NAME PLUGIN_ID
```

Enable a plugin in the agent's config.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `PLUGIN_ID` | argument | text | required | Plugin id (name@marketplace) |

## agent plugin disable

```sh
coffer agent plugin disable [OPTIONS] NAME PLUGIN_ID
```

Disable a plugin in the agent's config.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `PLUGIN_ID` | argument | text | required | Plugin id (name@marketplace) |

## agent plugin rm

```sh
coffer agent plugin rm [OPTIONS] NAME PLUGIN_ID
```

Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Agent name or uid |
| `PLUGIN_ID` | argument | text | required | Plugin id (name@marketplace) |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |
