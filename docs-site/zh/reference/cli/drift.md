---
title: coffer drift
description: "See and repair drift between Coffer and the agents' own files"
---

# coffer drift

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer drift [OPTIONS] COMMAND [ARGS]...
```

See and repair drift between Coffer and the agents' own files

## drift list

```sh
coffer drift list [OPTIONS]
```

List every difference a reconcile pass would find now. Writes nothing.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--target` | 选项 | text |  | One target only |
| `--kind` | 选项 | text |  | Only items about this kind |
| `--uid` | 选项 | text |  | Only items about this resource |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## drift repair

```sh
coffer drift repair [OPTIONS] [IDS]...
```

Apply drift items now. Each repair is audited with you as the actor.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `IDS` | 参数 | text（可变个数） |  | Item ids from `coffer drift list` |
| `--all` | 选项 | 开关 |  | Every item a request would repair |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
