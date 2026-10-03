---
title: coffer proxy
description: "Inspect the local model proxy and its per-agent tokens"
pageClass: cli-ref
---

# coffer proxy

Inspect the local model proxy and its per-agent tokens

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer proxy --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`proxy token`](#proxy-token) | Print an agent's local proxy token (what its key helper runs). |
| [`proxy rotate`](#proxy-rotate) | Replace an agent's local proxy token; the old one stops working at once. |
| [`proxy status`](#proxy-status) | Show whether the model proxy is running, where, and how often it restarted. |

## proxy token

Print an agent's local proxy token (what its key helper runs).

The token unlocks only this machine's loopback model proxy; it is never a provider key. Exits 4 with nothing on stdout for an agent this machine does not have, so a stale helper fails instead of printing a token.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy token [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--agent-uid` <span class="cli-chip">option</span> | text | required | The agent whose token to print |

## proxy rotate

Replace an agent's local proxy token; the old one stops working at once.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy rotate [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | Agent name or uid |

## proxy status

Show whether the model proxy is running, where, and how often it restarted.

<p class="cli-label">Synopsis</p>

```sh
coffer proxy status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Machine-readable output |
