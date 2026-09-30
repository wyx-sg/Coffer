# Design — file the vault and sync it thinly

The decisions are the ADRs'
([storage-is-five-classes-by-nature](../../../docs/decisions/storage-is-five-classes-by-nature.md),
[identity-is-the-uid-inside-the-file](../../../docs/decisions/identity-is-the-uid-inside-the-file.md),
[every-vault-file-carries-its-format-version](../../../docs/decisions/every-vault-file-carries-its-format-version.md),
[every-vault-write-is-a-validated-commit-naming-its-writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md),
[sync-applies-clean-merges-and-stops-on-any-conflict](../../../docs/decisions/sync-applies-clean-merges-and-stops-on-any-conflict.md),
[sync-deletion-breaker](../../../docs/decisions/sync-deletion-breaker.md),
[reach-is-a-machine-local-predicate-over-a-context](../../../docs/decisions/reach-is-a-machine-local-predicate-over-a-context.md),
[credentials-across-machines](../../../docs/decisions/credentials-across-machines.md)).
This file records what the implementation chose inside them, and where it
deviates from their text.

## Choices

| # | Decision | Why / deviation |
|---|---|---|
| D1 | Vault documents Coffer parses are **JSON** (`resources/<kind>/<name>.json`, `state/<area>/<name>.json`, `machines/<id>.json`), 2-space indent, trailing newline, key order preserved on round trip. | The Sync boards show `resources/mcp_server/linear.json`; JSON round-trips unknown keys in place with the stdlib (the ADR's "comment- and order-preserving YAML writer" would need ruamel, not in the lock). ADR text `<name>.yaml` amended. Memory triggers stay Markdown+frontmatter (already files). |
| D2 | Storage class per kind, declared on `Kind.storage` (`vault` default; `agent` → `local`; `memory` → `derived`), with a per-row refinement replacing `converges_row` (builtin `coffer-guide` → `derived`). `converges`/`converges_row` are deleted. | "Agents are machine-local and do not sync" (decision log 2026-09-30); memory tree is derived; the directory is the policy. |
| D3 | `Resource.id` (integer surrogate) is deleted. Every table that held `resources.id` is re-keyed to the uid (`resource_uid`, `skill_uid`, `agent_uid`). | ADR identity: "The integer `resources.id` surrogate and the foreign keys on it disappear with the table". |
| D4 | `Resource.rev` stays an `int`, now a derived per-uid counter bumped whenever the file's blob id changes (kept in the derived uid index). | The event stream and reconciler contracts carry an int; the ADR's "blob id as rev" is the value compared, the counter is its ordinal. Deleting `derived/` restarts counters, which only the in-process dedupe reads. |
| D5 | Reach lives in `local/reach.json`: `{uid: {"enabled": bool, "agents": [uid]\|null, "projects": null}}`. A resource with no record gets its kind's default (enabled, unrestricted, or the kind's `default_scope`). The `Scope` API is unchanged; `projects` is reserved and always null. | ADR reach: "moves in the same migration, in its new shape, so it moves once". Channel `may_drive` is follow-up (not in Q9). |
| D6 | Writers: `user` (a person through a Coffer surface), `disk` (found on disk: a person's editor or an agent's file tools), `agent` (+`Coffer-Agent: <type>`), `daemon`, `curation`, `sync`. Trailers `Coffer-Writer/-Operation/-Actor/-Agent/-Machine/-Restored-From/-Layout` (+ knowledge's collection/item/status/undoes). | Brief's "you / agent:<type> / sync / daemon / curation"; `disk` keeps the knowledge history's existing word for a hand edit. |
| D7 | CAS: every content API (skill file save, knowledge save, vault restore) takes a mandatory `expected_fingerprint` (sha256 of the bytes read). Structured writes through `ResourceRepo` and the state stores are read-modify-write under the one vault lock and refuse (`VAULT_FILE_STALE`, 409) when the file on disk differs from `HEAD` (an unsettled hand edit). | Threading an expected hash through every resource API would change ~40 call sites for no extra safety: the lock already serialises daemon writers; the only other writer is the disk. |
| D8 | Effective state = `HEAD`. The resource and state stores read parsed documents from a cache loaded from `HEAD` and refreshed after each commit; an invalid hand edit stays in the working tree, uncommitted, flagged (`derived/vault-problems.json` + attention source `vault`). | ADR writers. |
| D9 | Watcher = `watchfiles` (already a direct dependency) as a hint, debounced until the changed paths are quiet for 1 s, plus a periodic scan (60 s) and the boot scan as the truth (`git status --porcelain -z`). | ADR writers; no new dependency. |
| D10 | Local state is JSON under `local/` (`reach.json`, `tool-reach.json`, `sync/remote.json`, `sync/round.json`, `retention.json`, `secrets/{bindings,approvals,settings}.json`, `skill-source-status.json`, `curation.json`). Written atomically under a per-file lock. | ADR storage: local = "settings can be set again"; no second Alembic lineage. |
| D11 | Derived tables (`mcp_server_health`, `skill_agent_bindings`, MCP capability first/last-seen) move to `derived/derived.db`, created with `create_all` and dropped/recreated when its `user_version` differs. | Derived is always rebuildable. |
| D12 | `runs.db` = today's `coffer.db`, renamed, with Alembic revision 0117 dropping the tables that moved out and re-keying `resource_id` → uid. `COFFER_DB_URL` keeps naming it. | ADR storage "runs.db keeps the single-writer rule … one Alembic lineage". |
| D13 | MCP capability toggles live in the vault as `state/mcp-preferences/<server name>.json` (server uid inside, only disabled capabilities listed); first/last seen go to derived. Channel pairings `state/channel-peers/<channel name>.json`; engine settings `state/settings/internal-engine.json`. Agent plugin inventory moves into the machine descriptor (`agents: [{type, plugins}]`). | Keeps today's synced areas (so the boards' areas and the breaker's areas stay), drops the churny columns. |
| D14 | Curation finds a person's edits by blob comparison: `local/curation.json` records the blob each document had when curation last settled it; a document whose `HEAD` blob differs and whose last commit writer is not `curation`/`sync` is pending. `_align_mtime`, `coffer_curated_at` stamps and the mtime check are deleted (stamps stripped by the migration). | ADR writers ("mtime never decides"). |
| D15 | The migration is Python, not an Alembic step: `infrastructure/vault/migration/` reads the pre-vault tables (DB at revision 0116), writes files, moves trees, folds the knowledge repository's history in, commits one `Coffer-Layout: db -> 1` commit, then the runner renames `coffer.db` → `runs.db` and runs 0117. Backup `coffer.db.pre-vault` (+wal/shm) first; a manifest `local/migration.json` records every move so `coffer migrate --rollback` reverses them; `coffer migrate --rehearse` runs it against a copy in a throwaway HOME. | ADR format-version rollback rules. |
| D16 | Thin sync per ADR option B: fetch → `merge-tree --write-tree` → stop on any conflict / guard / snapshot → `read-tree -m -u` CAS checkout → push. Stopped round in `local/sync/round.json` with per-file answers (`mine` / `theirs` / `edited`, editor copy under `derived/sync-conflicts/`). Join: `new` (union: nothing deleted, differing files left alone until chosen, same-name-different-uid = conflict) and `returning` (3-way from the descriptor's last commit), both previewed. Credential ciphertext conflicts are settled by Fernet time, never asked. Snapshots `refs/tags/coffer/pre-apply/<ts>`, ten kept; rollback = a new `user` commit of the snapshot's tree for the paths the round changed. Breaker 20% / 20 documents, uid-counted for resource files. Problems classified: `unreachable`, `auth_failed`, `push_failed`, `cloud_folder`. | ADR sync; boards 6.5.01–6.5.23. |

## Layout

```
~/.coffer/
  vault/                         git repository, always (sync only adds a remote)
    manifest.json                {"schema_version": 3}
    resources/<kind>/<name>.json mcp_server, skill, channel, provider, knowledge
    state/mcp-preferences/<server>.json   state/channel-peers/<channel>.json
    state/settings/internal-engine.json
    knowledge/<collection>/...   (history folded in from the old <knowledge root>/.git)
    skills/<name>/...            master folders
    memory-triggers/<id>.md
    credentials/<ref>.enc        excluded in .git/info/exclude unless include_credentials
    machines/<machine id>.json   descriptors (sync)
  local/                         never synced
    resources/agent/<name>.json  reach.json  tool-reach.json  retention.json  curation.json
    skill-source-status.json  secrets/{bindings,approvals,settings}.json
    sync/{remote,round}.json  migration.json  daemon-config.json stays at ~/.coffer (read pre-DB by the desktop app's peers)
  content/                       chat-media/  channel-media/  workspace/
  derived/                       derived.db  memory/  cache/agent/  index/uids.json
                                 resources/memory/  resources/skill/coffer-guide.json
                                 skills/coffer-guide/  vault-problems.json  sync-conflicts/
  runs.db (+wal/shm)             audit_log, mcp_invocations, conversations, chat_messages,
                                 channel_thread_*, channel_outbox, sync_runs, usage_*, quota_snapshots
  coffer.db.pre-vault            the read-only backup, kept one version
  logs/ bin/ daemon.json master.key (until the keychain lands) vendor/ proxy-usage/ ...
```

## Where every table went

| Table | Class | Goes to |
|---|---|---|
| resources (config) | vault / local (agent) / derived (memory, builtin skill) | resource files |
| resources.enabled, scope_json | local | `local/reach.json` |
| mcp_tool_reach (custom tools' per-tool reach) | local | `local/tool-reach.json` |
| credentials | vault | `vault/credentials/<ref>.enc` |
| secret_bindings, secret_approvals, secret_boundary_settings | local | `local/secrets/*.json` |
| mcp_capability_preferences (enabled) | vault | `state/mcp-preferences/` |
| mcp_capability_preferences (first/last seen) | derived | `derived.db` |
| channel_peers | vault | `state/channel-peers/` |
| internal_engine_config | vault | `state/settings/internal-engine.json` |
| retention_policies | local | `local/retention.json` |
| sync_remotes | local | `local/sync/remote.json` |
| sync_convergence_state, sync_held_paths | — (retired with the pointer and retry set) | dropped |
| skill_source_status | local | `local/skill-source-status.json` |
| mcp_server_health, skill_agent_bindings | derived | `derived.db` |
| audit_log, mcp_invocations, conversations, chat_messages, channel_thread_conversations, channel_thread_history, channel_outbox, sync_runs, usage_requests, usage_daily, quota_snapshots | runs | `runs.db` |
| workflow tables kept by the lineage | runs | untouched |

## The migration, step by step

On the first start of the new build, before any service is built:
1. `alembic upgrade 0116` if the DB is older (existing `coffer.db.pre-<rev>` backup rule).
2. Copy `coffer.db` (+`-wal`/`-shm`) to `coffer.db.pre-vault`; never opened for writing again.
3. Create `vault/`, `local/`, `content/`, `derived/`; write resource files, reach, state files,
   ciphertext files, local JSON from the tables.
4. Move (rename, not copy) `knowledge/` → `vault/knowledge/`, `skills/` → `vault/skills/`
   (`skills/coffer-guide` → `derived/skills/coffer-guide`), `memory/` → `derived/memory/`,
   `chat-media/`, `channel-media/`, `workspace/` → `content/`, `cache/agent/` → `derived/cache/agent/`;
   the old sync working tree `~/.coffer/sync` is left in place (not deleted) and named in the report.
5. Fold `<knowledge root>/.git` history into the vault repository under `knowledge/`; strip
   `coffer_curated_at` stamps; one commit `Coffer-Layout: db -> 1` (writer daemon).
6. Record every move in `local/migration.json`; rename `coffer.db` → `runs.db`; Alembic 0117 drops the
   moved tables and re-keys the runs tables to uids.
7. Report symlinks into the old memory tree and the old sync tree; nothing is deleted.

Rollback: stop the daemon; `coffer migrate --rollback` moves `vault/` to `vault.rolled-back-<ts>`,
reverses every recorded move, restores `coffer.db.pre-vault` as `coffer.db`, moves `runs.db` aside and
writes a hold marker so this build does not migrate again until `coffer migrate --resume`; then install
the previous build. Rehearse: `coffer migrate --rehearse` copies `~/.coffer` (read-only) into a temp
HOME, migrates there, reports counts per class, rolls back, deletes the copy.
