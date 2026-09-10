# Data Model — Vault Export and Import

> 中文版: [data-model.zh.md](./data-model.zh.md)

## Persistent state

**None.** Export and import are one-shot operations over the live vault; they
own no tables. There is no sync configuration to persist (the user names a
directory per invocation), no last-run state to arbitrate against, no machine
registry, and no tombstone ledger — continuous sync and everything that served
it is withdrawn ([Vault Export and Import](../../docs/decisions/vault-export-import.md)).

`infrastructure/sync/` therefore contributes no ORM models and no migration of
its own beyond the one that drops the withdrawn `sync_config`, `sync_state`,
`machine_identity` and `sync_tombstones` tables.

The credential ciphertext an export carries comes from the existing
`credentials` table; the resource documents come from the existing resource
tables via `ResourceService`. SQLite remains the local system of record.

## Filesystem state (the export bundle)

A bundle is a plain directory the user names on each export. It is not managed
by Coffer between runs: nothing is remembered about it, nothing is written to
it in the background, and it has no relationship to any other bundle.

```
manifest.json                  bundle schema version + creation time
knowledge/                     mirror of ~/.coffer/knowledge
skills/                        mirror of ~/.coffer/skills (master skill store)
resources/<kind>/<name>.yaml   one deterministic file per config resource
state/<area>/...yaml           module-owned shared state docs
credentials/<ref>.enc          Fernet ciphertext, base64 text; never the key
```

`credentials/` exists only when the export was taken with `--with-credentials`.

### `manifest.json`

| Field            | Type   | Notes                                          |
| ---------------- | ------ | ---------------------------------------------- |
| `schema_version` | int    | Bumped on incompatible bundle layout changes.  |
| `created_at`     | String | ISO-8601 of when the bundle was written.       |

Current version: **1**. The bundle is a new format with its own lineage; the
withdrawn git workspace's `schema_version` (which had reached 3) does not carry
over, because no bundle in that layout was ever produced by this format.

`schema_version` is checked on import: a bundle newer than the running build
fails closed with `SYNC_BUNDLE_TOO_NEW` before anything is applied, mirroring
the DB `DB_SCHEMA_TOO_NEW` rule. `created_at` is informational — it is the only
field that legitimately differs between two exports of an unchanged vault, so
determinism comparisons exclude it.

### Resource serialization (`resources/<kind>/<name>.yaml`)

Deterministic projection of a `Resource`:

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
scope: ["claude-code"]   # omitted when null (active for every agent)
config: { ... }          # the validated, json-mode config; keys sorted
```

- `created_at` / `updated_at` / the local `id` are **excluded** — machine-local,
  and they would make every export differ from the last.
- Mapping keys are sorted; there is exactly one document per resource, so two
  exports of an unchanged vault are byte-identical.
- `scope` ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md))
  is an ordinary field — a list of agent names — and rides through export and
  import unmodified. No dedicated machinery; a resource out of scope for every
  local agent still imports, and simply is not activated.
- String values under the exporting machine's home are normalized to
  `${HOME}/...` and expanded against the importing machine's home (see
  [Path portability](#path-portability)).

On import the resource is upserted by `<kind>:<name>` through the kind-agnostic
`ResourceService`, and the kind's post-import hook runs so the machine-local
side-effects (shim install, native-config projection, skill symlink) are
performed. A local resource is **never** deleted by an import: absence from a
bundle carries no meaning, because a bundle is one machine's snapshot rather
than an assertion about what should exist everywhere.

### Path portability

An export written on one machine must import on another whose home directory
differs.

| Path shape         | On export                    | On import                              |
| ------------------ | ---------------------------- | -------------------------------------- |
| Under `$HOME`      | stored as `${HOME}/...`      | expanded against the importing home    |
| Outside `$HOME`    | stored verbatim              | used verbatim; may not resolve here    |

A verbatim path that does not exist on the importing machine surfaces as a
per-resource import failure (that resource's ref plus the reason in the import
result), never as a silent mismatch and never as a fatal error for the run.

### State areas (`state/<area>/...yaml`)

Module-owned shared state that belongs to the vault rather than to one machine.
Each module implements `SyncedStatePort` (export/import of deterministic YAML
docs) and the composition root registers the providers — the sync slice never
imports kind modules. Current areas:

- `channel-peers/<channel>/<chat>.yaml` — pairing identity (chat_id, sender_id,
  display name, preferred agent, paired_at; the machine-local
  `active_conversation_id` never travels). Import upserts; a doc referencing a
  channel not present locally is reported as a per-doc failure and skipped.
- `mcp-preferences/<server>.yaml` — the DISABLED capabilities per server
  (enabled is the default; seen-timestamps stay machine-local). Import
  reconciles the servers present locally to match the bundle.
- `settings/embedding.yaml` + `settings/internal-engine.yaml` — the two engine
  singletons. Exported only once the exporting machine has persisted them
  locally, so an untouched machine never exports its defaults over another
  machine's configured values.
- `memory-labels/<store>.yaml` — the user-set display label of a memory store
  (spec knowledge FR-017c), so a `project-<ULID>` store reads by its name after an
  import instead of "unnamed store". A cleared label travels as an explicit
  empty-label doc (`{label: ""}`) rather than as doc absence, which import
  cannot distinguish from "never set".

Skill delivery bindings (`skill_agent_bindings`) stay machine-local by
decision: delivery is a side-effectful file operation against directories that
differ per machine. Adopt skills per machine through the existing skill
surfaces after importing the master store.

### Credential blob (`credentials/<ref>.enc`)

The Fernet ciphertext for `ref`, base64-encoded as text. No master key, no
plaintext, no metadata beyond the ref (which is the path).

`ref` may be namespaced with slashes (e.g. `channel/seatalk/app-secret`,
`provider/agnes/key`), so the blob lives at the matching nested path
`credentials/channel/seatalk/app-secret.enc`. Export creates the parent
directories; import walks recursively and rebuilds the full slash ref from the
relative path.

Ciphertext imported onto a machine that does not hold the matching master key
is stored as-is and reported as `credentials_locked`; the affected resources
refuse to spawn rather than failing decryption silently. The key is
bootstrapped out-of-band (`coffer sync key export` / `coffer sync key import`)
and never appears in a bundle. Those commands move the key **material** over the
loopback API — `POST /sync/key/export` returns `{material}`, `POST
/sync/key/import` accepts it — and each surface does its own file I/O: the CLI
writes and reads the file itself (`0600`), the web UI uses a browser download
and an `<input type="file">`. The daemon opens no caller-named path.

## Local-only, never in a bundle

`~/.coffer/logs/`, `coffer.db`, `daemon.json`, PID/port files, chat history,
the audit log, and the master key file / keychain entry.

## Derived indexes (excluded + regenerated)

Files that are *regenerated* from the source-of-truth files are excluded from
the mirror — carrying them would let a stale copy overwrite a freshly rebuilt
one. The memory store's `MEMORY.md` index is the current case: the per-fact
`<slug>.md` files travel, and `MEMORY.md` is rebuilt from the imported facts.
The set lives in `infrastructure/sync/` alongside the bundle layout.
