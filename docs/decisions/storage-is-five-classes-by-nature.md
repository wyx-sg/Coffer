# Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy

> **Superseded in part (2026-10-04).** The change `move-agent-sessions-to-terminal` removed the web chat and Coffer's copy of conversation text. The `runs` class no longer holds `chat_messages` or `chat_reply_files`; `conversations` is an index of channel conversations with no text. The five-class decision is unchanged.

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [History Is One SQLite File, `runs.db`, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](history-is-one-sqlite-file-written-only-by-the-daemon.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Secrets Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](secrets-cross-machines-only-as-ciphertext.md), [Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md), [Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [principles](../../docs-site/architecture/principles.md) (Persistence; Secrets; Single SQLite writer), [Persistence](../../docs-site/architecture/persistence.md), spec vault-sync "Keep machine-local state out of the repository", spec vault-storage "Store state in five classes by nature", spec vault-sync "Carry secrets as ciphertext only", spec daemon "Deploy frozen sibling binaries and back up the history database before migrating"

## Context

State has to be stored by what it **is**, not by where the code that wrote it
happened to put it. Coffer's state has five natures:

- **The user's configuration and authored content** — resource definitions,
  skills, knowledge, the memory hub, state documents, the ciphertext of
  secrets. It must be
  complete on every machine that wants it, editable with the user's own tools,
  versioned, and able to travel.
- **Facts about this machine only** — which agents a resource reaches here, the
  sync remote, retention, the secret boundary's approvals. They must never
  travel, and can be set again if lost.
- **Media and the chat workspace** — the user's only copy, large, not worth
  syncing yet.
- **History** — the audit log, conversations, invocations, usage. Append-only,
  time-ordered, pruned, never meaningful on another machine.
- **Derived state** — health checks, caches, the rendered `coffer-guide`
  skill. It can be rebuilt from the rest.

One undifferentiated store gives all of them one backup answer, one retention
answer and one sync answer, and none of those answers is right for every kind.
Before this decision they sat in one SQLite file, `coffer.db`, beside file
trees for knowledge and skills: the user's resource definitions (the only
copy), this machine's reach, an append-only audit log, a health cache rebuilt
on every probe, and the ciphertext of every secret, row by row.

Sync is where this cost most. Every database-held fact that should travel had
to be **translated** into a file and back by an exporter, a set of appliers, a
document projection and a backwards-compatibility layer — over a thousand lines
of sync code — plus per-kind adapters. Each translation needed its own rules for
what *not* to carry: reach was left out by the exporter, derived output by a flag
on the kind and a literal path list, machine-local tables by omission. A rule
that lives in a translation is a rule a later translation can forget.

## Options Considered

### Option A — Five classes by nature, one directory each; sync is a policy per class (chosen)

Every piece of state is classified by what it **is** — who writes it, whether
it can be rebuilt, whether it is meaningful on another machine — and stored in
its class's directory (`infrastructure/vault/home.py` is the one module that
names them; `scripts/check_coffer_paths.py` fails the build on a `".coffer"`
path built anywhere else). Whether a class converges is then a one-line policy
of the class, not a rule inside a translator.

| Class | Directory | Holds | Writers | Sync policy | If lost |
| --- | --- | --- | --- | --- | --- |
| **vault** | `~/.coffer/vault/` — always a git repository | resource files with their uid (`resources/<kind>/`); skills; knowledge; the memory hub (`memory/`, one file per memory an agent learned); state documents (an MCP server's switched-off capabilities and Coffer's own settings); machine descriptors; **secret ciphertext** under `secret/`, one file per ref, the file name being the opaque ref | people, sync, the daemon — every write validated ([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)) | converges with the user's remote when one is configured; `secret/` only when that remote's `include_secret` is on (default off), and never through a three-way merge | the only copy of the user's configuration — not deletable, backed up by the remote when there is one |
| **local** | `~/.coffer/local/` | reach, per resource uid (`reach.json`); machine-local resources (the agents, and the channels under `resources/channel/`, with their pairings in `channel-peers.json`, keyed by channel uid — see [Channels Are Machine-Local Resources, Like Agents](channels-are-machine-local-resources.md)); the sync remote and a stopped round's choices; retention; the secret boundary's approvals and bindings; machine-local ciphertext; the record of the one-time upgrade; what the memory sync wrote into this machine's agents (`memory-sync.json`) | the daemon, through its settings API and the memory sync | never — it is true of this machine only | settings can be set again |
| **content** | `~/.coffer/content/` | chat and channel media; the chat workspace; skill folders Coffer set aside (`backup/skills/`) | the service that owns each | not for now; a later decision may converge part of it | unrecoverable — needs a backup |
| **runs** | `~/.coffer/runs.db`, `~/.coffer/skill-data/<skill-name>/`, and `~/.coffer/config-backups/<file>/` | `audit_log`, `mcp_invocations`, `conversations`, `chat_messages`, channel threads and outbox, `sync_runs`, usage; in `skill-data/`, the logs, operation journals and temp files a skill's scripts write; in `config-backups/`, copies of agent config files made before a rewrite | the daemon, the only writer of `runs.db`; a skill's scripts, of `skill-data/`, and `config-backups/` | never | history; pruned by retention anyway (`skill-data/` by the `skill_data` policy and `config-backups/` by the `config_backups` policy, files by mtime; each config file's newest backup is kept) |
| **derived** | `~/.coffer/derived/` | `derived.db` (MCP server health, skill delivery bindings, capability first/last seen), the rendered `coffer-guide` skill, derived resource files, editor copies of a stopped round's conflicts, price lists | the daemon | never | rebuilt; deleting the directory is always safe |

The **master key** belongs to no class directory: on the shipped platform it
lives in the macOS Keychain, reached through the platform port
([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md)),
and a development build keeps it in a `0600` file, `~/.coffer/master.key`. It
never syncs, and it cannot be set again: without it every ciphertext is
unreadable, so it is exported only as the desktop app's passphrase-protected
backup (Settings › Security) and installed on another machine with
Settings › Security › **Import a master key**. There is no CLI export, because an agent could run it.

The runtime files directly under `~/.coffer` — `daemon.json` (the rendezvous
every surface reads to find the running daemon, unlinked on exit),
`daemon-config.json` (the port the daemon binds and the feature switches, read
before any migration can run), the model proxy's files, the logs, the deployed
binaries — are not stored state of any class.

Rules that come with the classes:

- **The directory is the policy.** Nothing outside `vault/` can reach the
  remote, because the sync round commits and pushes only the vault repository.
  "Reach never travels" is a fact about where reach is stored, not a line an
  exporter must remember to omit.
- **Ciphertext lives in the vault; the key lives in the OS credential store.**
  With `include_secret` off, `vault/secret/` is excluded from every commit (a
  path filter in the repository's own `info/exclude`, never a tracked
  `.gitignore` another machine could change); with it on, the subtree is
  committed but settled by the fresher-encryption rule, never a text merge
  ([Secrets Cross Machines Only as Ciphertext](secrets-cross-machines-only-as-ciphertext.md)).
  Ciphertext that has entered a pushed commit cannot be withdrawn; revoking it
  means rotating the secret.
- **Derived is never the only copy of anything.** A consumer that finds
  `derived/` empty rebuilds it (`derived.db` is deleted and created again when
  its schema version differs, never migrated); a writer that would put an only
  copy there is a defect.
- **Memory is vault content, not derived.** What the person's agents learned
  is kept in the memory hub, `vault/memory/`, one file per memory, and
  synced like any other vault content. It cannot be rebuilt on one machine:
  each entry is read from the native memory of an agent on the machine where
  it was learned, so the hub is the only place another machine finds it. The
  copies each machine writes into its own agents are made from the hub, and
  the record of what it wrote, `local/memory-sync.json`, is true of that
  machine only
  ([Sync Memory Into Each Agent's Own Memory](sync-memory-into-each-agents-own-memory.md)).
- **`runs.db` keeps the single-writer rule** of
  [History Is One SQLite File](history-is-one-sqlite-file-written-only-by-the-daemon.md):
  WAL, one Alembic lineage, the daemon the only process that opens it.

Pros: backup, retention, cleanup and sync each get one answer per class;
sync stops translating (the vault already *is* files); "machine-local" and
"rebuildable" become properties a reader can see in the directory listing;
deleting `derived/` is the safe action it looks like.

Cons: the vault loses the database's
transactions and foreign keys, so cross-file references by uid are checked by
validation rather than by SQLite; two engines (git files and SQLite) instead of
one.

It wins because it removes the translation layer rather than maintaining it,
and because every recurring sync defect in the Context was a rule about *what
not to carry* living in the wrong place.

### Option B — Keep one SQLite system of record and serialize to files for sync (the design this replaced)

The database stays the truth for configuration; sync exports it into a working
tree and applies diffs back.

- **Pros.** Transactions and foreign keys across a resource and its
  dependents; no data migration; the design every guard of the first sync was
  built against.
- **Cons.** The translation code stays, and so does the class of bug it
  breeds: a projection that disagrees with its source (the reason the first
  sync design was retired), a field forgotten by the exporter, a derived row
  published by accident. A person cannot edit configuration as a file, which
  the product's goal requires. And the usual reason to reject files —
  no transactions, no foreign keys, no indexed queries over the audit and
  invocation logs — applies to the **logs**, which stay in SQLite under
  Option A, not to a few dozen small documents.
- **Why it loses.** It keeps the mechanism that makes sync expensive and keeps
  configuration un-editable.

### Option C — One `~/.coffer/` tree under git, with ignore rules deciding what syncs

Make the whole home one repository and list machine-local and derived paths
in `.gitignore`.

- **Pros.** One directory, one repository, no moves between classes.
- **Cons.** "Never synced" becomes an ignore line: a tracked `.gitignore`
  arrives from other machines, a user's `git add -f` or a mistaken rule
  publishes the reach of every resource or the sync remote's settings, and
  nothing structural prevents it. SQLite files under WAL would sit inside a
  working tree git keeps statting and diffing.
- **Why it loses.** It makes "never synced" — the property machine-local
  state depends on — a text file that syncs.

### Option D — Two classes: synced and not synced

A vault directory and one local store for everything else.

- **Pros.** Fewer directories; the only distinction sync cares about.
- **Cons.** It merges three different answers into one. Reach and the master
  key must *never* travel; media and the chat workspace do not travel *yet* but
  are the user's only copy and may converge later; health and bindings can be
  deleted at any time. A user clearing "local data" would delete media with the
  cache; a later decision to converge media would have to split the class.
- **Why it loses.** The distinctions it erases are the ones backup and
  cleanup need.

### Option E — Configuration as files, but secrets stay in a SQLite table

Move everything as Option A except the table of secrets.

- **Pros.** No change to the secret store's storage; the envelope design is
  untouched.
- **Cons.** Sync would still need a translator for ciphertext, reading and
  writing rows, which is the last piece of the translation layer; the vault
  would not be complete on its own, so "the remote can be rebuilt from any one
  machine" would need the database too.
- **Why it loses.** Ciphertext is safe to hold as files — it is exactly what
  already crosses the remote at `secret/<ref>.enc` — and keeping it in a table
  keeps one translator alive for no protection gained. The protection is the
  key's location, which Option A keeps outside the tree, in the OS credential
  store.

## Decision

Coffer's state is stored in five classes by nature — **vault**, **local**,
**content**, **runs**, **derived** — each in its own directory under
`~/.coffer/`, with the contents, writers, sync policy and loss consequence in
the table above. The vault is always a git repository. Secret ciphertext lives
in `vault/secret/`, one file per ref; it is committed only when the remote's
`include_secret` is on (default off) and is never three-way merged. The master
key lives in the OS credential store (the macOS Keychain on the shipped
platform, behind the platform port), or in a `0600` file in a development build;
it never syncs, and must be exported to survive the loss of the machine.

Rules a future change must respect:

- New state is classified before it is stored; its class decides its
  directory, and its directory decides whether it can travel.
- Nothing machine-local is written under `vault/`; nothing that is the only
  copy is written under `derived/`.
- `runs.db` has one writer, the daemon.

## Consequences

- SQLite remains the engine for `runs.db` only, with its pragmas, single writer
  and forward-only Alembic lineage; it is not the system of record for
  configuration. The principles' Persistence clause, its Secrets clause
  (ciphertext as files under the vault) and the "Single SQLite writer"
  guarantee (which names `runs.db`) say so.
- The exporter, the appliers, the document projection and the
  backwards-compatibility layer of the earlier sync are gone
  ([Sync Only Pulls and Pushes the Vault Repository](sync-applies-clean-merges-and-stops-on-any-conflict.md)),
  and so is the literal list of paths sync must not carry: `coffer-guide`
  renders into `derived/` and is delivered from there.
- Reach is in `local/`, stored once in its own shape
  ([Reach Is Machine-Local](reach-is-machine-local-stored-by-uid-never-synced.md)).
- `daemon-config.json` stays directly under `~/.coffer`, not under `local/`: it
  carries the port the daemon binds and is read before any migration can run, so
  it cannot sit in a directory the migration creates.
- The Overview's dismissed attention items (`attention_ignores`) stay in
  `runs.db` rather than `local/`.
- Not built yet: a gate (an AST or path check) that `derived/` is never read as
  the only source of a fact. The rule is held by review and by the spec scenario that
  deletes `derived/` and expects it rebuilt.
