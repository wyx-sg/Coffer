---
title: coffer migrate
description: "Move this home out of coffer.db into the vault layout (once, daemon stopped)."
pageClass: cli-ref
---

# coffer migrate

Move this home out of coffer.db into the vault layout (once, daemon stopped).

```sh
coffer migrate [OPTIONS]
```

This page matches what `coffer migrate --help` prints. Add `--help` to any command below to see its options in the terminal.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--rollback` <span class="cli-chip">option</span> | flag |  | Put this home back as it was before the upgrade. |
| `--resume` <span class="cli-chip">option</span> | flag |  | Lift the hold a rollback left, so the upgrade can run again. |
| `--rehearse` <span class="cli-chip">option</span> | flag |  | Run the upgrade and its rollback on a copy; the home itself is only read. |
| `--home` <span class="cli-chip">option</span> | path |  | With --rehearse: the home to copy (default: $HOME). |
