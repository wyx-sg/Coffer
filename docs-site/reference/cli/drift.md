---
title: coffer drift
description: "See and repair drift between Coffer and the agents' own files"
pageClass: cli-ref
---

# coffer drift

See and repair drift between Coffer and the agents' own files

```sh
coffer drift [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer drift --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`drift list`](#drift-list) | List every difference a reconcile pass would find now. |
| [`drift repair`](#drift-repair) | Apply drift items now. |

## drift list

List every difference a reconcile pass would find now. Writes nothing.

<p class="cli-label">Synopsis</p>

```sh
coffer drift list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--target` <span class="cli-chip">option</span> | text |  | One target only |
| `--kind` <span class="cli-chip">option</span> | text |  | Only items about this kind |
| `--uid` <span class="cli-chip">option</span> | text |  | Only items about this resource |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## drift repair

Apply drift items now. Each repair is audited with you as the actor.

<p class="cli-label">Synopsis</p>

```sh
coffer drift repair [OPTIONS] [IDS]...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `IDS` <span class="cli-chip">argument</span> | text (variadic) |  | Item ids from `coffer drift list` |
| `--all` <span class="cli-chip">option</span> | flag |  | Every item a request would repair |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
