# Data Model — Secrets

The ciphertext files, the master key, the secret boundary's files, and a
handful of error codes. None of them holds a plaintext value: anything this
document listed beyond ciphertext, timestamps and where a value is allowed to
go would be another place for a secret to be inferred from.

## The ciphertext files

One file per ref, written by `EncryptedSecretStore`
(`infrastructure/secret/encrypted_store.py`):

| Ref | File | Class |
| --- | ---- | ----- |
| any ref | `~/.coffer/vault/secret/<ref>.enc` | vault |
| a machine-local ref (`proxy-token/…`: a proxy token unlocks only this machine's loopback model proxy) | `~/.coffer/local/secret/<ref>.enc` | local — never in the vault |

The file holds the Fernet token and a trailing newline; its path *is* the ref:
`/` separates directories, `.enc` is appended to the last segment, and each
segment is made a safe file name by percent-encoding every byte outside
`[A-Za-z0-9._-]` (and a leading `.`), so `channel/seatalk/app-secret` is
`secret/channel/seatalk/app-secret.enc`. A ref with an empty, `.` or `..`
segment is refused (`infrastructure/secret/ref_paths.py`). Files are
`0600`, the directories holding them `0700`.

| Field | Where it comes from |
| ----- | ------------------- |
| `ref` | the file's path under `secret/` |
| ciphertext | the file's bytes. Never logged, never audited; its plaintext leaves only through the desktop app's presence-gated reveal |
| `updated_at` | the token's own encryption time, which a Fernet token carries in clear, so it is right on every machine |
| `created_at` | when *this machine* first stored the ref: `~/.coffer/local/secret-boundary/times.json`, `{ref: iso time}`. A ref that arrived from another machine by sync has none, and is never counted as a value a person here has just supplied |
| `last_used_at` | when a consumer last had the value decrypted on this machine, stamped at most once a minute; a reveal or an import's read-back does not count: `~/.coffer/local/secret-boundary/last-used.json`, `{ref: iso time}`. Never synced; absent until first used |

Whether `vault/secret/` is committed is the vault repository's business:
`/secret/` is listed in `vault/.git/info/exclude` until the sync remote
carries secrets (`include_secret` on `local/sync/remote.json`, spec
vault-sync). When it does, a set or delete is one `daemon` commit naming the
ref only (operations `secret-set` / `secret-delete`), through the
vault's one writer with compare-and-swap. A ciphertext conflict in a sync round
is settled by the fresher Fernet time and never asked about.

There is no `kind` field and no link to any resource. A reference is resolved
by string, in the direction resource → secret only, which is why "who cites
this ref" is answered by scanning resource configs (see "Refuse to delete a
secret still in use") rather than by a join.

The store is synchronous, because sync callers — the MCP spawn path,
register-time probing — need a synchronous contract. Its `a*` facade is what
async callers use (see "Keep blocking store calls off the event loop"): a vault
write runs git.

## The master key

Not a vault file. Where it lives is chosen by how the build was made (see "Keep the
master key behind a storage port chosen by the build"):

| Location                | Where                                                                 | Build |
| ----------------------- | --------------------------------------------------------------------- | ----- |
| `keychain_access_group` | data-protection Keychain item, service `coffer`, account `master-key`, access group `<TEAMID>.coffer`, no presence flag | signed release, the only place |
| `file`                  | `~/.coffer/master.key`, mode `0600`                                   | development default |
| `keychain`              | OS keychain entry under ref `master-key`                              | development opt-in |

In a development build:

Resolution reads the file first, then the keychain (see "Resolve the master key
file-first and create it only for an empty store"). `MasterKeyManager` records
which location answered; that value is what `GET /api/v1/settings/secrets`
reports and what `PUT` compares against before relocating.

Relocation writes and verifies the destination, then removes the source, so the
intermediate state is "both copies exist" rather than "neither does".

## The secret boundary's files

Machine-local: an approval happened here, in front of this machine's app, so
the boundary's state is under `~/.coffer/local/secret-boundary/`, never in the
vault and never synced. Written by `FileBoundaryStore`
(`infrastructure/secret/boundary_store.py`), each file read whole and
changed atomically under its own lock; synchronous, because the gate is
consulted from the synchronous resolve path.

| File | Shape |
| ---- | ----- |
| `bindings.json` | `{"bindings": [binding, ...]}` — a ref approved for one slot of one destination, unique on `(ref, destination_kind, destination_uid, slot)` |
| `approvals.json` | `{"approvals": [approval, ...]}` — what waits for the desktop app |
| `settings.json` | `{key: value}` — `require_approval` |
| `times.json` | `{ref: iso time}` — when this machine first stored each ref (the ciphertext's `created_at`, above) |
| `last-used.json` | `{ref: iso time}` — when a consumer last had each ref decrypted here (`last_used_at`, above) |

| Binding field | Notes |
| ------------- | ----- |
| `ref`, `destination_kind`, `destination_uid`, `slot` | the key |
| `target_fingerprint` | `sha256(target)[:32]`; a new target is a new destination |
| `approved_at` | ISO time |
| `approval_id` | `null` when fresh, or approved while protection was off |

| Approval field | Notes |
| -------------- | ----- |
| `id` | the approval id |
| `op` | `bind` \| `disable_protection` |
| `status` | `pending` \| `approved` \| `rejected` \| `superseded` |
| `created_at`, `requested_by` | when and by whom |
| `ref`, `destination_kind`, `destination_uid`, `destination_label`, `slot`, `target`, `target_fingerprint` | what the approval is for, written out so a person can read it |
| `decided_at`, `decided_by` | set by the decision |

A destination is identified by `(destination_kind, destination_uid)` — a
resource's kind and uid, or `sync_remote` / `remote` — and a slot names the
place inside it (an environment variable, a header, `token`, `secret`). The
target a binding is pinned to is written out in the approval so a person can
read it; the binding keeps only its fingerprint. No plaintext is ever written
to any of these files.

## Secret references

A reference is not stored anywhere by this spec. It is a string inside another
kind's resource config, and each kind declares how to find its own:

```
Kind.secret_ref_extractor: (config) -> {logical_key: ref}
```

`mcp_server` maps env var names and header names to refs; `channel` maps a bot
token; `provider` maps an API key. A kind without an extractor declares no
secrets, is never probed at register time, and releases nothing on delete.

## Error codes

| Code                   | Raised when                                                        | Surfaced as |
| ---------------------- | ------------------------------------------------------------------ | ----------- |
| `SECRET_MISSING`   | A ref a configuration cites does not resolve                        | 400 / startup failure at the citing surface |
| `SECRET_IN_USE`    | Delete attempted while a resource config still cites the ref | 409, with `details.references` naming each citer by kind and current label (`channel 'my-bot'`) — never by uid, which is not what the user sees on the page they must visit next |
| `SECRET_LOCKED`    | The OS keychain refused or could not be read                        | 503 |
| `SECRET_UNREADABLE`| Ciphertext will not decrypt with the current key                   | 5xx, naming the ref |
| `MASTER_KEY_MISSING`   | Ciphertext exists and no key resolves, or the key is corrupt | Fatal at daemon startup, naming the path |
| `SECRET_BINDING_PENDING` | A secret would go to a destination or target nobody approved | 409, `details.approval_ids`; the CLI exits `9` |
| `PRESENCE_GRANT_INVALID` | A presence grant is missing, expired, reused, for another operation or target, or not signed with the grant key | 403 |
| `APPROVAL_NOT_FOUND` / `APPROVAL_NOT_PENDING` | An approval id that does not exist, or was already decided | 404 / 409 |
| `SECRET_NAME_INVALID` / `SECRET_NOT_FOUND` | A `coffer run` name that is not one `secret/` segment, or is not stored | 422 / 404 |

## Audit events

Written by this spec into the shared `audit_log` table in `runs.db` (whose
shape is the framework's):

| Event                  | Payload                          |
| ---------------------- | -------------------------------- |
| `secret_set`       | `{ref}`                          |
| `secret_revealed`  | `{ref}` — the desktop app's presence-gated reveal |
| `secret_deleted`   | `{ref}`                          |
| `master_key_relocated` | `{to}` |
| `master_key_exported`  | `{path, fingerprint}` — the desktop app's key backup |
| `secret_resolved`      | `{name, argv0, cwd}` — one `coffer run` resolve, never the rest of argv |
| `secret_approval_requested` / `_approved` / `_rejected` | `{approval_id, op, ref}` |
| `secret_imported`      | `{name, path}` — a plaintext file value moved into the store |

No payload carries a value (see "Keep secret values out of secret audit
events"). `secret_deleted` is written both by the delete route and by the
release that follows a resource deletion (see "Release unshared references when
a resource is deleted").

## Invariants enforced by importlinter

| Contract | Subject                                                                 |
| -------- | ------------------------------------------------------------------------ |
| `keyring` confinement | Only `coffer.infrastructure.secret` may import `keyring`. The CLI, every surface and every other kind are outside it. |

That contract predates this spec's extraction; the fence is what makes "Confine
key management to the secret package" checkable rather than aspirational.
