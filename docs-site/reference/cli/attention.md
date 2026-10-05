---
title: coffer attention
description: "What needs you (the Overview list): list, ignore, un-ignore."
pageClass: cli-ref
---

# coffer attention

What needs you (the Overview list): list, ignore, un-ignore.

```sh
coffer attention [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer attention --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`attention list`](#attention-list) | What needs you, each with its fix or its hand-off prompt. |
| [`attention ignore`](#attention-ignore) | Stop listing an informational item. |
| [`attention unignore`](#attention-unignore) | List an ignored item again. |

## attention list

What needs you, each with its fix or its hand-off prompt.

<p class="cli-label">Synopsis</p>

```sh
coffer attention list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## attention ignore

Stop listing an informational item.

<p class="cli-label">Synopsis</p>

```sh
coffer attention ignore [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | key |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## attention unignore

List an ignored item again.

<p class="cli-label">Synopsis</p>

```sh
coffer attention unignore [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | key |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
