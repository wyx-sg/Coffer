# Data Model — Vault Storage

Where every piece of Coffer's state lives, the shape of the documents Coffer
parses in the vault, and what every vault commit says about itself. Each kind's
own documents and tables are that kind's spec's; this is the frame they sit in.
The decisions are the ADRs
[storage-is-five-classes-by-nature](../../../docs/decisions/storage-is-five-classes-by-nature.md),
[identity-is-the-uid-inside-the-file](../../../docs/decisions/identity-is-the-uid-inside-the-file.md),
[every-vault-file-carries-its-format-version](../../../docs/decisions/every-vault-file-carries-its-format-version.md)
and
[every-vault-write-is-a-validated-commit-naming-its-writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md).

## The five classes

State is stored by what it **is**; the class decides the directory, and the
directory decides whether it can travel (`StorageClass`, `domain/vault/layout.py`;
the roots are resolved from `HOME` at every call by `infrastructure/vault/home.py`,
with no per-tree override, and `coffer path logs` prints the log directory).

| Class | Directory | What | Travels |
| --- | --- | --- | --- |
| vault | `~/.coffer/vault/` | the user's configuration and content — the only copy | a git repository from first use; committed, and pushed when a sync remote is set |
| local | `~/.coffer/local/` | what is true of this machine only: agents, reach, the sync remote, retention, the secret boundary | never committed or pushed; can be set again |
| content | `~/.coffer/content/` | media and the chat workspace — the user's only copy | not synced |
| runs | `~/.coffer/runs.db` (+`-wal`/`-shm`) | append-only history | never synced; pruned by retention |
| derived | `~/.coffer/derived/` | rebuilt from other state | never; deleting it is always safe |

```
~/.coffer/
  vault/
    manifest.json                          {"schema_version": 3}
    resources/<kind>/<name>.json           mcp_server, skill, channel, provider, knowledge
    state/mcp-preferences/<server>.json    state/channel-peers/<channel>.json
    state/settings/internal-engine.json
    knowledge/<collection>/...
    skills/<name>/...                      skill master folders
    secret/<ref>.enc                       Fernet ciphertext
    machines/<machine id>.json             one descriptor per machine
    .git/                                  info/exclude, tags coffer/pre-apply/<time>
  local/
    resources/agent/<name>.json
    reach.json  tool-reach.json  engine.json  retention.json  curation.json
    skill-source-status.json
    secret/<ref>.enc                       machine-local ciphertext (proxy tokens)
    secret-boundary/{bindings,approvals,settings,times,last-used}.json
    sync/{remote,round}.json
  content/
    chat-media/  channel-media/  workspace/
    backup/skills/                         folders set aside from an agent's link path
  derived/
    derived.db                             mcp_server_health, mcp_capability_seen, skill_agent_bindings
    resources/memory/<name>.json  resources/skill/coffer-guide.json
    memory/  skills/coffer-guide/  cache/agent/  sync-conflicts/
    reported-prices.json  genai-prices.json
  runs.db                                  audit_log, mcp_invocations, conversations, chat_messages,
                                           channel_thread_*, channel_outbox, sync_runs, usage_*
```

`daemon-config.json` and `daemon.json` stay directly under `~/.coffer`, outside
every class: the first is read before any migration can run, the second is the
rendezvous every surface reads (spec daemon).

| Kind | `Kind.storage` | Resource files under |
| --- | --- | --- |
| `mcp_server`, `skill`, `channel`, `provider`, `knowledge` | `vault` | `vault/resources/<kind>/` |
| `agent` | `local` | `local/resources/agent/` |
| `memory` | `derived` | `derived/resources/memory/` |
| `skill` `coffer-guide` (`Kind.storage_row`) | `derived` | `derived/resources/skill/` |

## Inside the vault: areas

Every vault path belongs to one **area** — the unit the deletion breaker counts
in and the Sync page groups by (`area_of`): the first path segment, except that
`resources/<kind>/` and `state/<area>/` are areas of their own. `machines/` and
`manifest.json` are the registry and are never counted as vault content. The
top-level directories are `resources`, `state`, `knowledge`, `skills`,
`secret` and `machines`; anything else a person puts there
is kept and committed but belongs to no area Coffer reads.

`vault/.git/info/exclude` — never a tracked `.gitignore` another machine could
change — keeps out editor and system litter (`.DS_Store`, `.*.tmp`, `.*.swp`,
`*~`, `.#*`, `__pycache__/`, `*.py[co]`), every hidden entry under `knowledge/`
except `.inbox`, and `/secret/` unless the sync remote has `include_secret`.

### `manifest.json`

```json
{
  "schema_version": 3
}
```

The one vault-wide number left: the **layout**. A sync round refuses a remote
whose manifest names a newer layout (`remote_too_new`) and replaces one at an
older layout with this vault (never converting it), and
`3` is what makes a build from before per-file versions refuse the file layout
rather than misread it.

## Documents Coffer parses

Resource files, state documents and machine descriptors are **JSON objects**
(`domain/vault/document.py`): 2-space indent, a trailing newline, keys in the
order the file already had them. Knowledge documents and skill files
are carried as bytes, not parsed as vault documents.

- **Unknown top-level keys are kept.** A reader validates the keys it knows
  and carries every other top-level key verbatim, in place; a write puts them
  back where they were. They are reported as warnings, never refused.
- **A resource's `config` holds only what its kind declares.** Every kind's
  config model refuses a key it does not declare (`extra="forbid"`), and the
  vault's resource rule does the same for a file: one `config_invalid` finding
  per unknown key, whether the file was edited by hand or brought by a sync
  merge. The kind's name rule (`validate_name`) is applied to every change of
  the file as well, and a `title` on a kind with `titled` false is refused.
- **The encoding is deterministic.** The same document always encodes to the
  same bytes, so a write that changes nothing makes no commit and two machines
  writing the same value do not conflict.
- **No `updated_at`.** Two machines stamping it would conflict on every edit;
  git knows when a file changed.

### Resource document — `resources/<kind>/<name>.json`

| Key | Required | Notes |
| --- | --- | --- |
| `uid` | — | the identity; absent only on a hand-made file until the daemon mints one. An opaque id `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`; minted as `uuid4().hex` |
| `kind` | yes | non-empty; must match the directory it sits in |
| `format_version` | — | positive integer; absent reads as `1` |
| `format_compat` | — | written only when the file's format is newer than the oldest version that can read it |
| `name` | yes | non-empty; unique within its kind |
| `title` | — | written only when set |
| `description` | — | always written, `null` when empty |
| `config` | yes | an object; the kind's own schema. Strings under the writing machine's home are `${HOME}/...` |
| `created_at` | — | ISO time |

`enabled` and scope are **not** in the file: reach is `local/reach.json`.
`updated_at` is the file's modification time on this machine; no revision counter
and no uid index is kept. The fields and both stores are spec resource-framework's data model.

**Identity is the uid inside the file.** Nothing keys on the path: a person may
move or rename the file and it is the same resource. A file without a `uid`
gets one in a `daemon` commit (operation `mint-uid`) right after the person's.
A second file claiming a uid that `HEAD` already holds at another path is
refused (`duplicate_uid`) and flagged; a second resource of one kind with a
taken name is refused (`name_taken`).

### State document — `state/<area>/<name>.json`

State that belongs to a resource without being part of it, one document per
owner, named after the owner and found by the owner's uid inside. The
resource store moves or deletes the document in the owner's own commit when the
owner is renamed or deleted. Only one document per owner is admitted.

| Area | Owner key | Own keys | Spec |
| --- | --- | --- | --- |
| `mcp-preferences` | `server_uid` | `disabled` — `{capability_type: [key, ...]}` | mcp-gateway |
| `channel-peers` | `channel_uid` | `peers` — `[{chat_id, sender_id, display_name, paired_at}]` | channels |
| `settings` (`internal-engine.json` only) | — | `model`, `curate_owner_machine_id`, `model_timeout_s`, `transcribe_model`, `upkeep` | internal-engine |

Every state document carries `format_version` (1). A key this build does not
know is a warning; an area it does not know is accepted as it is.

### Machine descriptor — `machines/<machine id>.json`

`format_version`, `machine_id`, `name`, `os`, `hostname`, `coffer_version`,
`last_round_at`, `last_converged_commit`, `key_fingerprint`,
`agents[{type, name, plugins[]}]` — spec vault-sync's data model.

## Format versions

Every parsed vault document carries an integer `format_version` for its own
kind (`domain/vault/formats.py`). A kind declares its current version and a
chain of pure upgrade steps `vN → vN+1`, each **additive** (only new optional
fields) or **breaking**. How a build treats a file:

| Status | When | What this build does |
| --- | --- | --- |
| `current` | the file's version is this build's | read and write it |
| `older` | below | read it through the upgrade chain in memory; an ordinary write never rewrites it at the new version (that is the owner machine's layout commit), so an edit to it is refused (`older_format_edit`) |
| `newer_readable` | above, and `format_compat` ≤ this build's version | read it, keep the fields it does not know, never write, delete or reconcile it (`newer_format_read_only`, a warning) |
| `newer_unreadable` | above, and no `format_compat` or one above this build's | keep the last valid version and flag the file (`newer_format`) |

A document that never names `format_compat` is breaking by default. Every
resource, state and descriptor format is at 1 today.

## The one write path

Every accepted write to the vault — a Coffer operation, a person's hand edit
once found, a sync round's merge, a restore — goes through the process's one
`VaultWriter` (`infrastructure/vault/writer.py`): the vault lock, a
compare-and-swap on what the write expects the file to hold (an expected
fingerprint — sha256 of the bytes read —, `ABSENT`, or `HEAD`: no unsettled hand
edit in the way), an atomic rename, validation, and **one commit per
operation**. A stale expectation is `VAULT_FILE_STALE` (409). The content APIs
(skill file save, knowledge save, vault restore) require `expected_fingerprint`.

The effective version of every vault file is the one at `HEAD`. A person's edit
is **found, not intercepted**: file-system events are a hint, debounced until
the changed paths are quiet for one second, and a scan every 60 seconds plus one
at boot asks git which files differ from `HEAD`. A valid edit is committed as a
`disk` write (audited `vault_file_edited`, actor `human`). An invalid one stays
in the working tree, uncommitted: it is on the attention list and
`GET /api/v1/vault/problems` / `coffer vault problems`, and `HEAD` stays in
effect. The problems list is held in the daemon's memory and rebuilt by the
next scan.

Validation findings (`domain/vault/findings.py`) stop the commit, except the
three warnings `unknown_field`, `newer_format_read_only` and
`dangling_reference`. The other codes: `invalid_document`, `missing_field`,
`kind_mismatch`, `duplicate_uid`, `name_taken`, `config_invalid`,
`newer_format`, `older_format_edit`, `secret_in_file`. A kind's
`exclusive_flags` are checked on every commit, so a merge that would leave two
holders is refused.

### Commit trailers

The author is `Coffer (<writer>)`; the message is a one-line summary, a blank
line, and one trailer per field set (`domain/vault/writers.py`). A commit with
no `Coffer-Writer` trailer — a person's own `git commit` in the vault — reads
as a `disk` write.

| Trailer | Value |
| --- | --- |
| `Coffer-Writer` | `user` (a person through a Coffer surface) · `disk` (found on disk: an editor, a shell, an agent's own file tools, a hand commit) · `agent` (an agent through a Coffer tool) · `daemon` (the daemon on its own account: a minted uid, a machine descriptor, the layout commit) · `curation` · `sync` (a round's merge) |
| `Coffer-Operation` | what the commit did: `create`, `update`, `delete`, `rename`, `edit`, `restore`, `mint-uid`, `layout`, `sync`, `baseline`, and each kind's own words |
| `Coffer-Actor` | the audit actor of the operation |
| `Coffer-Agent` | the agent, when the writer is `agent`; for a curation pass, the author of the item it curated |
| `Coffer-Machine` | the machine id that made the commit |
| `Coffer-Restored-From` | for a restore, the commit restored from |
| `Coffer-Layout` | for a layout commit, the layout move it made (`<from> -> <to>`) |

The knowledge history adds `Coffer-Collection`, `Coffer-Item`, `Coffer-Status`
and `Coffer-Undoes` (spec knowledge). A history row shows the writer as
`agent:<type>` for an agent.

### History, diff and restore

Any vault file or folder: `GET /api/v1/vault/{history,diff,content,changes,problems}`,
`POST /api/v1/vault/restore`; the CLI keeps only `coffer vault problems`.
A restore is a new commit through the same checks, carrying
`Coffer-Restored-From` and audited `vault_file_restored`; a folder restore
removes files the version did not have. `secret/` is refused
(`VAULT_PATH_INVALID`, 400) for content, diff and restore.

## Local state files

Each file under `local/` is one JSON object (`JsonStore`,
`infrastructure/vault/json_store.py`): read whole, changed under a per-file
lock, written back atomically. A missing file reads as the empty object; a file
that does not parse is moved aside as `<name>.unreadable-<n>` and read as
empty, because local state can be set again.

| File | Shape | Spec |
| --- | --- | --- |
| `reach.json` | `{uid: {enabled, agents: [uid] \| null, projects: null}}` | resource-framework |
| `tool-reach.json` | `{group uid: {tool: [agent uid]}}` | mcp-gateway |
| `engine.json` | `{updated_at}` | internal-engine |
| `retention.json` | `{table: {retention_days, last_pruned_at, last_pruned_rows, updated_at}}` | resource-framework |
| `curation.json` | `{documents: {relpath: {blob, at}}}` | knowledge |
| `skill-source-status.json` | `{skill uid: {checked_at, last_success_at, error, latest_commit, commits_ahead, files_changed, dismissed_commit}}` | skill-manager |
| `secret-boundary/*.json` | bindings, approvals, settings, first-stored times, last-used times | secret |
| `sync/remote.json`, `sync/round.json` | the remote; the round waiting for a person | vault-sync |

## `derived/derived.db`

Three tables of observations this machine can make again
(`infrastructure/persistence/derived_db.py`): `mcp_server_health`,
`mcp_capability_seen` (spec mcp-gateway) and `skill_agent_bindings` (spec
skill-manager). No Alembic lineage: the schema is created at open, and a file
whose `PRAGMA user_version` is not `SCHEMA_VERSION` (1) is deleted and created
again rather than migrated.

## `runs.db`

The history database, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another:
one Alembic lineage, single writer. The lineage starts at one baseline revision,
`0146`, that creates the whole schema; every later revision stacks on it and
carries a working `downgrade()`. Every row that names a resource names it by
uid — `resource_uid`, `skill_uid`, `agent_uid`; there is no integer resource
id.
