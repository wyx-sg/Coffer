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

本页与 `coffer secret --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`secret set`](#secret-set) | Store a secret in the encrypted secret store (via the daemon). |
| [`secret get`](#secret-get) | Check that a secret is stored, without its value. |
| [`secret list`](#secret-list) | List every stored secret and every ref a resource cites. |
| [`secret rm`](#secret-rm) | Delete a secret from the encrypted secret store (via the daemon). |
| [`secret approvals`](#secret-approvals) | List what waits for approval in the Coffer app. |
| [`secret reject`](#secret-reject) | Refuse a pending approval. |
| [`secret scan`](#secret-scan) | Find plaintext secrets in ~/.coffer/secrets/ and in your skills. |
| [`secret import`](#secret-import) | Move plaintext secrets into the encrypted store, leaving references. |

## secret set

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

<p class="cli-label">概要</p>

```sh
coffer secret set [OPTIONS] REF
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">参数</span> | text | 必填 | Secret reference key |
| `--value` <span class="cli-chip">选项</span> | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` <span class="cli-chip">选项</span> | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## secret get

Check that a secret is stored, without its value.

Prints [redacted] when it is, exits 4 when it is not. No value leaves the daemon and nothing is audited. To see a value, open the Coffer desktop app: it asks for Touch ID or your password each time.

<p class="cli-label">概要</p>

```sh
coffer secret get [OPTIONS] REF
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">参数</span> | text | 必填 | Secret reference key |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## secret list

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

<p class="cli-label">概要</p>

```sh
coffer secret list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## secret rm

Delete a secret from the encrypted secret store (via the daemon).

Asks first unless --force is given.

<p class="cli-label">概要</p>

```sh
coffer secret rm [OPTIONS] REF
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">参数</span> | text | 必填 | Secret reference key |
| `--force, -f` <span class="cli-chip">选项</span> | 开关 |  | Skip confirmation prompt |

## secret approvals

List what waits for approval in the Coffer app.

Approving takes Touch ID or your password in the desktop app; the terminal can only list and reject.

<p class="cli-label">概要</p>

```sh
coffer secret approvals [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Include decided approvals |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## secret reject

Refuse a pending approval. Refusing needs no presence check.

<p class="cli-label">概要</p>

```sh
coffer secret reject [OPTIONS] APPROVAL_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APPROVAL_ID` <span class="cli-chip">参数</span> | text | 必填 | Approval id (see `coffer secret approvals`) |

## secret scan

Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

Prints where each one is and the name it would get — never the value. Move them into the encrypted store with `coffer secret import`.

<p class="cli-label">概要</p>

```sh
coffer secret scan [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ to an agent |

## secret import

Move plaintext secrets into the encrypted store, leaving references.

Each value is stored as coffer://secret/&lt;name&gt;, read back and compared, and only then replaced in its file by the reference. No plaintext backup is kept.

<p class="cli-label">概要</p>

```sh
coffer secret import [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--id` <span class="cli-chip">选项</span> | text（可重复） |  | Only this finding (repeatable; default: every finding) |
| `--dry-run` <span class="cli-chip">选项</span> | 开关 |  | Print the plan and write nothing |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Skip the confirmation prompt |
