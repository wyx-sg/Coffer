---
title: coffer agent
description: "Manage registered AI agents"
pageClass: cli-ref
---

# coffer agent

Manage registered AI agents

```sh
coffer agent [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer agent --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`agent list`](#agent-list) | List registered agents. |
| [`agent add`](#agent-add) | Register the agent of TYPE — one per type, named by it. |
| [`agent show`](#agent-show) | Show one agent, with its Coffer connection part by part. |
| [`agent prompt`](#agent-prompt) | Print the prompt to give your agent to install TYPE's program. |
| [`agent edit`](#agent-edit) | Change an agent's config directory or model binding. |
| [`agent rm`](#agent-rm) | Remove an agent (re-discoverable by `coffer scan` — removal isn't permanent). |
| [`agent enable`](#agent-enable) | Switch an agent back on: Coffer writes into and reads from it again. |
| [`agent disable`](#agent-disable) | Switch an agent off: its delivered skills are reclaimed. |
| [`agent connect`](#agent-connect) | Connect this agent to Coffer: install every part that applies to it. |
| [`agent disconnect`](#agent-disconnect) | Disconnect this agent from Coffer: remove every part Coffer wrote into it. |
| [`agent transcript`](#agent-transcript) | List this agent's conversations on this machine, or print one of them. |
| [`agent models`](#agent-models) | List the models a picker offers for this agent, with their effort levels. |
| [`agent hooks`](#agent-hooks) | List every hook the agent will run; Coffer's own is marked with \*. |
| [`agent config`](#agent-config) | Write and delete an agent's config files (read them via `coffer path`) |
| [`agent config edit`](#agent-config-edit) | Edit one config file, or one file inside a directory entry. |
| [`agent config rm`](#agent-config-rm) | Delete one file inside a directory entry (its content is kept as .bak). |
| [`agent plugin`](#agent-plugin) | View and manage an agent's installed plugins |
| [`agent plugin list`](#agent-plugin-list) | List the agent's installed plugins and known marketplaces. |
| [`agent plugin show`](#agent-plugin-show) | Show one plugin: its metadata, install dir and everything it contributes. |
| [`agent plugin enable`](#agent-plugin-enable) | Enable a plugin in the agent's config. |
| [`agent plugin disable`](#agent-plugin-disable) | Disable a plugin in the agent's config. |
| [`agent plugin rm`](#agent-plugin-rm) | Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI). |

## agent list

List registered agents.

<p class="cli-label">概要</p>

```sh
coffer agent list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## agent add

Register the agent of TYPE — one per type, named by it.

Without ``--config-dir`` it is registered at the type's standard directory; an agent installed but never run gets that directory created. To move a registered agent, use ``coffer agent edit NAME --config-dir``.

<p class="cli-label">概要</p>

```sh
coffer agent add [OPTIONS] TYPE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `TYPE` <span class="cli-chip">参数</span> | text | 必填 | claude-code \| codex |
| `--config-dir` <span class="cli-chip">选项</span> | text |  | Config directory other than the standard one (~/.claude etc.). |

## agent show

Show one agent, with its Coffer connection part by part.

<p class="cli-label">概要</p>

```sh
coffer agent show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name (claude-code \| codex) or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## agent prompt

Print the prompt to give your agent to install TYPE's program.

Offered while the program is not found, added or not — the same words the Agents page copies (spec agent-registry "Hand installing an agent's program to an agent").

<p class="cli-label">概要</p>

```sh
coffer agent prompt [OPTIONS] TYPE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `TYPE` <span class="cli-chip">参数</span> | text | 必填 | claude-code \| codex |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## agent edit

Change an agent's config directory or model binding.

An agent's name is its type and it carries no title or description, so these are the whole of what can change. The model binding lives on the agent, not on the connection: an unbound agent projects no model and runs on its own default. A change here takes effect on disk the next time that agent is switched onto its connection (`coffer provider switch <name> --agent <type>`), which is what re-projects the config.

<p class="cli-label">概要</p>

```sh
coffer agent edit [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name (claude-code \| codex) or uid |
| `--config-dir` <span class="cli-chip">选项</span> | text |  | Use a different config directory |
| `--model` <span class="cli-chip">选项</span> | text |  | Model this agent answers with |
| `--effort` <span class="cli-chip">选项</span> | text |  | Reasoning effort level |
| `--clear-effort` <span class="cli-chip">选项</span> | 开关 |  | Unbind the effort |
| `--tier` <span class="cli-chip">选项</span> | text（可重复） |  | Claude Code tier pin &lt;tier&gt;=&lt;model&gt; (opus, sonnet, haiku, fable); repeatable |
| `--clear-tiers` <span class="cli-chip">选项</span> | 开关 |  | Unbind every tier pin |

## agent rm

Remove an agent (re-discoverable by `coffer scan` — removal isn't permanent).

<p class="cli-label">概要</p>

```sh
coffer agent rm [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## agent enable

Switch an agent back on: Coffer writes into and reads from it again.

<p class="cli-label">概要</p>

```sh
coffer agent enable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## agent disable

Switch an agent off: its delivered skills are reclaimed.

<p class="cli-label">概要</p>

```sh
coffer agent disable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## agent connect

Connect this agent to Coffer: install every part that applies to it.

<p class="cli-label">概要</p>

```sh
coffer agent connect [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |

## agent disconnect

Disconnect this agent from Coffer: remove every part Coffer wrote into it.

<p class="cli-label">概要</p>

```sh
coffer agent disconnect [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |

## agent transcript

List this agent's conversations on this machine, or print one of them.

The listing pages by cursor: a page with more after it ends with the --cursor value that reads the next one. With an ID, what comes back is a window — --limit turns from --offset, each cut at the server's per-turn cap and secret-scrubbed — and the header says how many turns the whole session holds.

<p class="cli-label">概要</p>

```sh
coffer agent transcript [OPTIONS] NAME [ID]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `[ID]` <span class="cli-chip">参数</span> | text |  | A session id from the listing; omit to list sessions |
| `--limit` <span class="cli-chip">选项</span> | integer |  | Sessions to list (default 20) or turns to show (default 200) |
| `--offset` <span class="cli-chip">选项</span> | integer | `0` | With an ID: skip this many turns. |
| `--cursor` <span class="cli-chip">选项</span> | text |  | Listing: read the page after the one that printed this cursor. |
| `--query, -q` <span class="cli-chip">选项</span> | text |  | Search title or project path. |
| `--project` <span class="cli-chip">选项</span> | text |  | Only this exact project path. |
| `--sort` <span class="cli-chip">选项</span> | text |  | started_at \| last_activity_at (default) \| message_count |
| `--order` <span class="cli-chip">选项</span> | text |  | asc \| desc (default) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## agent models

List the models a picker offers for this agent, with their effort levels.

<p class="cli-label">概要</p>

```sh
coffer agent models [OPTIONS] TYPE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `TYPE` <span class="cli-chip">参数</span> | text | 必填 | Agent type, e.g. claude_code or codex |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output |

## agent hooks

List every hook the agent will run; Coffer's own is marked with \*.

<p class="cli-label">概要</p>

```sh
coffer agent hooks [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output |

## agent config

Write and delete an agent's config files (read them via `coffer path`)

<p class="cli-label">概要</p>

```sh
coffer agent config [OPTIONS] COMMAND [ARGS]...
```

子命令：`edit`, `rm`。

## agent config edit

Edit one config file, or one file inside a directory entry.

Opens $EDITOR on the current content, or takes it from --from-file. Coffer validates the content against the file's format (malformed JSON/TOML is rejected, exit 2, and the file is left unchanged), writes it atomically and keeps a `<path>.bak` of the prior version. A change made on disk since the read is refused (exit 5) instead of overwritten.

<p class="cli-label">概要</p>

```sh
coffer agent config edit [OPTIONS] NAME KEY[/CHILD]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `KEY[/CHILD]` <span class="cli-chip">参数</span> | text | 必填 | Config-file key (e.g. settings, config, instructions), or KEY/CHILD for one file inside a directory entry (e.g. subagents/reviewer.md) |
| `--from-file` <span class="cli-chip">选项</span> | text |  | Take the new content from PATH ('-' for stdin) instead of opening $EDITOR. |

## agent config rm

Delete one file inside a directory entry (its content is kept as .bak).

<p class="cli-label">概要</p>

```sh
coffer agent config rm [OPTIONS] NAME KEY/CHILD
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `KEY/CHILD` <span class="cli-chip">参数</span> | text | 必填 | One file inside a directory entry (e.g. subagents/x.md) |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## agent plugin

View and manage an agent's installed plugins

<p class="cli-label">概要</p>

```sh
coffer agent plugin [OPTIONS] COMMAND [ARGS]...
```

子命令：`list`, `show`, `enable`, `disable`, `rm`。

## agent plugin list

List the agent's installed plugins and known marketplaces.

<p class="cli-label">概要</p>

```sh
coffer agent plugin list [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## agent plugin show

Show one plugin: its metadata, install dir and everything it contributes.

<p class="cli-label">概要</p>

```sh
coffer agent plugin show [OPTIONS] NAME PLUGIN_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `PLUGIN_ID` <span class="cli-chip">参数</span> | text | 必填 | Plugin id (name@marketplace) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output |

## agent plugin enable

Enable a plugin in the agent's config.

<p class="cli-label">概要</p>

```sh
coffer agent plugin enable [OPTIONS] NAME PLUGIN_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `PLUGIN_ID` <span class="cli-chip">参数</span> | text | 必填 | Plugin id (name@marketplace) |

## agent plugin disable

Disable a plugin in the agent's config.

<p class="cli-label">概要</p>

```sh
coffer agent plugin disable [OPTIONS] NAME PLUGIN_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `PLUGIN_ID` <span class="cli-chip">参数</span> | text | 必填 | Plugin id (name@marketplace) |

## agent plugin rm

Uninstall a plugin (Codex edits its config; Claude Code shells out to its own CLI).

<p class="cli-label">概要</p>

```sh
coffer agent plugin rm [OPTIONS] NAME PLUGIN_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |
| `PLUGIN_ID` <span class="cli-chip">参数</span> | text | 必填 | Plugin id (name@marketplace) |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |
