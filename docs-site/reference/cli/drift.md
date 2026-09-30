---
title: coffer drift
description: "See and repair drift between Coffer and the agents' own files"
---

# coffer drift

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer drift [OPTIONS] COMMAND [ARGS]...
```

See and repair drift between Coffer and the agents' own files

## drift list

```sh
coffer drift list [OPTIONS]
```

List every difference a reconcile pass would find now. Writes nothing.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--target` | option | text |  | One target only |
| `--kind` | option | text |  | Only items about this kind |
| `--uid` | option | text |  | Only items about this resource |
| `--json` | option | flag |  | JSON output for scripts |

## drift repair

```sh
coffer drift repair [OPTIONS] [IDS]...
```

Apply drift items now. Each repair is audited with you as the actor.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `IDS` | argument | text (variadic) |  | Item ids from `coffer drift list` |
| `--all` | option | flag |  | Every item a request would repair |
| `--json` | option | flag |  | JSON output for scripts |
