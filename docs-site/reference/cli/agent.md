---
title: coffer agent
description: "Manage coding agents: add, connect, their MCP entries, plugins and sessions."
pageClass: cli-ref
---

# coffer agent

Manage coding agents: add, connect, their MCP entries, plugins and sessions.

```sh
coffer agent [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer agent --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`agent list`](#agent-list) | Registered agents. |
| [`agent types`](#agent-types) | Every supported agent type, found or not, and whether it can be added. |
| [`agent show`](#agent-show) | One agent. |
| [`agent add`](#agent-add) | Register an agent. |
| [`agent update`](#agent-update) | Change an agent. |
| [`agent connect`](#agent-connect) | Write Coffer's MCP entry, hooks and skills into the agent. |
| [`agent disconnect`](#agent-disconnect) | Remove what Coffer wrote into the agent. |
| [`agent connection`](#agent-connection) | Each part of the connection and its state. |
| [`agent config-files`](#agent-config-files) | The agent's config files and their paths (read them with your own tools). |
| [`agent hooks`](#agent-hooks) | The hooks in the agent's config. |
| [`agent models`](#agent-models) | The models an agent type can be switched to. |
| [`agent providers`](#agent-providers) | Each agent type's model catalogue source. |
| [`agent mcp-entry`](#agent-mcp-entry) | An agent's own MCP entries: list, show, adopt into Coffer, remove. |
| [`agent mcp-entry list`](#agent-mcp-entry-list) | The agent's own MCP entries. |
| [`agent mcp-entry show`](#agent-mcp-entry-show) | One entry (secret values never shown). |
| [`agent mcp-entry remove`](#agent-mcp-entry-remove) | Remove an entry from the agent's config. |
| [`agent mcp-entry adopt`](#agent-mcp-entry-adopt) | Register an entry as a Coffer MCP server. |
| [`agent mcp-import`](#agent-mcp-import) | Import MCP servers found in agents' configs into Coffer. |
| [`agent mcp-import plan`](#agent-mcp-import-plan) | What importing these entries would register. |
| [`agent mcp-import apply`](#agent-mcp-import-apply) | Register the entries as Coffer MCP servers. |
| [`agent plugin`](#agent-plugin) | An agent's plugins: list, show, switch on or off, uninstall. |
| [`agent plugin list`](#agent-plugin-list) | The agent's plugins. |
| [`agent plugin show`](#agent-plugin-show) | One plugin and what it brings. |
| [`agent plugin set`](#agent-plugin-set) | Switch a plugin on or off. |
| [`agent plugin uninstall`](#agent-plugin-uninstall) | Uninstall a plugin with the agent's own CLI. |
| [`agent session`](#agent-session) | An agent's native sessions: list, rename, delete. |
| [`agent session list`](#agent-session-list) | The agent's native sessions, newest first. |
| [`agent session all`](#agent-session-all) | Every agent's sessions in one list. |
| [`agent session rename`](#agent-session-rename) | Rename a session. |
| [`agent session delete`](#agent-session-delete) | Delete a session from the agent's store. |
| [`agent unmanaged-skill`](#agent-unmanaged-skill) | Skills an agent holds that Coffer does not manage. |
| [`agent unmanaged-skill list`](#agent-unmanaged-skill-list) | Skills in the agent Coffer does not manage. |
| [`agent unmanaged-skill show`](#agent-unmanaged-skill-show) | One unmanaged skill. |
| [`agent unmanaged-skill files`](#agent-unmanaged-skill-files) | The skill's files (read them with your own tools). |
| [`agent unmanaged-skill adopt`](#agent-unmanaged-skill-adopt) | Make Coffer manage the skill. |
| [`agent unmanaged-skill delete`](#agent-unmanaged-skill-delete) | Delete an unmanaged skill from the agent. |
| [`agent native-memory`](#agent-native-memory) | What an agent keeps in its own memory files (read-only). |
| [`agent native-memory list`](#agent-native-memory-list) | What the agent keeps in its own memory. |
| [`agent native-memory files`](#agent-native-memory-files) | The memory files and their paths. |

## agent list

Registered agents.

<p class="cli-label">Synopsis</p>

```sh
coffer agent list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent types

Every supported agent type, found or not, and whether it can be added.

<p class="cli-label">Synopsis</p>

```sh
coffer agent types [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent show

One agent.

<p class="cli-label">Synopsis</p>

```sh
coffer agent show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent add

Register an agent. Body: type (claude-code | codex), config_dir.

<p class="cli-label">Synopsis</p>

```sh
coffer agent add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent update

Change an agent. Body: config_dir, model, tier_models.

<p class="cli-label">Synopsis</p>

```sh
coffer agent update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent connect

Write Coffer's MCP entry, hooks and skills into the agent.

<p class="cli-label">Synopsis</p>

```sh
coffer agent connect [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent disconnect

Remove what Coffer wrote into the agent.

<p class="cli-label">Synopsis</p>

```sh
coffer agent disconnect [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent connection

Each part of the connection and its state.

<p class="cli-label">Synopsis</p>

```sh
coffer agent connection [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent config-files

The agent's config files and their paths (read them with your own tools).

<p class="cli-label">Synopsis</p>

```sh
coffer agent config-files [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent hooks

The hooks in the agent's config.

<p class="cli-label">Synopsis</p>

```sh
coffer agent hooks [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent models

The models an agent type can be switched to.

<p class="cli-label">Synopsis</p>

```sh
coffer agent models [OPTIONS] AGENT_KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT_KEY` <span class="cli-chip">argument</span> | text | required | The agent type (claude-code, codex) |
| `--source` <span class="cli-chip">option</span> | text |  | Where the list comes from |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent providers

Each agent type's model catalogue source.

<p class="cli-label">Synopsis</p>

```sh
coffer agent providers [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-entry

An agent's own MCP entries: list, show, adopt into Coffer, remove.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-entry [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `show`, `remove`, `adopt`.

## agent mcp-entry list

The agent's own MCP entries.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-entry list [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-entry show

One entry (secret values never shown).

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-entry show [OPTIONS] UID ENTRY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `ENTRY` <span class="cli-chip">argument</span> | text | required | entry |
| `--source` <span class="cli-chip">option</span> | text |  | The config file the entry is in |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-entry remove

Remove an entry from the agent's config.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-entry remove [OPTIONS] UID ENTRY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `ENTRY` <span class="cli-chip">argument</span> | text | required | entry |
| `--source` <span class="cli-chip">option</span> | text |  | The config file the entry is in |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-entry adopt

Register an entry as a Coffer MCP server. Body: new_name, secrets, source.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-entry adopt [OPTIONS] UID ENTRY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `ENTRY` <span class="cli-chip">argument</span> | text | required | entry |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-import

Import MCP servers found in agents' configs into Coffer.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-import [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `plan`, `apply`.

## agent mcp-import plan

What importing these entries would register. Body: entries[{agent_uid, name, source, new_name}].

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-import plan [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent mcp-import apply

Register the entries as Coffer MCP servers. Body as for plan.

<p class="cli-label">Synopsis</p>

```sh
coffer agent mcp-import apply [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent plugin

An agent's plugins: list, show, switch on or off, uninstall.

<p class="cli-label">Synopsis</p>

```sh
coffer agent plugin [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `show`, `set`, `uninstall`.

## agent plugin list

The agent's plugins.

<p class="cli-label">Synopsis</p>

```sh
coffer agent plugin list [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent plugin show

One plugin and what it brings.

<p class="cli-label">Synopsis</p>

```sh
coffer agent plugin show [OPTIONS] UID PLUGIN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `PLUGIN_ID` <span class="cli-chip">argument</span> | text | required | plugin id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent plugin set

Switch a plugin on or off. Body: enabled (--set enabled=false).

<p class="cli-label">Synopsis</p>

```sh
coffer agent plugin set [OPTIONS] UID PLUGIN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `PLUGIN_ID` <span class="cli-chip">argument</span> | text | required | plugin id |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent plugin uninstall

Uninstall a plugin with the agent's own CLI.

<p class="cli-label">Synopsis</p>

```sh
coffer agent plugin uninstall [OPTIONS] UID PLUGIN_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `PLUGIN_ID` <span class="cli-chip">argument</span> | text | required | plugin id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent session

An agent's native sessions: list, rename, delete.

<p class="cli-label">Synopsis</p>

```sh
coffer agent session [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `all`, `rename`, `delete`.

## agent session list

The agent's native sessions, newest first.

<p class="cli-label">Synopsis</p>

```sh
coffer agent session list [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--q` <span class="cli-chip">option</span> | text |  | Text to search for |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--cursor` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent session all

Every agent's sessions in one list.

<p class="cli-label">Synopsis</p>

```sh
coffer agent session all [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--q` <span class="cli-chip">option</span> | text |  |  |
| `--source` <span class="cli-chip">option</span> | text |  |  |
| `--agent` <span class="cli-chip">option</span> | text |  | An agent uid |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--cursor` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent session rename

Rename a session. Body: title.

<p class="cli-label">Synopsis</p>

```sh
coffer agent session rename [OPTIONS] UID SESSION_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SESSION_ID` <span class="cli-chip">argument</span> | text | required | session id |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent session delete

Delete a session from the agent's store.

<p class="cli-label">Synopsis</p>

```sh
coffer agent session delete [OPTIONS] UID SESSION_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SESSION_ID` <span class="cli-chip">argument</span> | text | required | session id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent unmanaged-skill

Skills an agent holds that Coffer does not manage.

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `show`, `files`, `adopt`, `delete`.

## agent unmanaged-skill list

Skills in the agent Coffer does not manage.

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill list [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent unmanaged-skill show

One unmanaged skill.

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill show [OPTIONS] UID SKILL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SKILL` <span class="cli-chip">argument</span> | text | required | skill |
| `--location` <span class="cli-chip">option</span> | text |  | Where the skill sits |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent unmanaged-skill files

The skill's files (read them with your own tools).

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill files [OPTIONS] UID SKILL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SKILL` <span class="cli-chip">argument</span> | text | required | skill |
| `--location` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent unmanaged-skill adopt

Make Coffer manage the skill. Body: location, name, reach.

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill adopt [OPTIONS] UID SKILL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SKILL` <span class="cli-chip">argument</span> | text | required | skill |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent unmanaged-skill delete

Delete an unmanaged skill from the agent.

<p class="cli-label">Synopsis</p>

```sh
coffer agent unmanaged-skill delete [OPTIONS] UID SKILL
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `SKILL` <span class="cli-chip">argument</span> | text | required | skill |
| `--location` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent native-memory

What an agent keeps in its own memory files (read-only).

<p class="cli-label">Synopsis</p>

```sh
coffer agent native-memory [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `files`.

## agent native-memory list

What the agent keeps in its own memory.

<p class="cli-label">Synopsis</p>

```sh
coffer agent native-memory list [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## agent native-memory files

The memory files and their paths.

<p class="cli-label">Synopsis</p>

```sh
coffer agent native-memory files [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The agent's name or uid |
| `--dir` <span class="cli-chip">option</span> | text |  | A folder under the agent's memory |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
