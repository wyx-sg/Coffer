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

本页与 `coffer migrate --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--rollback` <span class="cli-chip">选项</span> | 开关 |  | Put this home back as it was before the upgrade. |
| `--resume` <span class="cli-chip">选项</span> | 开关 |  | Lift the hold a rollback left, so the upgrade can run again. |
| `--rehearse` <span class="cli-chip">选项</span> | 开关 |  | Run the upgrade and its rollback on a copy; the home itself is only read. |
| `--home` <span class="cli-chip">选项</span> | path |  | With --rehearse: the home to copy (default: $HOME). |
