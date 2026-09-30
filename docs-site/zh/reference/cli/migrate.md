---
title: coffer migrate
description: "Move this home out of coffer.db into the vault layout (once, daemon stopped)."
---

# coffer migrate

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer migrate [OPTIONS]
```

Move this home out of coffer.db into the vault layout (once, daemon stopped).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--rollback` | 选项 | 开关 |  | Put this home back as it was before the upgrade. |
| `--resume` | 选项 | 开关 |  | Lift the hold a rollback left, so the upgrade can run again. |
| `--rehearse` | 选项 | 开关 |  | Run the upgrade and its rollback on a copy; the home itself is only read. |
| `--home` | 选项 | path |  | With --rehearse: the home to copy (default: $HOME). |
