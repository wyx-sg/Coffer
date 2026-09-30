# Data Model — Credentials

The ciphertext table, the master key, the secret boundary's three tables, and a
handful of error codes. None of them holds a plaintext value: anything this
document listed beyond ciphertext, timestamps and where a value is allowed to
go would be another place for a secret to be inferred from.

## The table

The `credentials` table arrived with the encrypted credential store (migration
`0016`) and lives in the same `~/.coffer/coffer.db` as every other kind's state.

```sql
CREATE TABLE credentials (
    ref         TEXT PRIMARY KEY,
    ciphertext  BLOB NOT NULL,                -- produced by EncryptedCredentialStore
    created_at  TEXT NOT NULL,                -- ISO-8601, written by the sync store
    updated_at  TEXT NOT NULL,
    last_used_at TEXT                         -- machine-local; migration 0134
);
```

| Column       | Notes                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------- |
| `ref`        | The opaque reference. Slash-separated `[A-Za-z0-9_.-]` segments; the store reads no meaning into it. |
| `ciphertext` | A Fernet token. Never logged, never audited; its plaintext leaves only through the desktop app's presence-gated reveal. |
| `created_at` | Set on first write for the ref; a re-write keeps it.                                              |
| `updated_at` | Set on every write, so rotation is visible without revealing anything.                            |
| `last_used_at` | When a consumer last had the value decrypted on this machine, stamped at most once a minute; a reveal or an import's read-back does not count. Never synced. NULL until first used. |

There is no `kind` column and no foreign key to `resources`. A reference is
resolved by string, in the direction resource → credential only, which is why
"who cites this ref" is answered by scanning resource configs (see "Refuse to
delete a credential still in use") rather than by a join.

| ORM class         | Table         | Lives in                                 |
| ----------------- | ------------- | ---------------------------------------- |
| `CredentialModel` | `credentials` | `infrastructure/persistence/models.py`   |

The store itself (`infrastructure/credentials/encrypted_store.py`) deliberately
uses stdlib `sqlite3` with a short-lived connection per call, because sync
callers — the MCP spawn path, register-time probing — need a synchronous
contract. Its `a*` facade is what async callers use (see "Keep blocking store
calls off the event loop").

## The master key

Not a table. Where it lives is chosen by how the build was made (see "Keep the
master key behind a storage port chosen by the build"):

| Location                | Where                                                                 | Build |
| ----------------------- | --------------------------------------------------------------------- | ----- |
| `keychain_access_group` | data-protection Keychain item, service `coffer`, account `master-key`, access group `<TEAMID>.coffer`, no presence flag | signed release, the only place |
| `file`                  | `~/.coffer/master.key`, mode `0600`                                   | development default |
| `keychain`              | OS keychain entry under ref `master-key`                              | development opt-in |

In a development build:

Resolution reads the file first, then the keychain (see "Resolve the master key
file-first and create it only for an empty store"). `MasterKeyManager` records
which location answered; that value is what `GET /api/v1/settings/ credentials`
reports and what `PUT` compares against before relocating.

Relocation writes and verifies the destination, then removes the source, so the
intermediate state is "both copies exist" rather than "neither does".

## The secret boundary's tables

Migration `0112`. Written by the credentials package's sync store
(`infrastructure/credentials/boundary_store.py`, stdlib `sqlite3` like the
ciphertext store, because the gate is consulted from the synchronous resolve
path).

```sql
CREATE TABLE secret_bindings (          -- a ref approved for one slot of one destination
    ref TEXT, destination_kind TEXT, destination_uid TEXT, slot TEXT,
    target_fingerprint TEXT NOT NULL,   -- sha256(target)[:32]; a new target is a new destination
    approved_at TEXT NOT NULL,
    approval_id TEXT,                   -- NULL when adopted, fresh or approved while protection was off
    PRIMARY KEY (ref, destination_kind, destination_uid, slot)
);
CREATE TABLE secret_approvals (         -- what waits for the desktop app
    id TEXT PRIMARY KEY,
    op TEXT NOT NULL,                   -- bind | add_secret | replace_value | disable_protection
    status TEXT NOT NULL,               -- pending | approved | rejected | superseded
    created_at TEXT NOT NULL, requested_by TEXT NOT NULL,
    ref TEXT, destination_kind TEXT, destination_uid TEXT, destination_label TEXT,
    slot TEXT, target TEXT, target_fingerprint TEXT,
    pending_ciphertext BLOB,            -- a new or replacement value, Fernet-sealed; cleared on any decision
    decided_at TEXT, decided_by TEXT
);
CREATE TABLE secret_boundary_settings ( -- require_approval, adopted_existing_bindings
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
```

A destination is identified by `(destination_kind, destination_uid)` — a
resource's kind and uid, or `sync_remote` / `remote` — and a slot names the
place inside it (an environment variable, a header, `token`, `secret`). The
target a binding is pinned to is written out in the approval so a person can
read it; the binding keeps only its fingerprint.

## Credential references

A reference is not stored anywhere by this spec. It is a string inside another
kind's resource config, and each kind declares how to find its own:

```
Kind.credential_ref_extractor: (config) -> {logical_key: ref}
```

`mcp_server` maps env var names and header names to refs; `channel` maps a bot
token; `provider` maps an API key. A kind without an extractor declares no
credentials, is never probed at register time, and releases nothing on delete.

## Error codes

| Code                   | Raised when                                                        | Surfaced as |
| ---------------------- | ------------------------------------------------------------------ | ----------- |
| `CREDENTIAL_MISSING`   | A ref a configuration cites does not resolve                        | 400 / startup failure at the citing surface |
| `CREDENTIAL_IN_USE`    | Delete attempted while a resource config still cites the ref | 409, with `details.references` naming each citer by kind and current label (`channel 'my-bot'`) — never by uid, which is not what the user sees on the page they must visit next |
| `CREDENTIAL_LOCKED`    | The OS keychain refused or could not be read                        | 503; the legacy migration treats it as "skip and retry next start" |
| `CREDENTIAL_UNREADABLE`| Ciphertext will not decrypt with the current key                   | 5xx, naming the ref |
| `MASTER_KEY_MISSING`   | Ciphertext exists and no key resolves, or the key is corrupt | Fatal at daemon startup, naming the path |
| `MASTER_KEY_CONFLICT`  | A signed build finds one key in its Keychain item and a different one in the file or legacy item | Fatal at daemon startup, naming both fingerprints |
| `SECRET_BINDING_PENDING` | A secret would go to a destination or target nobody approved | 409, `details.approval_ids`; the CLI exits `9` |
| `PRESENCE_GRANT_INVALID` | A presence grant is missing, expired, reused, for another operation or target, or not signed with the grant key | 403 |
| `APPROVAL_NOT_FOUND` / `APPROVAL_NOT_PENDING` | An approval id that does not exist, or was already decided | 404 / 409 |
| `SECRET_NAME_INVALID` / `SECRET_NOT_FOUND` | A `coffer run` name that is not one `secret/` segment, or is not stored | 422 / 404 |

## Audit events

Written by this spec into the shared `audit_log` table (whose shape is the
framework's):

| Event                  | Payload                          |
| ---------------------- | -------------------------------- |
| `credential_set`       | `{ref}`                          |
| `credential_revealed`  | `{ref}` — the desktop app's presence-gated reveal |
| `credential_deleted`   | `{ref}`                          |
| `credential_migrated`  | `{ref}`                          |
| `master_key_relocated` | `{to}` (and `{from}` for the signed build's move into its access group) |
| `master_key_exported`  | `{path, fingerprint}` — the desktop app's key backup |
| `secret_resolved`      | `{name, argv0, cwd}` — one `coffer run` resolve, never the rest of argv |
| `secret_approval_requested` / `_approved` / `_rejected` | `{approval_id, op, ref}` |
| `secret_imported`      | `{name, path}` — a plaintext file value moved into the store |

`credential_read` is no longer written (no route returns a value); older rows
keep their label.

No payload carries a value (see "Keep secret values out of credential audit
events"). `credential_deleted` is written both by the delete route and by the
release that follows a resource deletion (see "Release unshared references when
a resource is deleted").

## Invariants enforced by importlinter

| Contract | Subject                                                                 |
| -------- | ------------------------------------------------------------------------ |
| `keyring` confinement | Only `coffer.infrastructure.credentials` may import `keyring`. The CLI, every surface and every other kind are outside it. |

That contract predates this spec's extraction; the fence is what makes "Confine
key management to the credentials package" checkable rather than aspirational.
