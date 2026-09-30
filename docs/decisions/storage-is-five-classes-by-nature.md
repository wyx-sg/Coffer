# Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy

**Status**: Proposed
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Control-Plane State Is One SQLite File, Written Only by the Daemon and Migrated Forward at Startup Through One Alembic Lineage](sqlite-alembic-persistence.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md), [Credentials Cross Machines Only as Ciphertext; the Master Key and the Push Token Never Enter the Repository](credentials-across-machines.md), [Resource Reach Is Machine-Local and Never Converges](resource-reach-is-machine-local.md), [Sync Withholds Derived Output; Each Machine Renders Its Own](sync-withholds-derived-output.md), [The Vault Converges With One User-Owned Git Remote, Git's Merge as Arbiter](vault-sync.md), [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Every Vault File Carries Its Own Format Version; One Owner Machine Commits Layout Upgrades](every-vault-file-carries-its-format-version.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [Reach Is a Machine-Local Predicate Over an Extensible Context](reach-is-a-machine-local-predicate-over-a-context.md), [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md), [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md), [Platform Differences Live Behind One Platform Port; Only macOS Ships](platform-differences-live-behind-one-platform-port.md), [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md), [Memory Reaches a Session at Three Moments: an Index at Start, Retrieval per Prompt, and a Guard Before a Known Trap](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md), [principles](../../docs-site/architecture/principles.md) (Persistence; Credentials; Single SQLite writer), spec vault-sync "Keep machine-local state out of the repository", spec vault-sync "Keep the working tree outside the vault", spec vault-sync "Carry secrets as ciphertext only", spec daemon "Deploy frozen sibling binaries and back up the vault before migrating", spec memory "Keep the memory tree derived and local"

## Context

Coffer's state is stored by **where the code that wrote it happened to put
it**, not by what it is. Today, under `~/.coffer/`:

| Location | What is there | Written by |
| --- | --- | --- |
| `coffer.db` | 17 ORM-mapped tables (`infrastructure/persistence/models.py` and the kinds' own models), plus the withdrawn workflow tables the lineage keeps: `resources`, `credentials`, `internal_engine_config`, `mcp_capability_preferences`, `channel_peers`, `skill_agent_bindings`, `mcp_server_health`, `retention_policies`, `sync_remotes`, `sync_convergence_state`, `sync_held_paths`, `sync_runs`, `audit_log`, `mcp_invocations`, `conversations`, `chat_messages`, `channel_thread_conversations` | daemon, 106 Alembic revisions (head `0106`) |
| `knowledge/`, `skills/` | Markdown collections, skill master folders | people, agents, the daemon |
| `memory/` | memory partitions | the daemon |
| `chat-media/`, `channel-media/`, `workspace/` | uploads, inbound media, the chat's default working directory | the daemon |
| `cache/agent/` | transcript summary cache | the daemon |
| `logs/` | the daemon log, rotated at 10 MB × 3 (`infrastructure/logging/setup.py:220`) | the daemon |
| `master.key` | the Fernet master key (`surfaces/http/secret_composition.py:99`) | the daemon |
| `daemon-config.json` | port, feature switches — read before the database opens (`infrastructure/daemon/config.py`) | the daemon |
| `daemon.json` | runtime port and per-start token, unlinked on exit | the daemon |
| `sync/` | the sync working tree (`DEFAULT_WORKTREE`, `domain/sync/backup.py:34`) | the sync round |

Inside `coffer.db`, rows of utterly different natures sit side by side: the
user's resource definitions (the only copy), this machine's reach
(`resources.enabled`, `resources.scope_json` — machine-local by decision), an
append-only audit log, a health cache that is rebuilt on every probe, and the
ciphertext of every secret. One file therefore has one backup answer, one
retention answer and one sync answer for all of them, and none of those
answers is right for every row.

Sync is where this costs most. Since the knowledge layer became files, the
vault's bulk content is already what git sees; the database is the exception,
and every database-held fact that should travel is **translated** into a file
and back: the exporter (`application/sync/exporter.py`, 221 lines), the
appliers (`appliers.py`, `appliers_read.py`, `appliers_resource.py`, 580),
the document projection (`domain/sync/serialization.py`, 165) and the
backwards-compatibility layer (`convergence_backwards.py`, 128) — 1,094 of
the sync package's 6,720 lines — plus 512 lines of per-kind `sync_state` /
`sync_reconcile` adapters. Each translation needs its own rules for what
*not* to carry: reach is left out by the exporter, derived output by a flag on
the kind and a literal path list (`NON_CONVERGING_TREE_PATHS`,
`infrastructure/sync/paths.py`), machine-local tables by omission. A rule that
lives in a translation is a rule a later translation can forget.

## Options Considered

### Option A — Five classes by nature, one directory each; sync is a policy per class (chosen)

Every piece of state is classified by what it **is** — who writes it, whether
it can be rebuilt, whether it is meaningful on another machine — and stored in
its class's directory. Whether a class converges is then a one-line policy of
the class, not a rule inside a translator.

| Class | Directory | Holds (today's source) | Writers | Sync policy | If lost |
| --- | --- | --- | --- | --- | --- |
| **vault** | `~/.coffer/vault/` — always a git repository | resource files with their uid (`resources`); skills; knowledge; capability toggles (`mcp_capability_preferences`); channel pairings (`channel_peers`); engine settings and the curation owner machine (`internal_engine_config`); a channel's `runs_on`; the machine descriptors; authored memory triggers under `vault/memory-triggers/`, one file per trigger; **credential ciphertext** under `vault/credentials/`, one file per ref, the file name being the opaque ref | people, sync, the daemon — every write validated ([Every Vault Write Is One Validated, Compare-and-Swap Commit](every-vault-write-is-a-validated-commit-naming-its-writer.md)) | converges with the user's remote when one is configured; `vault/credentials/` only when that remote's `include_credentials` is on (default off), and never through a three-way merge | the only copy of the user's configuration — not deletable, backed up by the remote when there is one |
| **local** | `~/.coffer/local/` | reach, per resource uid (`resources.enabled`, `resources.scope_json`); the sync remote (`sync_remotes`); held paths and the pending confirmation (`sync_held_paths`, `sync_convergence_state`); retention (`retention_policies`); `daemon-config.json` | the daemon, through its settings API | never — it is true of this machine only | settings can be set again |
| **content** | `~/.coffer/content/` | chat and channel media; the chat workspace | the service that owns each | not for now; a later decision may converge part of it | unrecoverable — needs a backup; retiring a machine asks export, migrate or discard |
| **runs** | `~/.coffer/runs.db` (+ `logs/`) | `audit_log`, `mcp_invocations`, `conversations`, `chat_messages`, `channel_thread_conversations`, `sync_runs`; later Run records and usage, with a `source` and a dedupe key reserved | the daemon, the only writer | never | history; pruned by retention anyway |
| **derived** | `~/.coffer/derived/` | the memory tree (`memory/`: partitions' `.raw/`, `notes/`, `MEMORY.md`, `RETIRED.md`), rebuilt from the agents' own memory; health (`mcp_server_health`), skill delivery bindings (`skill_agent_bindings`), the uid→path index, the transcript cache (`cache/agent/`), dependency probes, the rendered `coffer-guide` skill, the in-memory lexical index memory delivery ranks with, any future search index | the daemon | never | rebuilt; deleting the directory is always safe |

The **master key** belongs to no directory: it lives in the OS credential store — the macOS Keychain on the shipped platform, reached through the platform port — never as a file under `~/.coffer/` ([The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md)). It never syncs, and it cannot be set again: without it every ciphertext is unreadable, so it must be exported as an explicit backup (`coffer sync key export`) or imported from another machine.

`daemon.json` stays where it is: it is not stored state but the rendezvous
every surface reads to find the running daemon, and it is unlinked on exit.

Rules that come with the classes:

- **The directory is the policy.** Nothing outside `vault/` can reach the
  remote, because the sync round commits and pushes only the vault repository.
  "Reach never travels" becomes a fact about where reach is stored, not a line
  the exporter must remember to omit.
- **Ciphertext lives in the vault; the key lives in the OS credential store.** With
  `include_credentials` off, `vault/credentials/` is excluded from every
  commit (a path filter in the repository's own `info/exclude`, never a
  tracked `.gitignore` another machine could change); with it on, the subtree
  is committed but settled by the fresher-encryption rule, never a text merge
  ([Credentials Cross Machines Only as Ciphertext](credentials-across-machines.md)).
  Ciphertext that has entered a pushed commit cannot be withdrawn; revoking it
  means rotating the secret.
- **Derived is never the only copy of anything.** A consumer that finds
  `derived/` empty rebuilds it; a writer that would put an only copy there is a
  defect.
- **Memory is derived, not content.** The canonical copy of what an agent
  learned is that agent's own native memory, which Coffer only reads
  ([Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md));
  the tree under `memory/` is its distillation, and spec memory "Keep the
  memory tree derived and local" already requires that deleting it and
  re-running aggregation and distil gives back an equivalent partition. The
  rebuild needs Coffer's internal model for the same wording quality, and a
  lesson whose source the agent itself has since deleted does not come back,
  which is the agent's retirement, not a loss. The one thing a person writes
  about memory — a trigger that guards a known trap
  ([Memory Reaches a Session at Three Moments](memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md))
  — is authored, so it is vault, not derived.
- **runs.db keeps the single-writer rule** of
  [Control-Plane State Is One SQLite File](sqlite-alembic-persistence.md): WAL,
  one Alembic lineage, the daemon the only process that opens it.

Pros: backup, retention, cleanup and sync each get one answer per class;
sync stops translating (the vault already *is* files); "machine-local" and
"rebuildable" become properties a reader can see in the directory listing;
Settings › Data can offer "clear derived" and "export local" as the safe
actions they are.

Cons: one migration that moves every table and tree of a running product, with
a rollback that must be rehearsed
([Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md));
the vault loses the database's transactions and foreign keys, so cross-file
references by uid are checked by validation rather than by SQLite; two
engines (git files and SQLite) instead of one.

It wins because it removes the translation layer rather than maintaining it,
and because every recurring sync defect in the Context was a rule about *what
not to carry* living in the wrong place.

### Option B — Keep one SQLite system of record and serialize to files for sync (today)

The database stays the truth for configuration; sync keeps exporting it into a
working tree and applying diffs back
([The Vault Converges With One User-Owned Git Remote](vault-sync.md)).

- **Pros.** Transactions and foreign keys across a resource and its
  dependents; no data migration; the design every current guard was built
  against.
- **Cons.** The 1,094 + 512 translation lines stay, and so does the class of
  bug they breed: a projection that disagrees with its source (the reason the
  first sync design was retired), a field forgotten by the exporter, a derived
  row published by accident. A person cannot edit configuration as a file,
  which v0.4's product goal requires. And the sqlite-alembic ADR's own reason
  for rejecting files (its Option E) — "no transactions, no foreign keys, no
  indexed queries over the audit and invocation logs" — applies to the
  **logs**, which stay in SQLite under Option A, not to a few dozen small
  documents.
- **Why it loses.** It keeps the mechanism that makes sync expensive and
  keeps configuration un-editable.

### Option C — One `~/.coffer/` tree under git, with ignore rules deciding what syncs

Make the whole home one repository and list machine-local and derived paths
in `.gitignore`.

- **Pros.** One directory, one repository, no moves between classes.
- **Cons.** "Never synced" becomes an ignore line: a tracked `.gitignore`
  arrives from other machines, a user's `git add -f` or a mistaken rule
  publishes the reach of every resource or the sync remote's settings, and
  nothing structural prevents it. SQLite files under WAL would sit inside a working
  tree git keeps statting and diffing.
- **Why it loses.** It makes "never synced" — the property machine-local
  state depends on — a text file that syncs.

### Option D — Two classes: synced and not synced

A vault directory and one local store for everything else.

- **Pros.** Fewer directories; the only distinction sync cares about.
- **Cons.** It merges three different answers into one. Reach and the master
  key must *never* travel; media and the chat workspace do not travel *yet* but are the
  user's only copy and may converge later; health and bindings can be deleted
  at any time. A user clearing "local data" would delete media with the cache;
  a later decision to converge media would have to split the class.
- **Why it loses.** The distinctions it erases are the ones backup and
  cleanup need.

### Option E — Configuration as files, but secrets stay in a SQLite table

Move everything as Option A except the `credentials` table.

- **Pros.** No change to the credential store's storage; the envelope design
  is untouched.
- **Cons.** Sync would still need a translator for ciphertext
  (`infrastructure/sync/secret.py` reading and writing rows), which is
  the last piece of the translation layer; the vault would not be complete on
  its own, so "the remote can be rebuilt from any one machine" would need the
  database too.
- **Why it loses.** Ciphertext is safe to hold as files — it is exactly what
  already crosses the remote at `credentials/<ref>.enc` — and keeping it in a
  table keeps one translator alive for no protection gained. The protection is
  the key's location, which Option A keeps outside the tree, in the OS
  credential store.

## Decision

Coffer's state is stored in five classes by nature — **vault**, **local**,
**content**, **runs**, **derived** — each in its own directory under
`~/.coffer/`, with the contents, writers, sync policy and loss consequence in
the table above. The vault is always a git repository. Credential ciphertext
lives in `vault/credentials/`, one file per ref; it is committed only when the
remote's `include_credentials` is on (default off) and is never three-way
merged. The master key lives in the OS credential store (the macOS Keychain on the
shipped platform, behind the platform port), never in a file under
`~/.coffer/`; it never syncs, and must be exported to survive the loss of the
machine.

Rules a future change must respect:

- New state is classified before it is stored; its class decides its
  directory, and its directory decides whether it can travel.
- Nothing machine-local is written under `vault/`; nothing that is the only
  copy is written under `derived/`.
- `runs.db` has one writer, the daemon.

## Consequences

- **Revises** [Control-Plane State Is One SQLite File](sqlite-alembic-persistence.md):
  SQLite remains the engine for `runs.db`, with its pragmas, single writer and
  forward-only Alembic lineage; it stops being the system of record for
  configuration. The principles' Persistence clause, its Credentials clause
  ("only as Fernet ciphertext in the `credentials` table") and the "Single
  SQLite writer" guarantee (which names `coffer.db`) are amended in the same
  change, and [Envelope-Encrypted Credential Store](envelope-encrypted-credential-store.md)
  is revised to store ciphertext as files; where its key lives is revised
  by [The Master Key Lives in a Keychain Access Group Only Coffer's Signed Binaries Can Read; Secrets Stay Envelope-Encrypted in the Vault](master-key-lives-in-the-macos-keychain.md).
- The exporter, the appliers, the document projection and the
  backwards-compatibility layer are deleted with the sync rework
  ([Sync Only Pulls and Pushes the Vault Repository](sync-applies-clean-merges-and-stops-on-any-conflict.md)).
  `NON_CONVERGING_TREE_PATHS` goes with them: `coffer-guide` renders into
  `derived/` and is delivered from there.
- The move is one migration, backed up and rehearsable, with the old database
  kept read-only for one version; its rules are in
  [Every Vault File Carries Its Own Format Version](every-vault-file-carries-its-format-version.md).
  Reach moves to `local/` in the same migration, in its new shape, so it moves
  once ([Reach Is a Machine-Local Predicate Over an Extensible Context](reach-is-a-machine-local-predicate-over-a-context.md)).
- A symlink a user made from an agent's own memory directory into
  `~/.coffer/memory/` would dangle after memory moves to `derived/`; Coffer
  does not create such links (nothing in `application/memory/` or
  `infrastructure/memory/` does), so the migration reports any it finds and
  the reconciler can check them afterwards.
- **Obligations.** A cross-cutting `vault-storage` spec; `data-model.md`
  rewritten to describe file formats; the docs-site persistence, vault-sync and
  filesystem reference pages rewritten; Settings › Data regrouped by class; an
  AST or path gate that `derived/` is never read as the only source of a
  fact.
