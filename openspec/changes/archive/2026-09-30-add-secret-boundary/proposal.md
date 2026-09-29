# Add the secret boundary

## Why

A prompt-injected coding agent runs as the user and can already read
`~/.coffer/daemon.json`, call every management route and run every `coffer`
command. Three of those paths hand it a secret outright
(`GET /api/v1/credentials/{ref}` / `coffer credentials get --show`,
`coffer sync key export`), and one more lets it take a secret without reading
it: register an MCP server whose environment cites an existing secret and whose
command is the attacker's script, and Coffer delivers the secret to it. ADR
[Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or
Sends It Somewhere New](../../../docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
moves Coffer's boundary to the secret itself; this change implements it.

## What Changes

- **No route, command or tool returns a secret's plaintext or the master key.**
  `GET /api/v1/credentials/{ref}`, `coffer credentials get --show`,
  `POST /api/v1/sync/key/export` and `coffer sync key export` are removed.
  `coffer credentials get` checks presence only.
- **Plaintext reaches only a present human, in the desktop app.** The shell runs
  a LocalAuthentication check (Touch ID or the login password,
  `deviceOwnerAuthentication`) for every reveal, copy, key backup and approval,
  with no reuse window, then signs a one-time, operation-bound grant with a key
  derived from the master key. The daemon releases a value
  (`POST /credentials/presence/reveal`), writes a key backup into a directory
  the person picked (`POST /credentials/presence/master-key-export`) or applies
  an approval only against a grant that verifies. The browser UI shows "Open in
  Coffer app" for these actions.
- **A secret goes to a new destination only with a person's approval.** Every
  consumer that injects a secret — an MCP server's environment variable or
  header, a channel adapter's credential, the sync remote's push token — asks
  the boundary first, naming the destination and the target that receives the
  value (a stdio server's full command line, an HTTP URL, a git URL). An
  unapproved binding becomes a pending approval and nothing is injected. The
  desktop app raises a notification and an in-app sheet; the CLI prints
  "waiting for approval in the Coffer app" and exits `9`, or waits with
  `--wait`. Bindings in use at upgrade are adopted once; a value supplied
  moments ago needs no approval. Replacing the value of a secret in use, and
  switching the protection off (`secrets.require_approval`), wait for the same
  approval. The boundary exposes one service call
  (`SecretBoundary.require`) for the destinations still to come: a provider
  connection's base URL and a custom tool's auth.
- **`coffer run [--secret NAME|ENV=NAME]… [--env-file FILE] -- cmd`** resolves
  standalone `secret/<name>` values (cited as `coffer://secret/<name>`) into
  one child's environment only, masks exact values in its output as `***`, and
  audits each resolution as `secret_resolved`. It keeps secrets out of files
  and transcripts by accident; it does not hide them from the agent that runs
  the command, and the docs say so.
- **Secrets page backend.** `GET /api/v1/credentials` lists every stored ref as
  well as every cited one, with what uses it (resources and skills citing the
  URI), `unreferenced`, the approved and pending bindings, and whether another
  local process can read the value where Coffer puts it. A delete is refused
  while a skill cites a standalone secret, as it already is while a resource
  does. `POST /credentials/scan` and `POST /credentials/import` (`coffer
  credentials scan|import`) find plaintext secrets in `~/.coffer/secrets/*.env|
  *.json` and in skills and move them into the store, leaving references.
- **Master key storage behind a port chosen by the build.** A Keychain
  access-group backend (data-protection keychain, Team-ID access group, no
  presence flag) for signed releases, with the upgrade move from the file or the
  legacy keychain item; the `0600` file and the legacy item stay the
  development fallback. Which one a build uses is fixed when it is built.
- **MCP stdio servers whose environment carries a secret** are reported as
  readable by other processes on this Mac
  (`secrets_readable_by_local_processes` on the resource).

## Capabilities

### Modified Capabilities
- `credentials`: the plaintext routes and commands go; the presence grant, the
  approvals, `coffer run`, the full listing, the plaintext scan and the build-
  chosen key storage arrive.
- `mcp-gateway`: a server's secrets are injected only once their binding is
  approved; stdio servers carrying a secret are marked.
- `desktop-app`: the shell gains the presence check, the grant, the approval
  notification and sheet, and the key backup export.
- `vault-sync`: `key export` leaves the CLI and the API; a push token pointed at
  a new URL waits for approval.

## Impact

- Backend: `domain/secrets.py`, `domain/secret_masking.py`,
  `application/credentials/{boundary,presence,resolver}.py`,
  `infrastructure/credentials/{boundary_store,master_key_backends,build_identity,plaintext_scan}.py`,
  `surfaces/http/{credential_boundary_routes,secret_boundary_wiring,credential_schemas}.py`,
  `surfaces/cli/{run_cmd,_approvals}.py`; migration `0112` (three tables).
- Desktop shell: presence, grant, key and approval modules; four IPC commands.
- Frontend: the desktop presence actions and approval sheet in the credential
  supplier's module; "Open in Coffer app" in the browser; generated types.
- Docs: security architecture, a secrets guide, credentials and vault-sync
  guides, the four ADRs' implementation notes.
