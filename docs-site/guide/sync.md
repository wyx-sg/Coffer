# Export and import

Moving to a new laptop, or want your desktop to start from what your laptop already knows? **Export** the vault to a directory, carry that directory across, and **import** it on the other machine. There is no remote, no background replication, and no vendor cloud — and the encryption master key never travels inside the directory.

## Export on machine A

```bash
coffer sync export ~/coffer-bundle                       # everything except credentials
coffer sync export ~/coffer-bundle --with-credentials    # + Fernet ciphertext blobs
```

The result is a plain directory of text you can read before you carry it:

```
manifest.json  knowledge/  skills/  resources/  state/  [credentials/]
```

One deterministic YAML per config resource means two exports of an unchanged vault are byte-identical — so `diff -r` between two bundles shows exactly what differs between two machines.

## Carry it across

Coffer does not transport the directory; that part is yours. `scp`, a USB drive, or your own git repository all work:

```bash
scp -r ~/coffer-bundle you@machine-b:~/coffer-bundle
```

## Import on machine B

```bash
coffer sync import ~/coffer-bundle
```

The import mirrors the knowledge and skill trees back, rebuilds the SQLite index from them, registers every config resource, and runs each kind's post-import step — so an imported agent has its shim installed and an imported skill has its symlink. It reports counts per area plus any resource that could not be applied here (for example an agent whose `config_dir` does not exist on this machine); those are reported with their reason, not fatal.

- **The bundle wins.** Anything the bundle contains replaces the local version — you chose the direction when you ran the command.
- **Import never deletes.** A resource this machine has that the bundle does not is left alone. A bundle is one machine's snapshot, not a statement about what should exist everywhere.

## What travels

**In the bundle:** the knowledge Markdown trees (entries and ingested documents alike), the master skill store, your config resources (MCP servers, agents, skills, channels), module-owned shared state (channel pairings, knowledge-scope labels, engine settings, MCP capability preferences, and the agent plugin inventory), and — only with `--with-credentials` — credentials **as Fernet ciphertext only**.

The plugin inventory is a **list, not an installer**. It records which plugins each agent has here, under `state/agent-plugins/<agent>.yaml`. Importing it stores the list; it does not install anything and does not touch any agent's configuration. On the new machine, open the file and install them with the vendor's own CLI. Coffer deliberately does not write another tool's private plugin format — and it has no install path to offer even if it wanted to.

**Machine-local (never exported):** logs, the rebuildable `coffer.db` index, `daemon.json`, PID files, port allocations, chat history, and the audit log.

## The master key (out of band)

The master key is **never** written into a bundle — only ciphertext travels. Move the key to each new machine yourself:

```bash
coffer sync key export ./master.key       # on the source machine
# move master.key over a trusted channel — NEVER inside the bundle
coffer sync key import ./master.key        # on the target machine
```

Until the key is present, imported credentials stay **locked** (reported as `credentials_locked`) and resources that need them won't start.

The daemon never opens a path you name for this. `POST /api/v1/sync/key/export` returns the key **material** and `POST /api/v1/sync/key/import` accepts it; the CLI does the file I/O itself (`0600` on write), and the web UI's master-key card saves the key as a browser download and reads it back through an `<input type="file">`.

## Keeping two machines aligned

There is no background convergence and nothing watches for drift. If the two machines diverge, re-export and re-import in the direction you want — that manual step is the deliberate trade for dropping the machinery continuous sync needed.

A **Sync** settings panel in the web UI does both operations without the terminal (each button opens a directory picker backed by the daemon's `/api/v1/fs` browse helper), and the same operations are available over REST at `/api/v1/sync/*`.

[Credentials →](/guide/credentials)
