---
title: coffer agent
description: "Manage registered AI agents"
---

# coffer agent

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer agent [OPTIONS] COMMAND [ARGS]...
```

Manage registered AI agents

## agent list

```sh
coffer agent list [OPTIONS]
```

List registered agents.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## agent add

```sh
coffer agent add [OPTIONS] TYPE
```

Register the agent of TYPE — one per type, named by it.

Without ``--config-dir`` it is registered at the type's standard directory; an agent installed but never run gets that directory created. To move a registered agent, use ``coffer agent edit NAME --config-dir``.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | claude-code \| codex |
| `--config-dir` | 选项 | text |  | Config directory other than the standard one (~/.claude etc.). |

## agent show

```sh
coffer agent show [OPTIONS] NAME
```

Show one agent, with its Coffer connection part by part.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name (claude-code \| codex) or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## agent prompt

```sh
coffer agent prompt [OPTIONS] TYPE
```

Print the prompt to give your agent to install TYPE's program.

Offered while the program is not found, added or not — the same words the Agents page copies (spec agent-registry "Hand installing an agent's program to an agent").

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | claude-code \| codex |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## agent edit

```sh
coffer agent edit [OPTIONS] NAME
```

Change an agent's config directory or model binding.

An agent's name is its type and it carries no title or description, so these are the whole of what can change. The model binding lives on the agent, not on the connection: an unbound agent projects no model and runs on its own default. A change here takes effect on disk the next time that agent is switched onto its connection (`coffer provider switch <name> --agent <type>`), which is what re-projects the config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name (claude-code \| codex) or uid |
| `--config-dir` | 选项 | text |  | Use a different config directory |
| `--model` | 选项 | text |  | Model this agent answers with |
| `--effort` | 选项 | text |  | Reasoning effort level |
| `--clear-effort` | 选项 | 开关 |  | Unbind the effort |
| `--tier` | 选项 | text（可重复） |  | Claude Code tier pin &lt;tier&gt;=&lt;model&gt; (opus, sonnet, haiku, fable); repeatable |
| `--clear-tiers` | 选项 | 开关 |  | Unbind every tier pin |

## agent rm

```sh
coffer agent rm [OPTIONS] NAME
```

Remove an agent (re-discoverable by `coffer scan` — removal isn't permanent).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## agent enable

```sh
coffer agent enable [OPTIONS] NAME
```

Switch an agent back on: Coffer writes into and reads from it again.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## agent disable

```sh
coffer agent disable [OPTIONS] NAME
```

Switch an agent off: its delivered skills are reclaimed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## agent connect

```sh
coffer agent connect [OPTIONS] NAME
```

Connect this agent to Coffer: install every part that applies to it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |

## agent disconnect

```sh
coffer agent disconnect [OPTIONS] NAME
```

Disconnect this agent from Coffer: remove every part Coffer wrote into it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |

## agent transcript

```sh
coffer agent transcript [OPTIONS] NAME [ID]
```

List this agent's conversations on this machine, or print one of them.

The listing pages by cursor: a page with more after it ends with the --cursor value that reads the next one. With an ID, what comes back is a window — --limit turns from --offset, each cut at the server's per-turn cap and secret-scrubbed — and the header says how many turns the whole session holds.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `[ID]` | 参数 | text |  | A session id from the listing; omit to list sessions |
| `--limit` | 选项 | integer |  | Sessions to list (default 20) or turns to show (default 200) |
| `--offset` | 选项 | integer | `0` | With an ID: skip this many turns. |
| `--cursor` | 选项 | text |  | Listing: read the page after the one that printed this cursor. |
| `--query, -q` | 选项 | text |  | Search title or project path. |
| `--project` | 选项 | text |  | Only this exact project path. |
| `--sort` | 选项 | text |  | started_at \| last_activity_at (default) \| message_count |
| `--order` | 选项 | text |  | asc \| desc (default) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## agent models

```sh
coffer agent models [OPTIONS] TYPE
```

List the models a picker offers for this agent, with their effort levels.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TYPE` | 参数 | text | 必填 | Agent type, e.g. claude_code or codex |
| `--json` | 选项 | 开关 |  | JSON output |

## agent hooks

```sh
coffer agent hooks [OPTIONS] NAME
```

List every hook the agent will run; Coffer's own is marked with \*.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `--json` | 选项 | 开关 |  | JSON output |

## agent config

```sh
coffer agent config [OPTIONS] COMMAND [ARGS]...
```

Write and delete an agent's config files (read them via `coffer path`)

子命令：`edit`, `rm`。

## agent config edit

```sh
coffer agent config edit [OPTIONS] NAME KEY[/CHILD]
```

Edit one config file, or one file inside a directory entry.

Opens $EDITOR on the current content, or takes it from --from-file. Coffer validates the content against the file's format (malformed JSON/TOML is rejected, exit 2, and the file is left unchanged), writes it atomically and keeps a `<path>.bak` of the prior version. A change made on disk since the read is refused (exit 5) instead of overwritten.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `KEY[/CHILD]` | 参数 | text | 必填 | Config-file key (e.g. settings, config, instructions), or KEY/CHILD for one file inside a directory entry (e.g. subagents/reviewer.md) |
| `--from-file` | 选项 | text |  | Take the new content from PATH ('-' for stdin) instead of opening $EDITOR. |

## agent config rm

```sh
coffer agent config rm [OPTIONS] NAME KEY/CHILD
```

Delete one file inside a directory entry (its content is kept as .bak).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `KEY/CHILD` | 参数 | text | 必填 | One file inside a directory entry (e.g. subagents/x.md) |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## agent plugin

```sh
coffer agent plugin [OPTIONS] COMMAND [ARGS]...
```

View and manage an agent's installed plugins

子命令：`list`, `show`, `enable`, `disable`, `rm`。

## agent plugin list

```sh
coffer agent plugin list [OPTIONS] NAME
```

List the agent's installed plugins and known marketplaces.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## agent plugin show

```sh
coffer agent plugin show [OPTIONS] NAME PLUGIN_ID
```

Show one plugin: its metadata, install dir and everything it contributes.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |
| `--json` | 选项 | 开关 |  | JSON output |

## agent plugin enable

```sh
coffer agent plugin enable [OPTIONS] NAME PLUGIN_ID
```

Enable a plugin in the agent's config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |

## agent plugin disable

```sh
coffer agent plugin disable [OPTIONS] NAME PLUGIN_ID
```

Disable a plugin in the agent's config.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |

## agent plugin rm

```sh
coffer agent plugin rm [OPTIONS] NAME PLUGIN_ID
```

Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Agent name or uid |
| `PLUGIN_ID` | 参数 | text | 必填 | Plugin id (name@marketplace) |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |
