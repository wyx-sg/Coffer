---
title: coffer secret
description: "Manage encrypted secrets."
---

# coffer secret

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

Manage encrypted secrets.

## secret set

```sh
coffer secret set [OPTIONS] REF
```

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--value` | 选项 | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## secret get

```sh
coffer secret get [OPTIONS] REF
```

Check that a secret is stored, without its value.

Prints [redacted] when it is, exits 4 when it is not. No value leaves the daemon and nothing is audited. To see a value, open the Coffer desktop app: it asks for Touch ID or your password each time.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## secret list

```sh
coffer secret list [OPTIONS]
```

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## secret rm

```sh
coffer secret rm [OPTIONS] REF
```

Delete a secret from the encrypted secret store (via the daemon).

Asks first unless --force is given.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `REF` | 参数 | text | 必填 | Secret reference key |
| `--force, -f` | 选项 | 开关 |  | Skip confirmation prompt |

## secret approvals

```sh
coffer secret approvals [OPTIONS]
```

List what waits for approval in the Coffer app.

Approving takes Touch ID or your password in the desktop app; the terminal can only list and reject.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--all` | 选项 | 开关 |  | Include decided approvals |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## secret reject

```sh
coffer secret reject [OPTIONS] APPROVAL_ID
```

Refuse a pending approval. Refusing needs no presence check.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `APPROVAL_ID` | 参数 | text | 必填 | Approval id (see `coffer secret approvals`) |

## secret scan

```sh
coffer secret scan [OPTIONS]
```

Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

Prints where each one is and the name it would get — never the value. Move them into the encrypted store with `coffer secret import`.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ to an agent |

## secret import

```sh
coffer secret import [OPTIONS]
```

Move plaintext secrets into the encrypted store, leaving references.

Each value is stored as coffer://secret/&lt;name&gt;, read back and compared, and only then replaced in its file by the reference. No plaintext backup is kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--id` | 选项 | text（可重复） |  | Only this finding (repeatable; default: every finding) |
| `--dry-run` | 选项 | 开关 |  | Print the plan and write nothing |
| `--yes, -y` | 选项 | 开关 |  | Skip the confirmation prompt |
