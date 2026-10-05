---
title: coffer conversation
description: "Conversations: rename, stop a turn, delete (list: agent session all)."
pageClass: cli-ref
---

# coffer conversation

Conversations: rename, stop a turn, delete (list: agent session all).

```sh
coffer conversation [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer conversation --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`conversation rename`](#conversation-rename) | Rename a conversation. |
| [`conversation interrupt`](#conversation-interrupt) | Stop the turn in progress. |
| [`conversation delete`](#conversation-delete) | Delete a conversation. |

## conversation rename

Rename a conversation. Body: title.

<p class="cli-label">Synopsis</p>

```sh
coffer conversation rename [OPTIONS] ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">argument</span> | text | required | id |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## conversation interrupt

Stop the turn in progress.

<p class="cli-label">Synopsis</p>

```sh
coffer conversation interrupt [OPTIONS] ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">argument</span> | text | required | id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## conversation delete

Delete a conversation.

<p class="cli-label">Synopsis</p>

```sh
coffer conversation delete [OPTIONS] ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">argument</span> | text | required | id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
