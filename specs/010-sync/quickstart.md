# Spec 010 — Quickstart

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Move a Coffer vault to another of your machines: export it to a directory on
machine A, carry that directory across, import it on machine B. The master key
never travels inside the directory — you bring it over once, out-of-band.

## 1. Export the vault on machine A

```bash
coffer sync export ~/coffer-bundle
```

The command writes a plain directory and reports what went into it: counts per
area (knowledge, memory, skills, resources, state) and the bundle path.

```
manifest.json  knowledge/  memory/  skills/  resources/  state/
```

Everything in it is text, so you can read exactly what you are about to carry —
`resources/mcp_server/confluence.yaml` is one readable file per resource.

To include credentials as well, ask for them explicitly:

```bash
coffer sync export ~/coffer-bundle --with-credentials
```

That adds `credentials/<ref>.enc` — Fernet **ciphertext only**. The master key
is never written into the bundle. Without the flag, no credential material
leaves the machine, which is the default because an export directory is easy to
leave somewhere careless.

## 2. Carry the directory to machine B

However you like — Coffer does not transport it:

```bash
scp -r ~/coffer-bundle you@machine-b:~/coffer-bundle
```

A USB drive or your own git repository works just as well.

## 3. Bring the master key over (only if you exported credentials)

On machine A:

```bash
coffer sync key export ~/coffer-master.key
```

Move that file to machine B over a channel you trust (password manager, secure
copy, USB) — **not** inside the bundle. On machine B:

```bash
coffer sync key import ~/coffer-master.key
```

> Skip this and the import still succeeds, but the imported credentials stay
> **locked**: they are reported as `credentials_locked`, and resources that need
> them won't spawn until you import the key.

## 4. Import on machine B

```bash
coffer sync import ~/coffer-bundle
```

Machine B now holds the same knowledge, memory, skills, registered resources and
shared state. Each kind's post-import step has already run, so an imported agent
has its shim installed and an imported skill binding has its symlink — the
resources are as usable as ones you had registered by hand.

The command prints a summary: counts per area, and any resource that could not
be applied here (for example an agent whose `config_dir` does not exist on this
machine) with its ref and the reason. Those are reported, not fatal — everything
else still imported.

## What import does and does not touch

- **The bundle wins.** Anything the bundle contains replaces the local version.
  You chose the direction when you ran the command, so there is nothing to
  arbitrate.
- **Import never deletes.** A resource machine B has that the bundle does not is
  left alone. A bundle is a snapshot of one machine, not a statement about what
  should exist everywhere.
- **Nothing machine-local travels.** Logs, `coffer.db`, `daemon.json`, chat
  history and the audit log stay where they are; the SQLite index on machine B
  is rebuilt from the imported files.

## Keeping two machines aligned

There is no background convergence. If both machines drift, re-export and
re-import in the direction you want — that manual step is the deliberate trade
in [ADR-016](../../docs/decisions/ADR-016-vault-export-import.md).

Because the export is deterministic, two bundles of unchanged vaults are
byte-identical, so you can diff them to see what actually differs:

```bash
diff -r ~/bundle-from-a ~/bundle-from-b
```

## REST / Web UI

Both operations are also available over `/api/v1/sync/*` and in the web UI's
**Sync** settings panel — an export button and an import button, each opening a
native directory picker, plus the master-key card for comparing fingerprints and
running the out-of-band key transfer.
