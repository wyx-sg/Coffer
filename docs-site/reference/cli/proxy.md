---
title: coffer proxy
description: "The local model proxy."
pageClass: cli-ref
---

# coffer proxy

The local model proxy.

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer proxy --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`proxy status`](#proxy-status) | The local model proxy's state. |
| [`proxy hint`](#proxy-hint) | The tail of an agent's proxy key. |
| [`proxy rotate`](#proxy-rotate) | Mint a new proxy key for an agent. |

## proxy status

The local model proxy's state.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## proxy hint

The tail of an agent's proxy key.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy hint [OPTIONS] AGENT_UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT_UID` <span class="cli-chip">argument</span> | text | required | agent uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## proxy rotate

Mint a new proxy key for an agent.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy rotate [OPTIONS] AGENT_UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT_UID` <span class="cli-chip">argument</span> | text | required | agent uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
