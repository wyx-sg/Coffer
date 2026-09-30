---
title: coffer proxy
description: "Inspect the local model proxy and its per-agent tokens"
---

# coffer proxy

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

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

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent-uid` | 选项 | text | 必填 | The agent whose token to print |

## proxy rotate

```sh
coffer proxy rotate [OPTIONS] REF
```

Replace an agent's local proxy token; the old one stops working at once.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Agent name or uid |

## proxy status

```sh
coffer proxy status [OPTIONS]
```

Show whether the model proxy is running, where, and how often it restarted.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | Machine-readable output |
