---
title: Upgrading an existing Coffer
description: Move a Coffer home from the single coffer.db database into the vault layout with coffer migrate — rehearse it, run it, roll it back, and replace your sync remote.
---

# Upgrading an existing Coffer

Coffer used to keep its configuration in one SQLite database, `~/.coffer/coffer.db`, beside file trees for knowledge and skills. It now keeps state in [five storage classes](/architecture/persistence): a vault git repository, local JSON, content, a history database and derived state. Moving an existing home across is a one-time step you run yourself, with `coffer migrate`. This page is for anyone who has used an earlier Coffer and installs a build with the vault layout. A fresh install needs none of it.

## What you will notice

After installing the new build, the daemon refuses to start on a home that still holds only `coffer.db`:

```text
/Users/you/.coffer/coffer.db was written by a Coffer from before the vault layout. Stop the
daemon and run `coffer migrate` once to move it into ~/.coffer/vault
(`coffer migrate --rehearse` tries it on a copy first).
```

The error code is `VAULT_MIGRATION_REQUIRED`. Nothing has been changed at that point. The daemon never migrates your home in your place, because the upgrade moves the trees and the database a running daemon holds open.

After the upgrade, one thing looks like a fault and is not: **every secret waits once for your approval**. The upgrade carries your secrets across but no approvals, and a secret goes to a destination only after you approve it there. So the first time a provider, an MCP server, a channel or the sync remote needs its secret, it waits for you in the Coffer app (the [Secrets page](/guides/secrets#approvals)) and stays idle until you approve — a channel, for example, shows "waiting for approval" instead of connecting, with its pairing and settings kept. Approve each one once; it starts by itself on its next attempt, with no restart.

## The default ports moved

The daemon's default port is now **38470** (it was 8000) and the local model proxy's is **38471** (it was 8001), because 8000 and 8001 are the most commonly taken development ports. A port you set yourself with `coffer config set daemon.port` is kept. Otherwise, after the first start of the new build:

- Bookmarks to `http://127.0.0.1:8000/` stop working; use `http://127.0.0.1:38470/`.
- The browser stores the web UI's language, sidebar state, page size and preferred editor per address, so they reset once on the new address. The desktop app is unaffected.
- Agents follow by themselves: the MCP shim reads the daemon's discovery file, and Coffer rewrites the model proxy address in each agent's config on its next reconcile.

## Before you start

- **Stop the daemon.** Quit the desktop app if you use it, then run `coffer daemon stop`. `coffer migrate` refuses while a daemon runs.
- **Have `git`.** The vault is a git repository, so git 2.40 or later must be on the `PATH`. If it is missing, Coffer's `GIT_MISSING` error offers a prompt that hands installing git to your agent.
- **Make sure the disk has room for a copy of `~/.coffer`** if you rehearse (below). The upgrade itself moves trees rather than copying them, and adds only a copy of the database.

## Rehearse it

```sh
coffer migrate --rehearse
```

A rehearsal copies `~/.coffer` into a throwaway home, runs the upgrade there, checks that every item it counted before is still there after, rolls the copy back, compares the result with the original byte for byte, and deletes the copy. Your home is only read. It ends with `rehearsal passed` or with a list of what went wrong and `do not migrate this home yet`. `--home PATH` rehearses another home.

## Run it

```sh
coffer migrate
```

In order, the upgrade:

1. Backs up `coffer.db` (with its `-wal` and `-shm` files) as `coffer.db.pre-vault`, and `daemon-config.json` into `~/.coffer/pre-vault/`. The backup is never opened for writing again.
2. Reads the old tables and creates `vault/`, `local/`, `content/` and `derived/`.
3. **Moves** (renames, never copies) the file trees:

   | Before | After |
   | --- | --- |
   | `~/.coffer/knowledge/` | `~/.coffer/vault/knowledge/` |
   | `~/.coffer/skills/` | `~/.coffer/vault/skills/` |
   | `~/.coffer/skills/coffer-guide/` | `~/.coffer/derived/skills/coffer-guide/` |
   | `~/.coffer/memory/` | `~/.coffer/derived/memory/` |
   | `~/.coffer/chat-media/`, `channel-media/`, `workspace/` | `~/.coffer/content/…` |
   | `~/.coffer/cache/agent/` | `~/.coffer/derived/cache/agent/` |

4. Folds the knowledge history (`knowledge/.git`) into the vault repository under `knowledge/`, keeping every commit's message, author and date. The old `.git` is kept as `pre-vault/knowledge.git`.
5. Removes the old curation stamps from knowledge documents (the originals are kept in `pre-vault/knowledge-stamped/`) and records which documents were settled in `local/curation.json`.
6. Writes everything from the database as files: each resource as `vault/resources/<kind>/<name>.json` (agents in `local/resources/agent/`), the MCP capability switches, channel pairings and engine settings under `vault/state/`, each secret's ciphertext as `vault/secret/<ref>.enc`, and reach, retention, the secret boundary and the sync remote as JSON under `local/`. The vault gets **one** commit for all of it, written by `daemon`.
7. Renames `coffer.db` to `runs.db` and upgrades it: from then on it holds only history (audit, invocations, conversations, rounds, usage), keyed by uid.

Every move is recorded in `local/migration.json` as it happens, so a rollback can reverse it even after a failure half-way. The report prints the counts per class, anything it could not carry, and notes to act on:

- **Links into moved trees.** Links in `~/.claude` and `~/.codex` that point into the old locations. The skill links Coffer delivered are repaired when the daemon next starts and reconciles; a link you made yourself, you re-point.
- **Nested git repositories** inside moved trees.
- **Your sync remote is replaced** by the first upgraded machine, if you had one (below).
- **Secrets waiting for approval.** When the home holds secrets, the report counts them and says that each one's first use at each destination waits once for your approval in the Coffer app.

Then start Coffer as usual. **Settings → Data** shows where the vault now lives (**Vault** and **Local content** each list their location).

## Roll it back

With the daemon stopped:

```sh
coffer migrate --rollback
```

Rollback puts the home back as it was, byte for byte: the stamped knowledge originals and the knowledge `.git` come back, every recorded move is reversed, `vault/` and `local/` are set aside as `vault.rolled-back-<timestamp>` and `local.rolled-back-<timestamp>` (so anything you changed after upgrading survives in that repository's history), `runs.db` is set aside, `coffer.db.pre-vault` is copied back to `coffer.db`, and `daemon-config.json` is restored. Then install the previous Coffer build.

A rollback leaves a hold marker, `~/.coffer/MIGRATION_ROLLED_BACK`, so the new build does not upgrade the home again behind your back: its daemon refuses to start and names `--resume`. When you want to upgrade again:

```sh
coffer migrate --resume
coffer migrate
```

If an upgrade stops half-way, `coffer migrate` refuses to run again and names `--rollback`: roll back first, then run it again.

## Replace your sync remote

A remote written by an earlier Coffer is in the old layout. It is never converted in place; the upgraded vault is the source of truth and replaces it. Nothing is refused: the first upgraded machine's next round, or its join, replaces the old remote.

1. **Upgrade the first machine.** On the **Sync** page press **Join and pull**: the preview says what goes up by area, which files only the old remote had and will go away (the first 100 are listed, with the exact total), who pushed the old tip and when, and that machines still on the older layout must upgrade. Confirm to replace the remote. The push is a fast-forward, so the old history stays in the remote's git log.

   Your old remote setting was carried into `local/sync/remote.json`, so nothing needs re-entering. A plaintext secret in the vault still stops the push, and the remote keeps its old tip.

2. **Upgrade each other machine**, then join the replaced remote. It joins as a new machine: it takes the union, deletes nothing, and leaves any file that differs for you to choose (**Choose versions** on the **Status** tab of the **Sync** page). A machine still on the earlier Coffer reads only the layout number and refuses the replaced remote until it is upgraded.

Secret ciphertext is committed to the remote only if your old remote carried secrets; otherwise switch on **Include encrypted secrets** when you want it.

## Related

- [Persistence](/architecture/persistence) · [Files and directories](/reference/filesystem)
- [Vault sync](/guides/vault-sync) · [Editing the vault by hand](/guides/vault-files)
- Decision records: [Storage Is Five Classes by Nature](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/storage-is-five-classes-by-nature.md), [Every Vault File Carries Its Own Format Version](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-file-carries-its-format-version.md)
