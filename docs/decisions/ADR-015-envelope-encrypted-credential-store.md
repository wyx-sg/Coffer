# ADR-015: Envelope-Encrypted Credential Store

**Status**: Accepted
**Date**: 2026-06-12
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md` (Credentials invariant — amended to v0.2.0), spec `001-mcp-gateway` (data-model: `credentials` table, audit events), [ADR-008](ADR-008-distribution-pyinstaller-tauri-sidecar.md) (unsigned macOS distribution)

## Context

Coffer originally stored every registered secret directly in the OS keychain
(macOS Keychain, Windows Credential Manager, Linux Secret Service), with the
daemon as the sole keychain owner and `keyring` confined to one adapter.

On macOS this broke down in daily use. The keychain pins each entry's access
control list to the **cdhash** of the binary that created it. Coffer's daemon
is distributed **unsigned** ([ADR-008](ADR-008-distribution-pyinstaller-tauri-sidecar.md)
defers Apple notarisation, which needs a paid Apple Developer account). Every
rebuild of the daemon produces a new cdhash, so macOS treats the new binary as
a different application and **re-prompts for keychain access — once per secret,
on every rebuild**. For a developer iterating on Coffer, or even just receiving
an updated release, this is a wall of modal password prompts.

The only real fix for the prompt itself is a **stable code-signing identity**: a
paid Apple Team ID signature would keep the cdhash-pinned ACL valid across
rebuilds. That is a dead end for a free, open-source, self-distributed tool — we
are not going to gate the credential UX on a paid Apple account.

So the keychain, as the primary secret store, is the wrong default. We need a
secret store that works with zero prompts under an unsigned binary, while still
offering keychain-grade hardening to users who want it.

## Decision

**Move to envelope encryption: store secrets as Fernet ciphertext in SQLite, and
keep a single Fernet master key in a `0600` file beside the database by default
(OS keychain opt-in).**

- **Ciphertext at rest.** Secrets live only as Fernet ciphertext in a
  `credentials` table in `~/.coffer/coffer.db`. Plaintext exists in memory
  solely between decrypt and the spawn/header injection that consumes it —
  never in logs, audit, or structured events (the pre-existing invariant is
  unchanged).
- **Master key, two locations, exactly one active.** The Fernet master key
  lives in **either** `~/.coffer/master.key` (a `0600` file — the **default**,
  zero keychain prompts) **or** the OS keychain (service `coffer`, ref
  `master-key` — opt-in via Settings → Security or
  `coffer credentials storage --set keychain`; macOS may prompt at most once
  per daemon start).
- **File-first, crash-safe resolution.** The daemon resolves the key file
  before the keychain. Relocation moves **only the master key** and deletes the
  old copy **last**, so an interrupted relocation always resolves back to a
  working state. We **relocate the key, never re-encrypt the data**: the
  ciphertext column is untouched when storage mode changes — far less code, no
  bulk re-encryption window, and nothing to corrupt mid-switch.
- **Fail-closed startup.** A new master key is generated **only when the
  `credentials` table is empty**. Ciphertext present with no resolvable key is
  a fatal, actionable startup error (`MasterKeyMissing`) — Coffer refuses to
  start rather than silently lose access to existing secrets.
- **One-time legacy migration.** On startup the daemon runs a best-effort
  migration: legacy keychain secrets whose refs are cited by registered
  resources are encrypted into the store, audited per ref as
  `credential_migrated`. A locked keychain skips and retries next startup.
- **Surface and audit changes.** `/api/v1/keychain` → `/api/v1/credentials`
  (POST, GET/{ref}, GET/{ref}/exists, DELETE/{ref}); new
  `GET/PUT /api/v1/settings/credentials` toggles `master_key_storage`
  (`"file"` | `"keychain"`, PUT relocates and audits `master_key_relocated`).
  CLI `coffer keychain …` → `coffer credentials …` plus
  `coffer credentials storage [--set file|keychain]`. Audit events
  `credential_set` / `_read` / `_deleted` / `_migrated` and
  `master_key_relocated` (legacy `keychain_*` stay renderable). `keyring`
  remains confined to `coffer.infrastructure.credentials` (importlinter
  Contract 4 unchanged), now serving only the master key and the legacy
  migration. The daemon remains the sole owner of secret material; CLI and web
  go through the HTTP API.

This required amending the constitution's Credentials invariant (v0.1.0 →
v0.2.0): from "only the credential module accesses the OS keychain; no plaintext
in the DB" to "secrets only as Fernet ciphertext in the `credentials` table;
master key managed solely by `coffer.infrastructure.credentials`, file default /
keychain opt-in".

## Consequences

**Positive**

- **Zero keychain prompts by default**, even under an unsigned, frequently
  rebuilt daemon — the original problem is gone.
- **At most one prompt per daemon start** in keychain mode, and only for the
  single master key — not one per secret.
- **Honest, improvable threat model.** Default mode keeps the master key beside
  the database, i.e. the same `~/.coffer/` boundary that already excluded a
  reader of that directory — no regression. Keychain mode is a real upgrade: it
  defends against offline exfiltration of `~/.coffer/` contents.
- **Crash-safe storage switching** with no re-encryption window.

**Negative / new obligations**

- **Backup caveat.** `coffer.db` now holds ciphertext; restoring it requires the
  matching `master.key` (or keychain entry). Users must back up the master key
  alongside the database, and docs must say so.
- **Constitution amendment** (v0.2.0) and a one-time legacy migration path to
  carry, both shipped with this change.
- **Default mode does not defend against a reader of `~/.coffer/`** — the key
  sits beside the data. This is the same boundary as before, stated plainly so
  no one over-trusts the default.

## Alternatives Considered

**Stay on per-secret keychain storage and add code signing.** Rejected. The only
fix for the cdhash re-prompt is a stable signing identity, which needs a paid
Apple Team ID. We will not gate the credential UX on a paid Apple account for a
free self-distributed tool. Envelope encryption removes the prompts without any
signing dependency.

**Re-encrypt all ciphertext when switching storage mode.** Rejected. Relocating
only the master key (the file ↔ keychain move) is a tiny, crash-safe operation;
re-encrypting every row would add a bulk-rewrite window with a half-migrated
failure mode and far more code, for no security gain — the data key is the same
either way.

**Derive the key from a user passphrase (no stored key).** Rejected for the
default. It would re-introduce a prompt (the passphrase) on every daemon start,
defeating the zero-prompt goal, and a forgotten passphrase is unrecoverable. The
keychain opt-in already covers users who want the key off the disk.

**Keep the keychain as default, file as opt-in.** Rejected. That keeps the
re-prompt wall as the out-of-box experience on the most common developer
platform. The mode that works painlessly under an unsigned binary must be the
default; hardening is the opt-in.
