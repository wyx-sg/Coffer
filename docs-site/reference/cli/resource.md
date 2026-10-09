---
title: coffer resource
description: "Any resource by uid: show, rename, switch on or off, reach, delete."
pageClass: cli-ref
---

# coffer resource

Any resource by uid: show, rename, switch on or off, reach, delete.

```sh
coffer resource [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer resource --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`resource list`](#resource-list) | Resources of every kind, or of one. |
| [`resource show`](#resource-show) | One resource by uid. |
| [`resource add`](#resource-add) | Register a resource. |
| [`resource update`](#resource-update) | Change a resource. |
| [`resource delete`](#resource-delete) | Delete a resource (the kind's cleanup runs first). |
| [`resource enable`](#resource-enable) | Switch a resource on. |
| [`resource disable`](#resource-disable) | Switch a resource off. |
| [`resource reach`](#resource-reach) | Which agents a resource reaches. |
| [`resource reach show`](#resource-reach-show) | Which agents a resource reaches. |
| [`resource reach set`](#resource-reach-set) | Set the agents a resource reaches. |

## resource list

Resources of every kind, or of one.

<p class="cli-label">Synopsis</p>

```sh
coffer resource list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--kind` <span class="cli-chip">option</span> | text |  | mcp_server, agent, skill, knowledge, memory, provider, channel |
| `--name` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource show

One resource by uid.

<p class="cli-label">Synopsis</p>

```sh
coffer resource show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource add

Register a resource. Body: kind, name, config, description.

<p class="cli-label">Synopsis</p>

```sh
coffer resource add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource update

Change a resource. Body: name, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer resource update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource delete

Delete a resource (the kind's cleanup runs first).

<p class="cli-label">Synopsis</p>

```sh
coffer resource delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource enable

Switch a resource on.

<p class="cli-label">Synopsis</p>

```sh
coffer resource enable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource disable

Switch a resource off.

<p class="cli-label">Synopsis</p>

```sh
coffer resource disable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource reach

Which agents a resource reaches.

<p class="cli-label">Synopsis</p>

```sh
coffer resource reach [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `show`, `set`.

## resource reach show

Which agents a resource reaches.

<p class="cli-label">Synopsis</p>

```sh
coffer resource reach show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource reach set

Set the agents a resource reaches. Body: scope ({agents: [uid…]} or null for every agent).

<p class="cli-label">Synopsis</p>

```sh
coffer resource reach set [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
