---
title: coffer skill
description: "Skills: import, update, delivery to agents, sources."
pageClass: cli-ref
---

# coffer skill

Skills: import, update, delivery to agents, sources.

```sh
coffer skill [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer skill --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`skill update`](#skill-update) | Change a skill. |
| [`skill enable`](#skill-enable) | Switch a skill on. |
| [`skill disable`](#skill-disable) | Switch a skill off. |
| [`skill reach`](#skill-reach) | Set the agents a skill reaches. |
| [`skill list`](#skill-list) | Every skill with its delivery and source state. |
| [`skill show`](#skill-show) | One skill: its master path, requirements, delivery and source. |
| [`skill files`](#skill-files) | The skill's files and its master path (edit them with your own tools). |
| [`skill delete`](#skill-delete) | Delete a skill and its copies in agents. |
| [`skill delete-many`](#skill-delete-many) | Delete several skills. |
| [`skill verify`](#skill-verify) | Check every skill's delivery to the agents it reaches. |
| [`skill repair`](#skill-repair) | Rewrite every delivery that drifted. |
| [`skill conformance-handoff`](#skill-conformance-handoff) | The prompt that hands fixing skills' format to an agent. |
| [`skill stage-folder`](#skill-stage-folder) | Stage skills from a folder on this machine. |
| [`skill stage-git`](#skill-stage-git) | Stage skills from a git repository. |
| [`skill stage-confirm`](#skill-stage-confirm) | Import staged skills. |
| [`skill stage-cancel`](#skill-stage-cancel) | Drop a staged import. |
| [`skill stage-archive`](#skill-stage-archive) | Stage skills from an archive file; confirm with ``skill stage-confirm``. |
| [`skill copy`](#skill-copy) | An agent's copy of a skill that differs from the master. |
| [`skill copy compare`](#skill-copy-compare) | How an agent's copy differs from the master. |
| [`skill copy resolve`](#skill-copy-resolve) | Keep the master or the agent's copy. |
| [`skill orphan`](#skill-orphan) | Folders in the skills store that no skill owns. |
| [`skill orphan list`](#skill-orphan-list) | Folders in the skills store that no skill owns. |
| [`skill orphan files`](#skill-orphan-files) | An orphan folder's files. |
| [`skill orphan adopt`](#skill-orphan-adopt) | Register an orphan folder as a skill. |
| [`skill orphan remove`](#skill-orphan-remove) | Delete an orphan folder. |
| [`skill source`](#skill-source) | Where a skill came from: check, change, merge updates. |
| [`skill source check`](#skill-source-check) | Ask the skill's source for a newer version. |
| [`skill source change`](#skill-source-change) | Stage the skill from another source. |
| [`skill source change-apply`](#skill-source-change-apply) | Apply a staged change of source. |
| [`skill source handoff`](#skill-source-handoff) | The prompt that hands merging an upstream update to an agent. |
| [`skill source merged`](#skill-source-merged) | Record that the upstream update was merged. |
| [`skill update-check`](#skill-update-check) | How often skills' sources are checked for updates. |
| [`skill update-check show`](#skill-update-check-show) | How often skills' sources are checked. |
| [`skill update-check set`](#skill-update-check-set) | Set how often skills' sources are checked. |

## skill update

Change a skill. Body: name, title, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer skill update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill enable

Switch a skill on.

<p class="cli-label">Synopsis</p>

```sh
coffer skill enable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill disable

Switch a skill off.

<p class="cli-label">Synopsis</p>

```sh
coffer skill disable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill reach

Set the agents a skill reaches. Body: scope ({agents: [uid…]} or null).

<p class="cli-label">Synopsis</p>

```sh
coffer skill reach [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill list

Every skill with its delivery and source state.

<p class="cli-label">Synopsis</p>

```sh
coffer skill list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill show

One skill: its master path, requirements, delivery and source.

<p class="cli-label">Synopsis</p>

```sh
coffer skill show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill files

The skill's files and its master path (edit them with your own tools).

<p class="cli-label">Synopsis</p>

```sh
coffer skill files [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill delete

Delete a skill and its copies in agents.

<p class="cli-label">Synopsis</p>

```sh
coffer skill delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--keep-foreign-copies` <span class="cli-chip">option</span> | flag |  | Keep copies Coffer did not write |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill delete-many

Delete several skills. Body: uids, keep_foreign_copies.

<p class="cli-label">Synopsis</p>

```sh
coffer skill delete-many [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill verify

Check every skill's delivery to the agents it reaches.

<p class="cli-label">Synopsis</p>

```sh
coffer skill verify [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill repair

Rewrite every delivery that drifted.

<p class="cli-label">Synopsis</p>

```sh
coffer skill repair [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill conformance-handoff

The prompt that hands fixing skills' format to an agent. Body: uids.

<p class="cli-label">Synopsis</p>

```sh
coffer skill conformance-handoff [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill stage-folder

Stage skills from a folder on this machine. Body: path.

<p class="cli-label">Synopsis</p>

```sh
coffer skill stage-folder [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill stage-git

Stage skills from a git repository. Body: url, ref, path.

<p class="cli-label">Synopsis</p>

```sh
coffer skill stage-git [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill stage-confirm

Import staged skills. Body: skills, replace.

<p class="cli-label">Synopsis</p>

```sh
coffer skill stage-confirm [OPTIONS] STAGING_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `STAGING_ID` <span class="cli-chip">argument</span> | text | required | staging id |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill stage-cancel

Drop a staged import.

<p class="cli-label">Synopsis</p>

```sh
coffer skill stage-cancel [OPTIONS] STAGING_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `STAGING_ID` <span class="cli-chip">argument</span> | text | required | staging id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill stage-archive

Stage skills from an archive file; confirm with ``skill stage-confirm``.

<p class="cli-label">Synopsis</p>

```sh
coffer skill stage-archive [OPTIONS] ARCHIVE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `ARCHIVE` <span class="cli-chip">argument</span> | path | required | A .zip or .tar.gz of one or more skills |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill copy

An agent's copy of a skill that differs from the master.

<p class="cli-label">Synopsis</p>

```sh
coffer skill copy [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `compare`, `resolve`.

## skill copy compare

How an agent's copy differs from the master.

<p class="cli-label">Synopsis</p>

```sh
coffer skill copy compare [OPTIONS] UID AGENT_UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `AGENT_UID` <span class="cli-chip">argument</span> | text | required | agent uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill copy resolve

Keep the master or the agent's copy. Body: keep (master | copy).

<p class="cli-label">Synopsis</p>

```sh
coffer skill copy resolve [OPTIONS] UID AGENT_UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `AGENT_UID` <span class="cli-chip">argument</span> | text | required | agent uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill orphan

Folders in the skills store that no skill owns.

<p class="cli-label">Synopsis</p>

```sh
coffer skill orphan [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `files`, `adopt`, `remove`.

## skill orphan list

Folders in the skills store that no skill owns.

<p class="cli-label">Synopsis</p>

```sh
coffer skill orphan list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill orphan files

An orphan folder's files.

<p class="cli-label">Synopsis</p>

```sh
coffer skill orphan files [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | name |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill orphan adopt

Register an orphan folder as a skill.

<p class="cli-label">Synopsis</p>

```sh
coffer skill orphan adopt [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | name |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill orphan remove

Delete an orphan folder.

<p class="cli-label">Synopsis</p>

```sh
coffer skill orphan remove [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | name |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill source

Where a skill came from: check, change, merge updates.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `check`, `change`, `change-apply`, `handoff`, `merged`.

## skill source check

Ask the skill's source for a newer version.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source check [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill source change

Stage the skill from another source. Body: url, ref, path.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source change [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill source change-apply

Apply a staged change of source. Body: staging_id.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source change-apply [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill source handoff

The prompt that hands merging an upstream update to an agent.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source handoff [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill source merged

Record that the upstream update was merged. Body: commit.

<p class="cli-label">Synopsis</p>

```sh
coffer skill source merged [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The skill's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill update-check

How often skills' sources are checked for updates.

<p class="cli-label">Synopsis</p>

```sh
coffer skill update-check [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `set`.

## skill update-check show

How often skills' sources are checked.

<p class="cli-label">Synopsis</p>

```sh
coffer skill update-check show [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## skill update-check set

Set how often skills' sources are checked. Body: interval.

<p class="cli-label">Synopsis</p>

```sh
coffer skill update-check set [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
