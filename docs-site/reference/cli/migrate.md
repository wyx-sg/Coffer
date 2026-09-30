---
title: coffer migrate
description: "Move this home out of coffer.db into the vault layout (once, daemon stopped)."
---

# coffer migrate

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer migrate [OPTIONS]
```

Move this home out of coffer.db into the vault layout (once, daemon stopped).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--rollback` | option | flag |  | Put this home back as it was before the upgrade. |
| `--resume` | option | flag |  | Lift the hold a rollback left, so the upgrade can run again. |
| `--rehearse` | option | flag |  | Run the upgrade and its rollback on a copy; the home itself is only read. |
| `--home` | option | path |  | With --rehearse: the home to copy (default: $HOME). |
