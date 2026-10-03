---
title: coffer secret
description: "Manage encrypted secrets."
pageClass: cli-ref
---

# coffer secret

Manage encrypted secrets.

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer secret --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`secret set`](#secret-set) | Store a secret in the encrypted secret store (via the daemon). |
| [`secret list`](#secret-list) | List every stored secret and every ref a resource cites. |

## secret set

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

<p class="cli-label">Synopsis</p>

```sh
coffer secret set [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | Secret reference key |
| `--value` <span class="cli-chip">option</span> | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## secret list

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

<p class="cli-label">Synopsis</p>

```sh
coffer secret list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
