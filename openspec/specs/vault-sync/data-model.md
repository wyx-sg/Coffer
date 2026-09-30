# Data Model — Vault Sync

Sync owns no copy of the vault. The vault is already a git repository
(`~/.coffer/vault/`, spec vault-storage), and a sync round only merges its
commits with one remote's. What sync itself persists is small, and where each
piece lives is the design:

| Where | What | Class |
| --- | --- | --- |
| `~/.coffer/local/sync/remote.json` | the one remote this machine syncs with | local — which remote *this machine* uses is a fact about it |
| `~/.coffer/local/sync/round.json` | the round waiting for a person: its stop or hold, the join choices, the confirmations | local |
| `~/.coffer/vault/machines/<machine id>.json` | one descriptor per machine | vault — committed and pushed like any other vault file |
| `~/.coffer/vault/.git` tags `refs/tags/coffer/pre-apply/<time>` | the snapshot before each apply | vault repository, never pushed |
| `~/.coffer/derived/sync-conflicts/<path>` | the editor copies of a stopped round's conflicting files | derived |
| `runs.db` `sync_runs` | every round this machine ran | runs |

There is no pointer of its own and no retry set: the last commit this machine
converged at is the vault's own history (and its descriptor's
`last_converged_commit`), and a round that cannot apply stops whole instead of
leaving some paths behind. In the one-time upgrade to the vault layout the old
remote row was carried to `local/sync/remote.json` and Alembic revision 0117
dropped `sync_remotes`, `sync_convergence_state` and `sync_held_paths` and
emptied `sync_runs`.

## `local/sync/remote.json`

`SyncRemote` (`domain/sync/remote.py`), written whole by `JsonRemoteStore`
(`infrastructure/sync/local_state.py`); an empty object (or no file) means no
remote. Machine-local and never committed.

```json
{
  "url": "https://github.com/me/vault.git",
  "branch": "main",
  "credential_ref": "secret/github",
  "username": "coffer",
  "include_secret": false,
  "interval_seconds": 3600,
  "enabled": true
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `url` | str | the user's own repository; must not start with `-` or contain whitespace (`SYNC_REMOTE_INVALID`, 422) |
| `branch` | str | default `main`; checked against git's branch-name rules |
| `credential_ref` | str? | a **reference** into the credential store, never a secret. Its value reaches git through a per-invocation credential helper, resolved through the secret boundary with destination `sync_remote` / `remote`, target `git <url>` — a token for a URL it was never approved for waits for a person (the round is `auth_failed` until then) |
| `username` | str | default `coffer`; the name an HTTPS token is sent with. GitHub and GitLab ignore it; Bitbucket needs one such as `x-token-auth`, Azure DevOps a real one. Non-blank, no spaces, `:`, `@` or `/`, at most 128 characters |
| `include_secret` | bool | whether `vault/secret/` is committed and pushed at all; default off. Off, `/secret/` is in `vault/.git/info/exclude` |
| `interval_seconds` | int | default 3600; positive, raised to at least 60 |
| `enabled` | bool | `false` pauses the timer; the remote and history are kept, and "Sync now" still runs a round |

Because `credential_ref` is a reference, the whole document can be returned by
the API or logged without redaction. Setting a remote with a different `url` or
`branch` clears `round.json`'s `stop`, `confirmed` and `joined` (a stop and a
join are facts about one remote's history); clearing the remote also clears
`join_choices` and switches `secret/` back to excluded. The vault and its
history stay as they are either way.

## `local/sync/round.json`

`JsonRoundState` (`infrastructure/sync/local_state.py`); each key is removed
when it has nothing to say.

| Key | Shape | Meaning |
| --- | --- | --- |
| `stop` | `Stop` | the round waiting for a person — conflicts to answer, or a hold to confirm or restore |
| `join_choices` | `[ConflictFile]` | files a join left as they are here because both sides hold them with no common base, until the person chooses (keep mine / take theirs); while listed, the vault writer *holds* those paths and their effective version is the one on disk |
| `confirmed` | `[local tip, remote tip]` | a hold the person confirmed, for exactly that pair of tips |
| `joined` | `true` | this machine has joined the current remote |

`Stop` (`domain/sync/stops.py`):

| Field | Notes |
| --- | --- |
| `kind` | `conflicts` \| `hold` |
| `local`, `remote`, `base` | the commits the stop was raised against; if either tip moves before the person answers, the round is derived and asked again |
| `raised_at` | ISO time |
| `conflicts` | `[ConflictFile]` |
| `hold` | `{direction: incoming \| outgoing, breaches: [{area, lost, total}], paths: [...]}` — the deletion breaker's stop |
| `tree` | the merged tree git produced (conflict markers where it could not merge); answers are applied on top of it |
| `join` | set when the stop belongs to a join |

`ConflictFile`:

| Field | Notes |
| --- | --- |
| `path`, `area` | the vault path and its area (spec vault-storage) |
| `reason` | `both_changed` \| `changed_and_deleted` \| `same_name_different_uid` \| `duplicate_uid` \| `invalid_merge` \| `join_differs` |
| `ours`, `theirs`, `base` | the blob on this machine, the other side and the merge base; `null` = absent there |
| `ours_time`, `theirs_time`, `theirs_machine` | when each side last changed the file, and which machine made the other side's change |
| `other_path` | the other file of a same-name conflict |
| `answer` | `mine` \| `theirs` \| `edited`, once answered |
| `edited` | the blob of the person's hand-merged version; refused while conflict markers are left in it |

An `edited` answer is prepared from an editor copy under
`derived/sync-conflicts/<path>`; the directory is cleared when the round
continues.

## Machine descriptor — `vault/machines/<machine_id>.json`

One JSON document per machine (`MachineDescriptor`, `domain/sync/machine.py`).
Each machine writes **only its own**, so descriptors never conflict; the machine
registry is whatever `machines/*.json` holds — a derived view, not a table.
Renaming this machine writes its descriptor at once as a `user` commit;
retiring another machine deletes that machine's descriptor in a commit.

```json
{
  "format_version": 1,
  "machine_id": "a3f21c9e4b7d2610",
  "name": "Desktop",
  "os": "Darwin 24.6.0",
  "hostname": "studio.local",
  "coffer_version": "0.2.0",
  "last_round_at": "2026-09-30T08:00:00+00:00",
  "last_converged_commit": "<40-hex commit sha>",
  "key_fingerprint": "<short sha256 of the master key>",
  "agents": [
    {
      "type": "claude_code",
      "name": "claude-code",
      "plugins": [
        { "id": "…", "name": "…", "marketplace": "…", "enabled": true, "version": "1.2.0" }
      ]
    }
  ]
}
```

| Field | Notes |
| --- | --- |
| `format_version` | the descriptor's format (1) |
| `machine_id` | also the file name. `sha256("coffer-machine:" + raw)` truncated to 16 hex characters; the raw host identifier — `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux — is a hardware identifier and is never written. When neither is readable the raw value is a UUID generated once into `~/.coffer/machine-id`, which does not survive deleting `~/.coffer`, and the machines page says so. It names this machine's commits (`Coffer-Machine`) |
| `name` | the user's label, defaulting from the hostname; mutable at any time, because nothing keys on it |
| `os`, `hostname`, `coffer_version` | descriptive, for the machines table |
| `last_round_at` | when this machine last finished a round that moved anything; also its "last seen" |
| `last_converged_commit` | the commit that round converged at — the base a **returning** machine joins from |
| `key_fingerprint` | the same short hash `GET /sync/key/fingerprint` returns, so another machine can say "your secrets will not decrypt here". Never the key |
| `agents` | each agent on the machine, `{type, name, plugins[]}`; a plugin is `{id, name, marketplace, enabled, version}`. An **inventory, not a replicator**: nothing is written into any agent's configuration from another machine's list |

A descriptor from a newer build is read tolerantly: unknown fields are ignored
and missing ones read as empty. The id and the label are cached in
`~/.coffer/daemon-config.json`; a lost cache recomputes to the same id, because
the host produces it.

## Snapshots — `refs/tags/coffer/pre-apply/<time>`

Before a round checks anything out, the vault's current commit is tagged
`coffer/pre-apply/<YYYYMMDDTHHMMSSZ>` (a `-<n>` suffix when two fall in one
second); the ten newest are kept. The tags live in the vault repository only
and are never pushed. Rolling a round back is a new `user` commit that puts
back, from the round's snapshot, the paths the round changed — later edits to
other paths are kept, and a round that applied nothing, or a rollback, cannot
be rolled back.

## `runs.db` — `sync_runs`

Every round this machine ran. Machine-local and never synced: a history that
travelled would be another machine's account of rounds this one never ran; the
vault's git history is the record of what *changed*.

```sql
CREATE TABLE sync_runs (
    id            INTEGER PRIMARY KEY,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP NOT NULL,
    status        VARCHAR   NOT NULL,
    join_kind     VARCHAR,              -- new / returning when the round joined; else NULL
    commit_sha    VARCHAR,              -- the commit the round reached (`commit` is reserved in SQL)
    error         TEXT,                 -- redacted of the push credential before it is written
    payload_json  TEXT                  -- the whole RoundRecord, written once
);
CREATE INDEX ix_sync_runs_finished_at ON sync_runs(finished_at);
```

`SyncRunModel` (`infrastructure/persistence/models.py`), written by `SyncRunRepo`
(`infrastructure/persistence/sync_runs_repo.py`). The columns are what a list
reads at a glance; `payload_json` is the `RoundRecord` (`domain/sync/rounds.py`)
and is what a row is read back from, so no column can disagree with it:

| `RoundRecord` field | Notes |
| --- | --- |
| `status` | the vocabulary below |
| `started_at`, `finished_at` | ISO times |
| `trigger` | `timer` \| `manual` |
| `from_commit`, `to_commit` | the range the vault moved across |
| `snapshot` | the pre-apply tag the round took |
| `pulled` | `[{version, time, machine, files}]` — the commits that came in |
| `applied`, `pushed` | `[{path, status: added \| modified \| removed}]` — the files applied here and sent out |
| `with_machines` | the labels of the machines whose commits the round pulled |
| `conflicts`, `held` | counts for a stopped or held round |
| `detail` | git's redacted message for a failure |
| `path` | the file a `waiting_on_edit` round names |
| `join` | `new` \| `returning` |

`status`:

| Value | Meaning |
| --- | --- |
| `nothing_to_do` | nothing to pull and nothing to push |
| `pulled` / `pushed` / `pulled_and_pushed` | what the round moved |
| `push_failed` | pulled and applied, but the remote refused the push |
| `stopped` | any conflict: nothing checked out, nothing pushed |
| `held` | the deletion breaker held the round (20% of an area or 20 files, in either direction; resource files counted by uid, so a moved file is not a loss) |
| `waiting_on_edit` | a person's uncommitted edit is on a path the round would change; it is never overwritten |
| `join_required` / `joined` | this machine has never converged with the remote / a join finished |
| `unreachable` / `auth_failed` | the remote could not be reached / sign-in failed (or the token waits for approval) |
| `paused_cloud_folder` | the vault is inside a folder another tool synchronises (Dropbox, iCloud, Syncthing, `~/Library/CloudStorage`) |
| `remote_too_new` | the remote was written by a newer layout; refused |
| `remote_too_old` | the remote is in the pre-vault layout; refused until it is rebuilt from an upgraded machine (point it at an empty branch or remote) |
| `rolled_back` | a rollback round |
| `failed` | anything else, with `detail` |

`stopped`, `held`, `waiting_on_edit`, `join_required`, `auth_failed`,
`paused_cloud_folder`, `remote_too_new` and `remote_too_old` leave the vault in
a state a person must look at, and each raises an attention item. Swept by the
retention worker as `sync_runs` (default 90 days).

## What never enters the repository

Everything outside `~/.coffer/vault/`: `local/` (reach, the sync remote, the
round state, the secret boundary, machine-local ciphertext), `content/`,
`derived/`, `runs.db` (conversations, the audit log, MCP invocations, rounds),
`logs/`, `daemon-config.json`, `daemon.json`, and the master key file or
keychain entry. Inside the vault, `vault/.git/info/exclude` — never a tracked
`.gitignore` another machine could change — keeps out editor and system
litter, hidden entries in knowledge collections (except the inbox), and
`/secret/` unless the remote has `include_secret`.

## Path portability

A resource file must work on a machine whose home directory differs. A string
value under this machine's home is written as `${HOME}/...` and expanded against
the reading machine's home; a path outside `$HOME` is carried verbatim and may
not resolve there.
