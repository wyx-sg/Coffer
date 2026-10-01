---
title: coffer sync
description: "Keep this vault in step with a git remote you own"
---

# coffer sync

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

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

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |
| `--prompt` | option | flag |  | Print the prompt that hands the current problem (a refused push or sign-in, an unreachable remote, git missing, a plaintext secret in what a push would publish) to your agent |

## sync push-anyway

```sh
coffer sync push-anyway [OPTIONS]
```

Push what the last round refused as a plaintext secret, once you checked it is not one.

Allows exactly the file versions that round found (a file changed since is read again), records it in the audit log, and runs a round.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--yes, -y` | option | flag |  | Do not ask before pushing |

## sync history

```sh
coffer sync history [OPTIONS]
```

Every round this machine has run, newest first, one line each.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--limit` | option | integer | `20` | How many rounds to show, newest first |

## sync rollback

```sh
coffer sync rollback [OPTIONS] RUN_ID
```

Put back what one round changed, from its snapshot.

The plan is printed first. Rolling back is a new commit on this machine, which the next round pushes; files edited since the round are kept.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `RUN_ID` | argument | integer | required | The round to roll back (see coffer sync history) |
| `--yes, -y` | option | flag |  | Do not ask before rolling back |

## sync join

```sh
coffer sync join [OPTIONS]
```

Join the configured remote. What joining would do is printed first; joining never deletes a file on either side.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--yes, -y` | option | flag |  | Do not ask before joining |

## sync conflicts

```sh
coffer sync conflicts [OPTIONS]
```

The files the stopped round waits on (or the held deletions).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--prompt` | option | flag |  | Print the prompt that hands merging the conflicting files to your agent |

## sync resolve

```sh
coffer sync resolve [OPTIONS] [PATH]
```

Answer one conflicting file, or record an agent's merge of them all with --merged. Nothing is written until 'continue'.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text |  | Vault-relative path of a conflicting file (not with --merged) |
| `--mine` | option | flag |  | Keep this machine's version |
| `--theirs` | option | flag |  | Take the other machine's version |
| `--edited` | option | flag |  | Take the hand-merged copy 'coffer sync edit' opened |
| `--merged` | option | flag |  | Record an agent's merge: every file handed to it takes its merged copy |

## sync edit

```sh
coffer sync edit [OPTIONS] PATH
```

Print the path of a marked-up copy of the file to hand-merge; then 'coffer sync resolve PATH --edited'. The vault's file is untouched.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | Vault-relative path of a conflicting file |

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

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--confirm` | option | flag |  | Delete the held files |
| `--restore` | option | flag |  | Keep the held files |

## sync choose

```sh
coffer sync choose [OPTIONS] [PATH]
```

Settle a file a join found different on both sides.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text |  | A file that differs (omit to list them) |
| `--mine` | option | flag |  | Keep this machine's version |
| `--theirs` | option | flag |  | Take the remote's version |

## sync remote

```sh
coffer sync remote [OPTIONS] COMMAND [ARGS]...
```

The one git remote this vault syncs with

Subcommands: `set`, `clear`, `pause`, `resume`, `check`.

## sync remote set

```sh
coffer sync remote set [OPTIONS] URL
```

Configure the remote ('coffer sync remote check' looks at it first).

On a configured remote an option not given keeps its stored value, and a paused remote stays paused (`coffer sync remote resume` resumes it). A remote set for the first time takes the defaults and starts enabled.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `URL` | argument | text | required | Git remote URL you own (https, ssh, or file://) |
| `--branch` | option | text |  | Default main |
| `--interval` | option | integer |  | Seconds between automatic rounds (default 3600) |
| `--with-secret / --without-secret` | option | boolean |  | Carry the encrypted secrets (ciphertext, never the master key); default off |
| `--secret-ref` | option | text |  | Name of the push token in the secret store ('' removes it) |
| `--username` | option | text |  | User name an HTTPS token is sent with, for a host that does not imply it (default coffer; GitLab: oauth2 or your user name; Bitbucket and Azure DevOps need a real one) |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

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

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `URL` | argument | text |  | A remote to look at (default: the stored one) |
| `--branch` | option | text |  | Default main |
| `--secret-ref` | option | text |  | Push token to use |
| `--username` | option | text |  | User name the token is sent with (default: the stored one, else coffer; GitLab: oauth2 or your user name) |

## sync machine

```sh
coffer sync machine [OPTIONS] COMMAND [ARGS]...
```

The machines sharing this vault

Subcommands: `list`, `rename`, `rm`.

## sync machine list

```sh
coffer sync machine list [OPTIONS]
```

Every machine sharing this vault.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## sync machine rename

```sh
coffer sync machine rename [OPTIONS] NAME
```

Rename this machine. Free: nothing keys on the label; the next round carries the new one.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required |  |

## sync machine rm

```sh
coffer sync machine rm [OPTIONS] MACHINE_ID
```

Retire another machine: its descriptor goes, in a commit of yours that the next round pushes. A machine that syncs again comes back.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `MACHINE_ID` | argument | text | required |  |

## sync key

```sh
coffer sync key [OPTIONS] COMMAND [ARGS]...
```

Install a master key brought from another machine, or compare fingerprints. Exporting a key backup is done in the Coffer desktop app.

Subcommands: `import`, `fingerprint`.

## sync key import

```sh
coffer sync key import [OPTIONS] PATH
```

Install a master key brought from another machine.

A ``.cfk`` backup asks for the passphrase it was exported with, without echoing it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | The key backup (coffer-master-key.cfk) exported from another machine, or a bare key |

## sync key fingerprint

```sh
coffer sync key fingerprint [OPTIONS]
```

This machine's key fingerprint, to compare with another machine's.
