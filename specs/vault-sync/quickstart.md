# Quickstart — Vault Sync

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Keep one vault across your machines. You point each of them at a git repository
you own; a background worker converges them. The master key never enters the
repository — you bring it over once, out-of-band.

## 1. Point machine one at a repository you own

Create an empty repository anywhere you like (GitHub, your own server, a bare
repo on a NAS). Put the push token in the credential store first, so the remote
can name it by reference and never by value:

```bash
coffer credentials set sync/github-token ghp_...
coffer sync remote set https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token \
  --interval 1h \
  --with-credentials
```

`--with-credentials` is what makes Fernet **ciphertext** ride along. Leave it
off and no credential material ever reaches the repository; the master key is
never written there either way.

Then run a round by hand rather than waiting for the timer:

```bash
coffer sync now
```

```
round ok — 214 documents published, nothing to apply
  knowledge 186 · skills 14 · resources 11 · state 3
pointer 9f1c2ab
```

The first round on an empty remote has nothing to apply and everything to
publish. Look at what you just published — it is all text, in a git repository
you own:

```bash
git -C ~/.coffer/sync log --stat -1
```

## 2. Join from machine two

Install Coffer on the other machine, then:

```bash
coffer sync adopt https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token
```

Adopting tells you **what kind of join this is** before it applies anything:

```
joining as a NEW machine — this machine's id is not in the registry
  remote holds   214 documents
  this vault has  37 documents, none of them published yet
  nothing will be deleted on either side

joined — 214 applied, 0 failed, 37 to publish next round
```

A new machine takes the **union**: everything the remote holds is added here,
everything this machine already had stays, and the next round publishes both.
Deletion is structurally impossible on a join like this, because the base is
git's empty tree and a diff from nothing can only contain additions.

If instead this machine has converged before and merely lost its pointer — a
reinstall, a wiped `~/.coffer`, a disk restored from elsewhere — it says so, and
recovers its base from its own descriptor in the registry:

```
joining as a RETURNING machine — last converged 2026-09-02 at 4a71e0c
  8 documents changed on the remote since
  3 documents changed in this vault since
```

That distinction is the whole point: a returning machine treated as new would
republish everything the others deleted while it was away. If its vault is
*also* gone, the round stops and asks instead of publishing the loss — see
step 7.

## 3. Bring the master key over (only if the remote carries credentials)

On machine one:

```bash
coffer sync key export ~/coffer-master.key
```

Move that file over a channel you trust (password manager, secure copy, USB) —
**not** through the sync repository. On machine two:

```bash
coffer sync key import ~/coffer-master.key
```

> Skip this and convergence still works, but the credentials that arrived stay
> **locked**: they are reported as `credentials_locked`, and resources that need
> them won't spawn. The Machines tab says so directly, by comparing key
> fingerprints for you.

## 4. Watch them converge

Nothing else is required — the worker runs a round every interval on both
machines. To see where things stand:

```bash
coffer sync status
```

```
remote   https://github.com/you/coffer-vault.git (main), every 1h
machine  Laptop — a3f21c9e4b7d2610 (this machine)
pointer  c04b8e1
last     ok, 2026-09-13 14:02 — 3 applied, 0 failed
next     15:02
pending  none
```

Write a knowledge note on one machine, wait a round, and read it on the other.
Delete it on one, wait a round, and it is gone on the other — because a deletion
reached the diff as a deletion. A machine that merely *lacks* a document never
deletes anything, which is why a laptop that was off for a week comes back and
absorbs what happened rather than undoing it.

An unchanged vault makes no commit at all. The serialization is deterministic,
so a round with nothing to say produces nothing, and the repository's history
records changes rather than heartbeats.

## 5. Keep something off one machine

Some things belong on one machine only — a work MCP server, a skill that needs a
binary the laptop doesn't have. The resource itself converges to both machines,
because its configuration is worth having in both places. What it **reaches**
does not: reach is set on the machine it applies to, and every machine sets its
own.

So say it on the laptop, sitting at the laptop:

```bash
coffer resource disable mcp_server:work-jira
```

It stays registered and visible there, its configuration keeps converging, and
the gateway exposes none of its tools to any session on that machine. The
desktop is untouched — and stays untouched, because nothing about reach is
published.

Restricting to one agent works the same way, and is also local to the machine
you run it on:

```bash
coffer scope set mcp_server:work-jira --agents claude-code
```

List your machines whenever you want to see who is in the vault:

```bash
coffer sync machines
```

```
ID                NAME      OS      LAST CONVERGED  KEY
a3f21c9e4b7d2610  Laptop    darwin  2026-09-13      4f2a91c0b8de  (this machine)
b7c40d29e1f58a33  Desktop   darwin  2026-09-13      4f2a91c0b8de
```

Rename one whenever you like — nothing keys on the label:

```bash
coffer sync machine rename "Work desktop"
```

## 6. When a conflict stops a round

Edit the same lines of the same document on two machines before either has
converged and git cannot decide. With an internal model configured, a bounded
pass attempts the merge in the working tree and reports every path it touched.
Otherwise the round stops without touching your vault:

```
round conflict — nothing applied, pointer unchanged
  knowledge/projects/coffer.md
resolve in ~/.coffer/sync with your own git tools, then run `coffer sync now`
```

Your vault is untouched and the pointer has not moved, so nothing is lost while
you decide. The working tree is an ordinary git repository:

```bash
cd ~/.coffer/sync
git status
$EDITOR knowledge/projects/coffer.md   # resolve the markers
git add -A && git commit
coffer sync now
```

A conflict blocks convergence on both machines until it is resolved. That is
deliberate: two machines quietly disagreeing about one document is worse than
two machines waiting.

## 7. When a round asks before it deletes

A round that would remove an unusual share of documents does not proceed. It
records what it would do and waits for you:

```
round awaiting confirmation — PUBLISH side
  this round would delete 186 documents from the remote
  knowledge 186 of 186 · skills 14 of 14
  this vault looks empty; the remote is not
```

Both directions are guarded. The **apply** side protects this vault from a
remote that went wrong; the **publish** side protects the other machines from
*this* one — a reinstall, a failed restore or a stray `rm -rf` would otherwise
publish the loss and take the fleet down with it.

```bash
coffer sync confirm            # yes, apply it
coffer sync confirm --reject   # no, leave everything as it is
coffer sync confirm --rebuild  # rebuild this machine from the remote instead
```

`--rebuild` is the answer when this machine is the damaged one: take the
remote's state and discard what is local-only, rather than publishing an
accidental deletion.

If a round did apply something you did not want, it is reversible — every round
tags the state of the vault immediately before it applied:

```bash
coffer sync rollback
```

## 8. Bring back something deleted last week

The remote's history is also your backup. Restore moves the working tree to a
revision and applies the difference from where you are now, so nothing the vault
has gained since is discarded:

```bash
coffer sync restore --at 2026-09-05
coffer sync restore --at 4a71e0c
```

A date resolves to the last commit at or before it. Restore is always explicit —
a round never reaches back into history on its own.

## What never travels

Logs, `coffer.db`, `daemon-config.json`, PID and port files, chat history,
conversations, the audit log, MCP invocation records — and the master key,
which is never written into the repository under any setting.

Conversations and the audit log are excluded on purpose: they record what
happened *on a machine*, and merging two machines' activity would be a different
feature with a different shape.

## REST / Web UI

Everything above is also a top-level **Sync** page with three tabs —
**Status** (the remote, the next round, a run button, and the master-key card),
**History** (every round this machine has run, as a table: when it ran, how it
ended, what it applied here, what it published to the remote, and the commit it
landed on — open a row for the paths an agent merged, the ones that could not be
applied, and anything that failed) and **Machines** (the registry table, with
this machine marked and any key-fingerprint mismatch stated in words). Conflicts
and pending confirmations appear as a banner on Status.

Over HTTP the same operations live under `/api/v1/sync/*` — `run`, `adopt`,
`status`, `runs`, `restore`, `confirm`, `rollback`, the `machines` family and
the key family. The key routes carry the key **material**, not a path: `POST
/sync/key/export` takes `{}` and returns `{"material": "…"}`, and `POST
/sync/key/import` takes `{"material": "…"}`. The CLI commands above still write
and read a file — the CLI does that file I/O itself, so the daemon never opens a
path a caller named. In the web UI the export lands as a browser download and
the import reads an `<input type="file">`.
