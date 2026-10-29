---
title: coffer task
description: "Scheduled tasks: list, add, run now, runs, pause, the daily report."
pageClass: cli-ref
---

# coffer task

Scheduled tasks: list, add, run now, runs, pause, the daily report.

```sh
coffer task [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer task --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`task update`](#task-update) | Change a task. |
| [`task delete`](#task-delete) | Delete a task. |
| [`task enable`](#task-enable) | Switch a task on. |
| [`task disable`](#task-disable) | Switch a task off. |
| [`task list`](#task-list) | Every scheduled task, with its next and last run. |
| [`task show`](#task-show) | One task: its config, next run and last run. |
| [`task add`](#task-add) | Add a scheduled task. |
| [`task chats`](#task-chats) | The paired chats a task may run in. |
| [`task run`](#task-run) | Run a task once, now, whatever its schedule. |
| [`task runs`](#task-runs) | A task's runs, newest first: when, and how each ended. |
| [`task daily-report`](#task-daily-report) | Set the daily report's time, made from its template the first time. |

## task update

Change a task. Body: name, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer task update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task delete

Delete a task.

<p class="cli-label">Synopsis</p>

```sh
coffer task delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task enable

Switch a task on.

<p class="cli-label">Synopsis</p>

```sh
coffer task enable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task disable

Switch a task off.

<p class="cli-label">Synopsis</p>

```sh
coffer task disable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task list

Every scheduled task, with its next and last run.

<p class="cli-label">Synopsis</p>

```sh
coffer task list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task show

One task: its config, next run and last run.

<p class="cli-label">Synopsis</p>

```sh
coffer task show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task add

Add a scheduled task. Body: name, description, config (schedule, prompt, chat {channel, chat_id}, session continue|fresh, agent, cwd, model).

<p class="cli-label">Synopsis</p>

```sh
coffer task add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task chats

The paired chats a task may run in.

<p class="cli-label">Synopsis</p>

```sh
coffer task chats [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task run

Run a task once, now, whatever its schedule.

<p class="cli-label">Synopsis</p>

```sh
coffer task run [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task runs

A task's runs, newest first: when, and how each ended.

<p class="cli-label">Synopsis</p>

```sh
coffer task runs [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The scheduled_task's name or uid |
| `--limit` <span class="cli-chip">option</span> | integer |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## task daily-report

Set the daily report's time, made from its template the first time. Body: channel, time (HH:MM), agent.

<p class="cli-label">Synopsis</p>

```sh
coffer task daily-report [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
