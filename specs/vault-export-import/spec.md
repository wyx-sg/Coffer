# Spec — Vault Export and Import

> 中文版: [spec.zh.md](./spec.zh.md)

Move one Coffer vault to another of the user's own machines by exporting it to
a directory and importing that directory back, and keep a recoverable copy by
pushing those exports to a git remote the user owns. One-way backup only: no
convergence, no merging, no arbitration between machines. Background and
alternatives in
[Vault Export and Import](../../docs/decisions/vault-export-import.md).

## Why

A developer sets up a new laptop, or wants their desktop to start from what
their laptop already knows. Today each machine is an island: knowledge,
registered resources, and credentials have to be rebuilt by hand.

This feature writes the vault to a directory the user picks, and reads one
back. Because the export is ordinary local file output, it needs no exception
to the constitution's local-first principle.

Two failures that moving a directory by hand does not survive: the disk dies,
and something is deleted but only noticed a week later. The first needs a copy
beyond this machine; the second needs history deep enough to reach past the
mistake. So the vault can also be backed up, on a timer, to a git repository
the user owns — a bounded exception to the local-first principle (constitution
0.5.0), because the remote is a backup and never a system of record.

## What exports

- **Knowledge** — the markdown files under `~/.coffer/knowledge/<scope>/` (files
  are already the source of truth). Since the 2026-09-10 knowledge-layer merge
  there is one root; `~/.coffer/memory/` no longer exists.
- **Skills** — the master skill store under `~/.coffer/skills/`.
- **Config resources** — `mcp_server`, `agent`, `skill`, `channel` definitions
  (system of record is SQLite; serialized to text for transport).
- **Shared state** — module-owned areas that are part of the vault rather than
  of one machine (e.g. channel peer pairings, knowledge scope labels, MCP
  capability preferences, and the **agent plugin inventory**).

  The plugin inventory is an **inventory, not a replicator**: export writes
  down which plugins each agent has on this machine; import stores that list
  and writes nothing into any agent's configuration. Coffer removed its plugin
  write paths because hand-writing another tool's private config format
  corrupts it silently when the format moves (spec agent-registry), and it never had an
  install path at all — so "install these for me" is not on offer, and would
  have had to be written from scratch either way. What the list gives is what
  no single agent can: Codex on a new laptop has no idea which plugins the old
  one had, because that fact exists only on the machine holding them.
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
- **Backup remote** — at most one git repository, owned by the user, that
  Coffer pushes exports to. Configured with a URL, a branch, a push credential
  reference, an interval, and whether exports carry credential ciphertext.
  Disabled until the user configures it.
- **Backup working tree** — the directory the timer exports into, which is also
  a git working tree (`~/.coffer/knowledge`-style local state, not a second
  vault). Default `~/.coffer/sync`; an existing repository there is adopted
  with its history intact rather than re-initialized.
- **Backup run** — one export into the working tree, a commit if the result
  differs from the last one, then a push. Commit and push are separate
  outcomes: a run can commit successfully and fail to push.
- **Restore** — fetch the backup remote, optionally move the working tree to an
  earlier revision, then run an ordinary import from it.
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
empty body and returns the Fernet key text as a `material` field;
`POST /sync/key/import` takes the same `material` field and returns the refs
that remain locked. The daemon never opens a filesystem path a caller named.
Each surface then does its own file I/O: the CLI's `key export <path>` writes
the material to that path itself (mode `0600`), its `key import <path>` reads
the file back, and the web UI hands the material to a browser download and reads
a file input for the import.

The reason is the web UI. Both directions used to go through the daemon's
native save/open dialogs — the daemon ran `osascript`/`zenity` on the user's
behalf and returned a chosen path — and those dialogs are removed. A browser has
no absolute path to hand the daemon anyway, while a file input hands over the
*contents* directly, which is strictly more useful than a path that has to
survive a round-trip.

The trade, stated: the key material now crosses the token-guarded loopback API,
where before it did not. That is acceptable. Whoever asked to export the master
key was going to hold the plaintext either way — that is what exporting it
means — and the alternative was the daemon executing a native dialog binary on
the user's behalf to avoid a hop that never left `127.0.0.1`.

## Backup

At most one backup remote exists, and it is off until the user sets it. Once
set, a worker runs a backup on an interval — immediately on daemon start, then
every `interval` (default one hour) — and the user can trigger one by hand.

A run exports into the working tree using the same serializer and the same
rules as any other export, then:

- If the export matches what the tree already holds, the run makes **no
  commit**. Determinism is what makes this reliable: an unchanged vault
  produces an unchanged bundle, so the backup history records changes and not
  ticks. `manifest.json` is the one exception the determinism rule above
  already names — every export restamps its creation time — so a staged diff
  that touches nothing else is a restamped manifest, not a change, and does
  not earn a commit.
- Otherwise it commits, with a message naming the counts per area.
- Then it pushes to the configured branch.

**A commit is never rolled back because a push failed.** The local history is
the first layer of recovery, and the next run pushes whatever is outstanding.
A run that cannot authenticate, cannot reach the network, or is rejected by the
remote records the failure and surfaces it; it never kills the worker and never
blocks the next run.

Whether a backup carries credential ciphertext is fixed when the remote is
configured, not per run — the same opt-in the `--with-credentials` flag
expresses for a manual export. The master key is never pushed under any
setting.

The push credential is resolved from the credential store at push time. It is
never written into the repository's git config, never passed as a command-line
argument, and is scrubbed from any error text before that text is recorded.

### Restore

Restore is always explicit; nothing is ever imported automatically. It fetches
the remote (cloning first if the working tree does not exist yet), optionally
moves to an earlier revision, and then runs the ordinary import — with the
import semantics already specified above, including never deleting anything the
bundle does not contain.

Because a backup mirrors deletions as faithfully as it mirrors additions, the
bundle at the remote's tip cannot return something deleted last week. Restoring
that means naming a revision or a date, which resolves to the last commit at or
before it.

## Scope

Resource `scope` (a list of agent names,
[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)) rides the
resource document through export and import unmodified — it is an ordinary
field, with no dedicated machinery. An imported resource that is out of scope
for every agent on this machine is registered and visible, just not activated.

## Surfaces

| Surface | Operation |
| --- | --- |
| CLI | `coffer sync export <dir> [--with-credentials]` · `coffer sync import <dir>` · `coffer sync key export <file>` / `coffer sync key import <file>` |
| CLI (backup) | `coffer sync remote set <url> [--branch] [--interval] [--with-credentials]` · `coffer sync remote show` · `coffer sync remote clear` · `coffer sync push` · `coffer sync restore [--at <rev\|date>] [--from <url>]` · `coffer sync status` |
| HTTP | `POST /api/v1/sync/export` · `POST /api/v1/sync/import` · `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| HTTP (backup) | `GET\|PUT\|DELETE /api/v1/sync/remote` · `POST /api/v1/sync/push` · `POST /api/v1/sync/restore` · `GET /api/v1/sync/status` |
| UI | Settings → Sync: an export button and an import button, each opening the daemon-hosted native **directory** picker (spec agent-registry FR-042), plus the master-key card — which uses the browser's own download / `<input type="file">`, not a daemon dialog |
| UI (backup) | Settings → Sync: a backup card shaped like the retention-policy card — enable, remote URL, branch, interval, whether credentials ride along, last-run status with its error, and a button to back up now |

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

### Scenario: configure a backup remote

- **Given** a vault with no backup configured,
- **When** the user runs `coffer sync remote set <url> --with-credentials`,
- **Then** the remote, branch, interval and credential opt-in are stored, the
  backup is enabled, the command prints what a push will contain, and
  `coffer sync status` reports the remote with no run yet.

### Scenario: an unchanged vault makes no backup commit

- **Given** a configured backup whose last run is already committed,
- **When** a backup run happens and nothing in the vault has changed,
- **Then** the export is written, no commit is created, the run is recorded as
  successful, and the repository history is unchanged.

### Scenario: a changed vault is committed and pushed

- **Given** a configured backup and a vault with a new knowledge document,
- **When** a backup run happens,
- **Then** the working tree holds the new export, one commit is created naming
  the counts per area, the commit is pushed to the configured branch, and the
  run's status and commit are recorded.

### Scenario: a failed push keeps the commit

- **Given** a configured backup whose remote is unreachable,
- **When** a backup run happens on a changed vault,
- **Then** the commit exists locally, the run is recorded as failed with the
  reason, the worker keeps running, and the next successful run pushes the
  outstanding commit without re-exporting it as a second commit.

### Scenario: restore a resource deleted last week

- **Given** a backup whose history contains a skill that was later deleted
  locally and mirrored as a deletion,
- **When** the user runs `coffer sync restore --at <date before the deletion>`,
- **Then** the working tree moves to the last commit at or before that date,
  the import runs from it, the skill is registered again, and everything the
  vault gained since then is left untouched.

### Scenario: restore onto a machine with no working tree

- **Given** a machine whose vault has no backup working tree,
- **When** the user runs `coffer sync restore --from <url>`,
- **Then** the repository is cloned, the bundle is imported, and resources
  whose credentials cannot be decrypted are reported as `credentials_locked`
  rather than failing the restore.

### Scenario: the push credential never reaches the repository

- **Given** a configured backup with a push credential,
- **When** a backup run pushes,
- **Then** the credential is not present in the repository's git config, not in
  the git process's command-line arguments, and not in any recorded error text
  or audit payload.

### Scenario: credentials ride along only when the remote says so

- **Given** a backup remote configured without the credential opt-in,
- **When** a backup run happens,
- **Then** the pushed bundle has no `credentials/` directory, and turning the
  opt-in on makes the next run include the ciphertext — while the master key is
  absent from the bundle in both cases.

## Out of scope

- **Getting a bundle between machines by hand.** `scp` or a USB drive remains
  the user's business; Coffer transports a bundle only to the one backup remote
  it was configured with.
- **More than one backup remote.** One is enough to survive a dead disk; a
  second is a fan-out problem with no matching failure.
- **Automatic restore.** Coffer never imports from the remote on its own, at
  daemon start or otherwise. A restore overwrites local state and is always a
  human decision.
- **Continuous convergence.** Two machines can drift apart, and Coffer will not
  notice or reconcile that; the fix is a manual re-export
  ([Vault Export and Import](../../docs/decisions/vault-export-import.md)).
- **Merging two divergent vaults.** Import is last-writer-wins per resource,
  not a three-way merge.
- **A hosted sync endpoint.** Would require a constitutional amendment.
