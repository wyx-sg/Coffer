# Data Model — Credentials

One table, one file, and a handful of error codes. The whole point of the design
is that there is nothing else: anything this document listed beyond ciphertext
and timestamps would be another place for a secret to be inferred from.

## The table

The `credentials` table arrived with the encrypted credential store (migration
`0016`) and lives in the same `~/.coffer/coffer.db` as every other kind's state.

```sql
CREATE TABLE credentials (
    ref         TEXT PRIMARY KEY,
    ciphertext  BLOB NOT NULL,                -- produced by EncryptedCredentialStore
    created_at  TEXT NOT NULL,                -- ISO-8601, written by the sync store
    updated_at  TEXT NOT NULL
);
```

| Column       | Notes                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------- |
| `ref`        | The opaque reference. Slash-separated `[A-Za-z0-9_.-]` segments; the store reads no meaning into it. |
| `ciphertext` | A Fernet token. Never logged, never audited, never returned except through the audited read.      |
| `created_at` | Set on first write for the ref; a re-write keeps it.                                              |
| `updated_at` | Set on every write, so rotation is visible without revealing anything.                            |

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

Not a table. Exactly one of:

| Location   | Where                                       | Default |
| ---------- | ------------------------------------------- | ------- |
| `file`     | `~/.coffer/master.key`, mode `0600`         | yes     |
| `keychain` | OS keychain entry under ref `master-key`    | opt-in  |

Resolution reads the file first, then the keychain (see "Resolve the master key
file-first and create it only for an empty store"). `MasterKeyManager` records
which location answered; that value is what `GET /api/v1/settings/ credentials`
reports and what `PUT` compares against before relocating.

Relocation writes and verifies the destination, then removes the source, so the
intermediate state is "both copies exist" rather than "neither does".

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

## Audit events

Written by this spec into the shared `audit_log` table (whose shape is the
framework's):

| Event                  | Payload                          |
| ---------------------- | -------------------------------- |
| `credential_set`       | `{ref}`                          |
| `credential_read`      | `{ref}`                          |
| `credential_deleted`   | `{ref}`                          |
| `credential_migrated`  | `{ref}`                          |
| `master_key_relocated` | `{to: "file" \| "keychain"}`     |

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
