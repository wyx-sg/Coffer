# Spec 010 — Vault Export and Import

> 中文版: [spec.zh.md](./spec.zh.md)

Move one Coffer vault to another of the user's own machines by exporting it to
a directory and importing that directory back. No transport medium, no remote,
no background replication. Background and alternatives in
[ADR-016](../../docs/decisions/ADR-016-vault-export-import.md).

## Why

A developer sets up a new laptop, or wants their desktop to start from what
their laptop already knows. Today each machine is an island: knowledge,
registered resources, and credentials have to be rebuilt by hand.

This feature writes the vault to a directory the user picks, and reads one
back. Getting that directory to the other machine — `scp`, a USB drive, their
own git repo — is the user's business and outside this spec. Because the export
is ordinary local file output, it needs no exception to the constitution's
local-first principle.

## What exports

- **Knowledge** — the markdown files under `~/.coffer/knowledge/<scope>/` (files
  are already the source of truth). Since the 2026-09-10 knowledge-layer merge
  there is one root; `~/.coffer/memory/` no longer exists.
- **Skills** — the master skill store under `~/.coffer/skills/`.
- **Config resources** — `mcp_server`, `agent`, `skill`, `channel` definitions
  (system of record is SQLite; serialized to text for transport).
- **Shared state** — module-owned areas that are part of the vault rather than
  of one machine (e.g. channel peer pairings, knowledge scope labels).
- **Credentials** — Fernet **ciphertext only**, and only when explicitly
  requested.

## What does not export (machine-local)

Logs, `coffer.db` (a rebuildable index), `daemon.json`, PID files, port
allocations, chat history, audit log, and any runtime artifact. The master key
is **never** written into an export.

## Concepts

- **Export bundle** — a directory the user names. Its layout:

  ```
  manifest.json                  # bundle schema version + creation time
  knowledge/                     # mirror of ~/.coffer/knowledge
  skills/                        # mirror of ~/.coffer/skills (master skill store)
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  state/<area>/...yaml           # module-owned shared state
  credentials/<ref>.enc          # Fernet ciphertext blob, opt-in; never the master key
  ```

- **Export** — write local vault state into a bundle directory (files mirrored,
  resources serialized, ciphertext dumped when requested).
- **Import** — apply a bundle back into the local vault (files mirrored back +
  reindex, resources reconciled into SQLite, ciphertext imported).
- **Import reconciliation** — reconciling registry rows is not enough: some
  resource config drives machine-local side-effects that each kind's own
  service performs on its front door (provider activation projects into the
  agent's native config file; an agent's registration installs its shim and
  session hook; a skill binding materializes a symlink). Import runs each
  kind's post-import hook so an imported resource is as usable as one
  registered by hand on this machine.

## Determinism

Resource serialization MUST be deterministic — sorted keys, normalized
timestamps, machine-local fields stripped. Two exports of an unchanged vault
produce byte-identical files. This is what makes a bundle diffable, so a user
can read exactly what they are about to carry, and can `diff` two bundles to
see what changed between machines.

## Path portability

An export written on one machine must import on another whose home directory
differs. Absolute paths under `$HOME` are stored relative to a `~` sentinel on
export and expanded against the importing machine's home on import. Paths
outside `$HOME` are stored verbatim; they may not resolve on the other machine,
which surfaces as an import error for that resource rather than a silent
mismatch.

## Import semantics

- **The bundle wins.** For every resource the bundle contains, the importing
  vault takes the bundle's version. There is no arbitration, because there is
  no concurrent writer: the user chose the direction when they ran the command.
- **Import never deletes.** A resource the local vault holds and the bundle
  does not is left untouched. A bundle is a snapshot of one machine, not an
  assertion about what should exist everywhere.
- **Per-resource failures are reported, not fatal.** A resource that cannot be
  applied on this machine (e.g. an agent whose `config_dir` does not exist)
  is reported in the import result with its ref and reason; every other
  resource still imports.
- **A newer bundle is refused.** A bundle whose `manifest.json` declares a
  schema version this build does not know fails closed with a clear error
  rather than importing a partially-understood bundle.

## Credentials

Credential material travels as Fernet ciphertext and **only when the user asks
for it**: export omits credentials unless `--with-credentials` is given,
because an export directory is easy to leave somewhere careless.

The master key is never written into a bundle. It is bootstrapped onto the
other machine out-of-band via `coffer sync key export` / `coffer sync key
import`. A machine that holds ciphertext but not the key reports
`credentials_locked` and refuses to spawn the affected resources — it never
silently fails decryption.

**The key crosses as material, not as a path.** `POST /sync/key/export` takes an
empty body and returns `{"material": "<fernet key text>"}`; `POST
/sync/key/import` takes `{"material": "<fernet key text>"}` and returns the refs
that remain locked. The daemon never opens a filesystem path a caller named.
Each surface then does its own file I/O: the CLI writes `coffer sync key export
<path>` to that path itself (mode `0600`) and reads the file back for `key
import`; the web UI hands the material to a browser download and reads an
`<input type="file">` for the import.

The reason is the web UI. Both directions used to go through the daemon's
native save/open dialogs — the daemon ran `osascript`/`zenity` on the user's
behalf and returned a chosen path — and those dialogs are removed. A browser has
no absolute path to hand the daemon anyway, while `<input type="file">` hands
over the *contents* directly, which is strictly more useful than a path that has
to survive a round-trip.

The trade, stated: the key material now crosses the token-guarded loopback API,
where before it did not. That is acceptable. Whoever asked to export the master
key was going to hold the plaintext either way — that is what exporting it
means — and the alternative was the daemon executing a native dialog binary on
the user's behalf to avoid a hop that never left `127.0.0.1`.

## Scope

Resource `scope` (a list of agent names,
[ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.md)) rides the
resource document through export and import unmodified — it is an ordinary
field, with no dedicated machinery. An imported resource that is out of scope
for every agent on this machine is registered and visible, just not activated.

## Surfaces

| Surface | Operation |
| --- | --- |
| CLI | `coffer sync export <dir> [--with-credentials]` · `coffer sync import <dir>` · `coffer sync key export <file>` / `coffer sync key import <file>` |
| HTTP | `POST /api/v1/sync/export` · `POST /api/v1/sync/import` · `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| UI | Settings → Sync: an export button and an import button, each opening the daemon-hosted native **directory** picker (spec 004 FR-042), plus the master-key card — which uses the browser's own download / `<input type="file">`, not a daemon dialog |

Both operations report a summary: counts per area, the resources that failed,
and the bundle path.

## Acceptance Scenarios

### Scenario: export a vault to a directory

- **Given** a vault with knowledge, skills, and registered resources,
- **When** the user runs `coffer sync export <dir>`,
- **Then** the directory holds `manifest.json`, the mirrored file trees, one
  deterministic YAML per config resource, and **no** `credentials/` directory,
  and the command reports counts per area.

### Scenario: an unchanged vault exports byte-identically

- **Given** a vault exported to a directory,
- **When** the user exports the unchanged vault again to a second directory,
- **Then** every file in the two directories is byte-identical apart from the
  manifest's creation time.

### Scenario: import a bundle into an empty vault

- **Given** a bundle exported from another machine and a vault with no
  resources,
- **When** the user runs `coffer sync import <dir>`,
- **Then** the knowledge and skill trees are mirrored in, the SQLite
  index is rebuilt from them, every config resource is registered, and each
  kind's post-import hook has run so the resources are usable without further
  action.

### Scenario: the bundle wins over an existing local resource

- **Given** a local `mcp_server:files` whose config differs from the one in the
  bundle,
- **When** the user imports the bundle,
- **Then** the local resource matches the bundle's version afterwards, and the
  change is audited.

### Scenario: import never deletes a local-only resource

- **Given** a local `mcp_server:local-only` that the bundle does not contain,
- **When** the user imports the bundle,
- **Then** `mcp_server:local-only` is still registered and unchanged.

### Scenario: config paths follow each machine's home

- **Given** a bundle exported on a machine whose home is `/Users/a`, holding an
  agent whose `config_dir` was `/Users/a/.claude`,
- **When** it is imported on a machine whose home is `/home/b`,
- **Then** the imported agent's `config_dir` is `/home/b/.claude`.

### Scenario: a resource that cannot apply here is reported, not fatal

- **Given** a bundle holding an agent whose `config_dir` does not exist on this
  machine, alongside three importable resources,
- **When** the user imports the bundle,
- **Then** the three resources import, and the result names the failed agent
  ref with its reason.

### Scenario: credentials are omitted unless requested

- **Given** a vault holding credentials,
- **When** the user exports without `--with-credentials`,
- **Then** the bundle has no `credentials/` directory, and importing it leaves
  the local credential store untouched.

### Scenario: master key never enters the bundle

- **Given** an export taken with `--with-credentials`,
- **When** the bundle is inspected,
- **Then** it holds Fernet ciphertext blobs and no key material, and importing
  it onto a machine without the key leaves those resources `credentials_locked`
  rather than failing decryption silently.

### Scenario: an older build refuses a newer bundle

- **Given** a bundle whose `manifest.json` declares a schema version newer than
  this build knows,
- **When** the user imports it,
- **Then** the import fails closed with a clear error and nothing is applied.

### Scenario: a scoped resource imports dormant

- **Given** a bundle holding an `mcp_server` scoped to an agent that is not
  registered on this machine,
- **When** the user imports the bundle,
- **Then** the server is registered and visible, and the gateway does not
  expose its tools to any session on this machine.

## Out of scope

- **Getting the bundle between machines.** `scp`, a USB drive, or the user's
  own git repository — Coffer writes and reads a directory and does not
  transport it.
- **Continuous convergence.** Two machines can drift apart, and Coffer will not
  notice or reconcile that; the fix is a manual re-export
  ([ADR-016](../../docs/decisions/ADR-016-vault-export-import.md)).
- **Merging two divergent vaults.** Import is last-writer-wins per resource,
  not a three-way merge.
- **A hosted sync endpoint.** Would require a constitutional amendment.
