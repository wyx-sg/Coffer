---
title: coffer model
description: "Ask a model endpoint which models it serves, or test it."
pageClass: cli-ref
---

# coffer model

Ask a model endpoint which models it serves, or test it.

```sh
coffer model [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer model --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`model list`](#model-list) | Ask an endpoint which models it serves. |
| [`model test`](#model-test) | Send one request to a model. |

## model list

Ask an endpoint which models it serves. Body: provider, base_url, secret_ref | secret_value.

<p class="cli-label">Synopsis</p>

```sh
coffer model list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## model test

Send one request to a model. Body: provider, base_url, model, secret_ref | secret_value.

<p class="cli-label">Synopsis</p>

```sh
coffer model test [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
