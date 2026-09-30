---
title: coffer proxy
description: "Inspect the local model proxy and its per-agent tokens"
---

# coffer proxy

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

Inspect the local model proxy and its per-agent tokens

## proxy token

```sh
coffer proxy token [OPTIONS]
```

Print an agent's local proxy token (what its key helper runs).

The token unlocks only this machine's loopback model proxy; it is never a provider key. Exits 4 with nothing on stdout for an agent this machine does not have, so a stale helper fails instead of printing a token.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--agent-uid` | option | text | required | The agent whose token to print |

## proxy rotate

```sh
coffer proxy rotate [OPTIONS] REF
```

Replace an agent's local proxy token; the old one stops working at once.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `REF` | argument | text | required | Agent name or uid |

## proxy status

```sh
coffer proxy status [OPTIONS]
```

Show whether the model proxy is running, where, and how often it restarted.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | Machine-readable output |
