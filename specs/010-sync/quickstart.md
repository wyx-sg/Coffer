# Spec 010 — Quickstart

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Keep one Coffer vault in sync across your machines using a git repo you own.
The master key never travels through git; you bring it to each new machine once,
out-of-band.

## 1. Create a remote you own

Make an empty private repository (GitHub, GitLab, or self-hosted), e.g.
`git@github.com:you/coffer-vault.git`. Coffer uses your normal git credentials
(SSH key or token) — the same ones `git push` already uses.

## 2. Initialise sync on machine A

```bash
coffer sync init git@github.com:you/coffer-vault.git
```

This creates the sync workspace (`~/.coffer/sync/`), records the remote, and
does a first sync run. Check it:

```bash
coffer sync status        # -> clean, last sync <time>
```

## 3. Bring the master key to machine B (out-of-band)

On machine A:

```bash
coffer sync key export ~/coffer-master.key
```

Move that file to machine B over a channel you trust (USB, password manager,
secure copy) — **not** through the sync repo. On machine B:

```bash
coffer sync key import ~/coffer-master.key
```

## 4. Pull the vault on machine B

```bash
coffer sync init git@github.com:you/coffer-vault.git
coffer sync status        # -> clean; credentials decrypt because the key is present
```

Machine B now has the same knowledge, memory, registered resources, and
credentials.

> If you skip step 3, sync still works but credentials stay **locked**:
> `coffer sync status` lists them under `credentials_locked`, and resources that
> need them won't spawn until you import the key.

## 5. Day-to-day

```bash
coffer sync               # export -> pull -> (if clean) push -> import
```

Run it whenever you switch machines. Or turn on hands-off mode:

```bash
coffer sync config --auto on --interval 300
```

With auto-sync, the daemon pushes your changes (debounced) and pulls others on
the interval — no manual command.

## Seeing your machines

```bash
coffer sync machines                    # every machine attached to the vault
coffer sync machines --rename studio    # rename this machine
```

Each machine registers itself (name, platform, last sync) when it syncs; the
list also appears in the desktop Sync panel.

## Conflicts resolve themselves

If you edited the same resource/file on two machines before syncing, the run
auto-resolves each conflicted path to the most recently synced edit and
completes — no manual step. (With auto-sync on both machines, "most recently
synced" and "newer" coincide.) In the rare case the engine cannot settle a
path, the run parks in
`conflicted` and the UI points you at your own repository (e.g. GitHub); the
CLI escape hatch still works:

```bash
coffer sync status        # -> conflicted, lists the paths (rare)
coffer sync resolve --theirs resources/mcp_server/confluence.yaml   # or --ours, or edit then --resolved
coffer sync               # completes
```

## REST / Desktop

Everything above is also available over `/api/v1/sync/*` and in the desktop
**Sync** settings panel (configure remote — validated on save, toggle
auto-sync, see status with actionable error hints, trigger a run, compare
master-key fingerprints across machines).
