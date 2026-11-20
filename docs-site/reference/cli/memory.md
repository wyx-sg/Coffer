---
title: coffer memory
description: "Memory, one Markdown file per topic in the vault: projects, topics, tidy."
pageClass: cli-ref
---

# coffer memory

Memory, one Markdown file per topic in the vault: projects, topics, tidy.

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer memory --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`memory state`](#memory-state) | The projects that hold memories, whether a tidy is open, and the Tidy prompt. |
| [`memory topics`](#memory-topics) | A project's memory files, with what breaks the format in each. |
| [`memory show`](#memory-show) | One memory file's text. |
| [`memory tidy-start`](#memory-tidy-start) | Open a tidy: until it finishes, the edits under memory/ are kept for one commit. |
| [`memory tidy-finish`](#memory-tidy-finish) | Close the tidy and commit its edits as one commit. |
| [`memory session-start`](#memory-session-start) | Print the memories a session started here is handed (the agents' hook runs it). |

## memory state

The projects that hold memories, whether a tidy is open, and the Tidy prompt.

<p class="cli-label">Synopsis</p>

```sh
coffer memory state [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory topics

A project's memory files, with what breaks the format in each.

<p class="cli-label">Synopsis</p>

```sh
coffer memory topics [OPTIONS] PROJECT
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PROJECT` <span class="cli-chip">argument</span> | text | required | The project's folder (from coffer memory state) |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory show

One memory file's text.

<p class="cli-label">Synopsis</p>

```sh
coffer memory show [OPTIONS] PROJECT NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PROJECT` <span class="cli-chip">argument</span> | text | required | The project's folder |
| `NAME` <span class="cli-chip">argument</span> | text | required | The file's name (from coffer memory topics) |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory tidy-start

Open a tidy: until it finishes, the edits under memory/ are kept for one commit.

<p class="cli-label">Synopsis</p>

```sh
coffer memory tidy-start [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory tidy-finish

Close the tidy and commit its edits as one commit. Body: summary (the agent's report).

<p class="cli-label">Synopsis</p>

```sh
coffer memory tidy-finish [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## memory session-start

Print the memories a session started here is handed (the agents' hook runs it).

Reads the hook's JSON from standard input for the session's working directory, falling back to the current directory. Prints nothing outside a repository, and nothing in a session Coffer started itself, whose system prompt already carries them. Never fails a session: any error prints nothing and exits 0. Needs no running daemon.

<p class="cli-label">Synopsis</p>

```sh
coffer memory session-start [OPTIONS]
```
