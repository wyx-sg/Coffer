---
title: coffer sync
description: "Keep this vault in step with a git remote you own"
---

# coffer sync

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer sync [OPTIONS] COMMAND [ARGS]...
```

Keep this vault in step with a git remote you own

## sync now

```sh
coffer sync now [OPTIONS]
```

Run one round with the remote, right now.

## sync status

```sh
coffer sync status [OPTIONS]
```

The remote, the last round, and anything waiting for you.

Exits 1 while a round waits for a person — stopped on conflicts, held, unable to reach or sign in to the remote, or paused because the vault is inside a synchronised folder — so a prompt or a monitor notices without reading the text. A paused remote exits 0.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands the current problem (a refused push or sign-in, an unreachable remote, git missing, a plaintext secret in what a push would publish) to your agent |

## sync push-anyway

```sh
coffer sync push-anyway [OPTIONS]
```

Push what the last round refused as a plaintext secret, once you checked it is not one.

Allows exactly the file versions that round found (a file changed since is read again), records it in the audit log, and runs a round.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--yes, -y` | 选项 | 开关 |  | Do not ask before pushing |

## sync history

```sh
coffer sync history [OPTIONS]
```

Every round this machine has run, newest first, one line each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--limit` | 选项 | integer | `20` | How many rounds to show, newest first |

## sync rollback

```sh
coffer sync rollback [OPTIONS] RUN_ID
```

Put back what one round changed, from its snapshot.

The plan is printed first. Rolling back is a new commit on this machine, which the next round pushes; files edited since the round are kept.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `RUN_ID` | 参数 | integer | 必填 | The round to roll back (see coffer sync history) |
| `--yes, -y` | 选项 | 开关 |  | Do not ask before rolling back |

## sync join

```sh
coffer sync join [OPTIONS]
```

Join the configured remote. What joining would do is printed first; joining never deletes a file on either side, except that this vault replaces a remote at an older layout (the old history stays in git).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--yes, -y` | 选项 | 开关 |  | Do not ask before joining |

## sync conflicts

```sh
coffer sync conflicts [OPTIONS]
```

The files the stopped round waits on (or the held deletions).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands merging the conflicting files to your agent |

## sync resolve

```sh
coffer sync resolve [OPTIONS] [PATH]
```

Answer one conflicting file, or record an agent's merge of them all with --merged. Nothing is written until 'continue'.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text |  | Vault-relative path of a conflicting file (not with --merged) |
| `--mine` | 选项 | 开关 |  | Keep this machine's version |
| `--theirs` | 选项 | 开关 |  | Take the other machine's version |
| `--edited` | 选项 | 开关 |  | Take the hand-merged copy 'coffer sync edit' opened |
| `--merged` | 选项 | 开关 |  | Record an agent's merge: every file handed to it takes its merged copy |

## sync edit

```sh
coffer sync edit [OPTIONS] PATH
```

Print the path of a marked-up copy of the file to hand-merge; then 'coffer sync resolve PATH --edited'. The vault's file is untouched.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | Vault-relative path of a conflicting file |

## sync continue

```sh
coffer sync continue [OPTIONS]
```

Continue the stopped round once every file has an answer.

## sync hold

```sh
coffer sync hold [OPTIONS]
```

Show a held round, or answer it: --confirm deletes the files, --restore keeps them. Either continues the round.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--confirm` | 选项 | 开关 |  | Delete the held files |
| `--restore` | 选项 | 开关 |  | Keep the held files |

## sync choose

```sh
coffer sync choose [OPTIONS] [PATH]
```

Settle a file a join found different on both sides.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text |  | A file that differs (omit to list them) |
| `--mine` | 选项 | 开关 |  | Keep this machine's version |
| `--theirs` | 选项 | 开关 |  | Take the remote's version |

## sync remote

```sh
coffer sync remote [OPTIONS] COMMAND [ARGS]...
```

The one git remote this vault syncs with

子命令：`set`, `clear`, `pause`, `resume`, `check`。

## sync remote set

```sh
coffer sync remote set [OPTIONS] URL
```

Configure the remote ('coffer sync remote check' looks at it first).

On a configured remote an option not given keeps its stored value, and a paused remote stays paused (`coffer sync remote resume` resumes it). A remote set for the first time takes the defaults and starts enabled.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `URL` | 参数 | text | 必填 | Git remote URL you own (https, ssh, or file://) |
| `--branch` | 选项 | text |  | Default main |
| `--interval` | 选项 | integer |  | Seconds between automatic rounds (default 3600) |
| `--with-secret / --without-secret` | 选项 | boolean |  | Carry the encrypted secrets (ciphertext, never the master key); default off |
| `--secret-ref` | 选项 | text |  | Name of the push token in the secret store ('' removes it) |
| `--username` | 选项 | text |  | User name an HTTPS token is sent with, for a host that does not imply it (default coffer; GitLab: oauth2 or your user name; Bitbucket and Azure DevOps need a real one) |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## sync remote clear

```sh
coffer sync remote clear [OPTIONS]
```

Stop syncing: forget the remote. The vault is left exactly as it is.

## sync remote pause

```sh
coffer sync remote pause [OPTIONS]
```

Pause sync. The remote, its settings and the history are all kept.

## sync remote resume

```sh
coffer sync remote resume [OPTIONS]
```

Resume a paused remote where the vault left off.

## sync remote check

```sh
coffer sync remote check [OPTIONS] [URL]
```

Look at a remote without keeping it: empty, a Coffer vault (and its layout), another repository, unreachable, or refusing the token.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `URL` | 参数 | text |  | A remote to look at (default: the stored one) |
| `--branch` | 选项 | text |  | Default main |
| `--secret-ref` | 选项 | text |  | Push token to use |
| `--username` | 选项 | text |  | User name the token is sent with (default: the stored one, else coffer; GitLab: oauth2 or your user name) |

## sync machine

```sh
coffer sync machine [OPTIONS] COMMAND [ARGS]...
```

The machines sharing this vault

子命令：`list`, `rename`, `rm`。

## sync machine list

```sh
coffer sync machine list [OPTIONS]
```

Every machine sharing this vault.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## sync machine rename

```sh
coffer sync machine rename [OPTIONS] NAME
```

Rename this machine. Free: nothing keys on the label; the next round carries the new one.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 |  |

## sync machine rm

```sh
coffer sync machine rm [OPTIONS] MACHINE_ID
```

Retire another machine: its descriptor goes, in a commit of yours that the next round pushes. A machine that syncs again comes back.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `MACHINE_ID` | 参数 | text | 必填 |  |

## sync key

```sh
coffer sync key [OPTIONS] COMMAND [ARGS]...
```

Install a master key brought from another machine, or compare fingerprints. Exporting a key backup is done in the Coffer desktop app.

子命令：`import`, `fingerprint`。

## sync key import

```sh
coffer sync key import [OPTIONS] PATH
```

Install a master key brought from another machine.

A ``.cfk`` backup asks for the passphrase it was exported with, without echoing it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The key backup (coffer-master-key.cfk) exported from another machine, or a bare key |

## sync key fingerprint

```sh
coffer sync key fingerprint [OPTIONS]
```

This machine's key fingerprint, to compare with another machine's.
