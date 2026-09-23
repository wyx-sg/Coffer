# Implementation Plan: Credentials

**Spec**: [./spec.md](spec.md)
**Status**: Accepted

## Summary

One encrypted store, one master key, and the surfaces that manage them. Every
other spec holds a reference; this one holds the secret. The shape is envelope
encryption: secrets are Fernet ciphertext in SQLite, and the only secret material
outside the database is the Fernet key, which lives in a `0600` file beside the
database or — opt-in — in the OS keychain.

See [./spec.md](spec.md) for the user-visible contract and
[Envelope-Encrypted Credential Store](../../../docs/decisions/envelope-encrypted-credential-store.md)
for why envelope encryption rather than the keychain alone.

## Technical Context

| Dimension                | Value                                                                                                   |
| ------------------------ | --------------------------------------------------------------------------------------------------------- |
| **Language / Version**   | Python 3.12+                                                                                            |
| **Primary Dependencies** | `cryptography` (Fernet), `keyring` (confined to this spec), stdlib `sqlite3`                            |
| **Storage**              | The `credentials` table in `~/.coffer/coffer.db`; `~/.coffer/master.key` or an OS keychain entry         |
| **Testing**              | Unit (key resolution, relocation, store round trip) + integration (routes, CLI, in-use refusal) + a leak scan that greps every artifact for the literal secret |
| **Surfaces**             | REST (`/api/v1/credentials/*`, `/api/v1/settings/credentials`), CLI (`coffer credentials …`), and one Settings card for the key's location |
| **Constraints**          | No plaintext outside memory; `keyring` confined by an importlinter contract; no blocking store call on the event loop |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                 |
| ----------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | ✅         | The store is a local SQLite table; the key is a local file or the local keychain. Nothing reaches a network.            |
| **II. Spec-as-Truth**                     | ✅         | Every acceptance scenario is owned by at least one test (audited by `make verify-acceptance`).                          |
| **Credentials: encrypted store**          | ✅         | This spec *is* that clause. The constitution states the invariant for every kind; here it is routes, commands and tests. |
| **Persistence: SQLite for control plane** | ✅         | One table, no file-backed content of its own beyond the key.                                                            |
| **Network defaults: loopback-only**       | ✅         | Inherited from spec daemon; this spec adds no listener.                                                                 |

## Project Structure

### Documentation (this feature)

```text
specs/credentials/
├── spec.md              # user-visible contract
├── plan.md              # this file
├── data-model.md        # the table, the key, the refs, the error codes
├── contracts/
│   └── api.openapi.yaml # the credential + key-location routes
└── quickstart.md        # how a user drives it
```

### Source code

```text
backend/coffer/
├── domain/
│   └── credential_errors.py              # CredentialMissing / InUse / Locked / Unreadable / MasterKeyMissing
├── application/
│   ├── credential_migration.py           # legacy keychain → encrypted store (FR-027)
│   └── resource_delete_ops.py            # release of refs nothing else cites (FR-024)
├── infrastructure/
│   └── credentials/
│       ├── encrypted_store.py            # Fernet ciphertext in the `credentials` table + the a* facade
│       ├── master_key.py                 # file-default / keychain-opt-in resolution, relocation, transfer
│       └── keyring_adapter.py            # the ONLY module importing `keyring`
└── surfaces/
    ├── http/
    │   ├── credential_routes.py          # /api/v1/credentials/*
    │   ├── credential_composition.py     # DI singletons + startup key resolution + migration
    │   └── settings_routes.py            # /api/v1/settings/credentials — the key's location
    └── cli/
        └── credentials_cmd.py            # coffer credentials set|get|list|delete|storage
```

```text
frontend/src/
└── pages/settings/SecuritySettings.tsx   # the master key's location card (FR-010)
```

`resource_service.py`'s credential probing and `resource_delete_ops.py`'s
release live in the kind-agnostic core rather than here, because they run
inside another kind's write path. They are this spec's rules executed at the
framework's seam; the store they call is this spec's.

## Layers and boundaries

**The store is sync on purpose.** `EncryptedCredentialStore` opens a short-lived
stdlib `sqlite3` connection per call, because the MCP spawn path and
register-time probing are synchronous and would otherwise need an event loop
they do not have. The cost is FR-004: an async caller that touches the sync
method on the loop deadlocks against the aiosqlite coroutine holding the write
lock, so every async caller goes through the `a*` facade or `asyncio.to_thread`.

**The key has one manager, and one importer.** `MasterKeyManager` is the only
thing that reads or writes key material, and `keyring_adapter.py` is the only
module that imports `keyring` — enforced by an importlinter contract rather than
by convention. The CLI in particular is outside it: it goes through the daemon
for everything, so the key has a single reader per machine.

**Startup order is a correctness property.** `init_credential_store` counts the
`credentials` rows *before* resolving the key, so `allow_create` is true only on
an empty store (FR-007). A corrupt key is caught by constructing the Fernet and
turned into `MASTER_KEY_MISSING` naming the path (FR-008), never into a silent
regeneration.

**Deletion is refused from the citing side.** `find_credential_citations` walks
registered resource configs through each kind's extractor. There is no foreign
key to enforce this, and there could not be: the ref lives inside a JSON config
column belonging to another kind.

**Rollback lives at the writing surface.** FR-023 is implemented where the
secret is written — the MCP import dialog, the channel register flow, the MCP
edit save — because only the caller knows whether the registration that followed
its write succeeded. Each is best-effort and logs rather than surfacing a second
error over the first.

## Complexity Tracking

| Decision                                         | Why needed                                                                                                          | Simpler alternative rejected because                                                                                              |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Envelope encryption rather than the OS keychain alone | One keychain prompt per secret per daemon start is unusable, and Linux keyrings are frequently absent.              | Storing every secret in the keychain made the daemon unstartable unattended and tied the vault to one OS.                            |
| Two key locations rather than one                | The file default matches the threat model (an attacker who can read `~/.coffer/` is out of scope); the keychain survives exfiltration of that directory. | A single location either costs a prompt on every start or offers nothing to users who want the harder posture.                       |
| A sync store with an async facade                | Sync callers (spawn, probe) exist and cannot be made async without dragging an event loop into the MCP supervisor.  | An async-only store would force every sync caller to create a loop, which is where the deadlock this design avoids comes from.        |

## Cross-Reference Index

- Spec contract: [spec.md](spec.md)
- Data model: [data-model.md](data-model.md)
- Wire contract: [contracts/api.openapi.yaml](contracts/api.openapi.yaml)
- Quickstart: [quickstart.md](quickstart.md)
- Decision record: [Envelope-Encrypted Credential Store](../../../docs/decisions/envelope-encrypted-credential-store.md)
- Constitution: [`.specify/memory/constitution.md`](../../../.specify/memory/constitution.md)
