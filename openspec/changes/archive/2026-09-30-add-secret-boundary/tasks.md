# Tasks

## 1. Backend
- [x] 1.1 Domain vocabulary: destinations, bindings, approvals, standalone names, masking
- [x] 1.2 Migration 0112 and the sync store for bindings, approvals and switches
- [x] 1.3 `SecretBoundary` gate, `PresenceGrants`, guarded `CredentialResolver`
- [x] 1.4 Wire every consumer with its destination: MCP spawn and test, channel adapters and SeaTalk websockets, sync push
- [x] 1.5 Remove `GET /credentials/{ref}` and `POST /sync/key/export`; presence routes, approvals routes, resolve route, scan and import routes, `/settings/secret-boundary`
- [x] 1.6 Full credential listing with references, unreferenced, bindings and local readability; delete refused while a skill cites a standalone secret
- [x] 1.7 Master key storage port: access-group backend, upgrade move, development fallback
- [x] 1.8 `secrets_readable_by_local_processes` on MCP stdio resources

## 2. CLI
- [x] 2.1 Remove `credentials get --show` and `sync key export`
- [x] 2.2 `credentials approvals|reject|scan|import`; `--wait` and exit 9 on `mcp add`, every `edit`, `channel add`, `sync remote set`, `credentials set`
- [x] 2.3 `coffer run` with masking and pass-through exit status
- [x] 2.4 `secrets.require_approval` config key

## 3. Desktop shell
- [x] 3.1 Presence check (LocalAuthentication, fresh context per operation; dev fallback alert)
- [x] 3.2 Grant key from the Keychain access group (production) or the key file (development); grant signing
- [x] 3.3 IPC commands: reveal, key backup export, approve, presence mode; approval notification watcher

## 4. Frontend
- [x] 4.1 Generated types (`make contracts`)
- [x] 4.2 Presence actions and the approvals sheet through the credential supplier's module; "Open in Coffer app" in the browser; key export on the Sync page moves to the app

## 5. Docs
- [x] 5.1 Security architecture page and a secrets guide (principles, usage, residual risks)
- [x] 5.2 Credentials, vault-sync and CLI docs; ADR implementation notes and the access-group spike as an open question
