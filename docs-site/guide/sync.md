# Multi-machine sync

**Sync** keeps one Coffer vault consistent across all your own machines by pushing and pulling vault state through a **git repository you own** — no vendor cloud, and the encryption master key never leaves your control.

## Set it up

```bash
coffer sync init git@github.com:me/coffer-vault.git    # point at YOUR remote, enable, first sync
coffer sync                                            # full sync: export → pull → push → import
coffer sync status                                     # clean / syncing / conflicted / error
```

- The remote is a private git URL you own; Coffer uses your ambient git credentials (SSH key or token), exactly like a normal `git push`. Coffer ships no hosted endpoint.
- `coffer sync config --auto on --interval 300` enables opt-in periodic sync; auto-sync is **off** by default.

## What travels

**Mirrored:** knowledge-base and memory Markdown, your config resources (MCP servers, agents, skills, channels), and credentials **as Fernet ciphertext only**. **Machine-local (never synced):** logs, the rebuildable `coffer.db` index, `daemon.json`, PID files, and port allocations.

## The master key (out of band)

The encryption master key is **never** written to the repo — only ciphertext travels. Move the key to each new machine yourself:

```bash
coffer sync key export ./master.key       # on the source machine
# move master.key over a trusted channel — NEVER through the repo
coffer sync key import ./master.key        # on the target machine
```

Until the key is present, imported credentials stay **locked** (`coffer sync status` reports it) and resources that need them won't start.

## Conflicts

A git merge conflict stops the run in a `conflicted` state and imports nothing — neither side is discarded. Resolve, then run again:

```bash
coffer sync resolve --theirs path/to/resource.json   # or --ours / --resolved
coffer sync
```

One file per resource keeps conflicts small. A desktop **Sync** settings panel does all of this without the terminal, and the same operations are available over REST at `/api/v1/sync/*`.

[Credentials →](/guide/credentials)
