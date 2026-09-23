# Data Model — Skill Manager

Entities, fields, relationships, and SQLite additions for the skill manager.
Depends on the agent kind from spec agent-registry and the kind-agnostic Resource
framework from spec resource-framework.

## Domain entities (`backend/coffer/domain/skill/`)

### `SkillSource` (`domain/skill/source.py`)

Pydantic models recording where a managed skill came from.
`SkillSource = Annotated[LocalImportSource | BuiltinSource, Field(discriminator="type")]`.

#### `LocalImportSource`

| Field           | Type                      | Notes                                                 |
| --------------- | ------------------------- | ----------------------------------------------------- |
| `type`          | `Literal["local_import"]` | source type                                           |
| `original_path` | `str`                     | informational only; not retained as a live dependency |

#### `BuiltinSource`

| Field  | Type                 | Notes |
| ------ | -------------------- | ----- |
| `type` | `Literal["builtin"]` | Coffer's own generated skill (see "Regenerate Coffer's builtin skill from the build"); carries no other field, because its master folder is regenerated from the running build |

The discriminator is also what marks the row as derived output: the skill kind
reads it (`domain/skill/builtin.py` `is_builtin`) to refuse a delete and to
withhold the row from convergence.

### `SkillConfig` (`domain/skill/config.py`)

Pydantic v2 `BaseModel`. It carries no copy of the skill's name: the name comes
from the SKILL.md frontmatter at import and is stored once, as `Resource.name`.
A `skill_md_name` key mirrored it until migration 0098 stripped it — one fact
written twice, with nothing reading the second copy and two places to disagree
once renaming arrived ([Resource Identity Is an Immutable
`uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

| Field                        | Type               | Notes                                               |
| ---------------------------- | ------------------ | --------------------------------------------------- |
| `source`                     | `LocalImportSource \| BuiltinSource` | discriminated on `type`             |
| `skill_md_description`       | `str`              | frontmatter `description`                           |
| `version_hash`               | `str`              | sha256 of SKILL.md content at last sync             |
| `last_synced_from_source_at` | `datetime \| None` | UTC; set on import                                  |

### `SkillFrontmatter` (`domain/skill/frontmatter.py`)

Pydantic v2 model used during validation of an imported folder. Aligns
with the agentskills.io constraints:

| Field           | Type                | Constraint                                                        |
| --------------- | ------------------- | ----------------------------------------------------------------- |
| `name`          | `str`               | required, 1–64 chars, `^[a-z0-9][a-z0-9_-]{0,63}$`                |
| `description`   | `str`               | required, 1–1024 chars                                            |
| `license`       | `str \| None`       | optional; recognized, not interpreted                             |
| `allowed_tools` | `list[str] \| None` | optional (`allowed-tools`); normalized from list or delimited str |

`name` accepts a documented superset of the standard's charset — the standard
allows lowercase letters, digits, and hyphens, and Coffer also tolerates
underscores for backward-compatibility. `license` and `allowed-tools` are
third-party authored, so recognizing them stays additive: a non-string
`license` scalar is coerced to a string and a malformed `allowed-tools` value
is tolerated (treated as absent) rather than failing validation. Every other
unrecognized field is tolerated under `extra='allow'`.

The frontmatter `description` is stored on the skill kind's config as
`SkillConfig.skill_md_description` (see above) — this is the authoritative
copy. The `resources` row has
its own `description` column inherited from the kind-agnostic Resource
framework; on import it is seeded from the frontmatter `description`
for parity with other kinds, but it is not re-synced afterwards
(treat it as a free-form human label after the initial write).

### `BindingState` (`domain/skill/binding.py`)

Plain dataclass; in-memory representation of one row from
`skill_agent_bindings`. The row is internal delivery bookkeeping — it records
that this agent currently holds a delivered copy — not a user-facing axis.

| Field               | Type               | Notes                                                                                                                 |
| ------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `skill_resource_id` | `int`              | FK                                                                                                                    |
| `agent_resource_id` | `int`              | FK                                                                                                                    |
| `enabled`           | `bool`             | still present in the table and in this dataclass; internal only — it marks a live delivered copy and no surface exposes it |
| `last_linked_at`    | `datetime \| None` | last successful link op                                                                                               |
| `last_link_path`    | `str \| None`      | absolute path where the link was created                                                                              |
| `link_mode`         | `LinkMode \| None` | `symlink`, `junction`, or `copy_fallback`; mirrors `SkillBindingOut.link_mode` and lets the UI flag degraded deliveries |

### `DriftKind` (`domain/skill/drift.py`)

String-valued enum.

| Value                   | Meaning                                       | Suggested remedy                      |
| ----------------------- | --------------------------------------------- | ------------------------------------- |
| `missing_link`          | a delivered copy is recorded but no target on disk | run the opt-in repair to re-link |
| `tampered_link`         | symlink target is not Coffer's master         | run the opt-in repair (backs up, then re-links) |
| `replaced_with_regular` | path is a regular file/dir instead of a link  | manual: move the foreign file/dir away; the next reconcile or repair re-links (repair never touches it) |
| `missing_master`        | binding refers to a master folder that's gone | re-import                             |
| `orphan_master`         | master folder on disk has no DB record        | adopt or remove                       |

### Unmanaged Skill (`domain/skill/scan.py` + `domain/agent/scan.py`) — workspace amendment

A derived (never stored) view of a skill-shaped entry found in an agent's skill
locations that Coffer does not manage (see "List unmanaged skills in an agent's
skill locations"). The filesystem is the source of truth; adoption or deletion
are the only mutations.

`scan_locations(agent_type, config_dir)` lives in `domain/agent/scan.py`
(it depends on `AgentType`, which `domain/skill` must not import — Contract
5c) and returns the ordered directories to scan: `<config_dir>/skills` for
both types, plus `~/.agents/skills` for `codex`. The infrastructure layer
(`infrastructure/skill/workspace_scan.py`) walks them into `ScanEntry` values
(name, path, `is_dir`, `link_target`), and the pure `classify` in
`domain/skill/scan.py` turns those into `UnmanagedSkill` results:

- entries that are Coffer-managed links (symlink resolving inside
  `~/.coffer/skills/`) are excluded;
- dot-entries (e.g. Codex's `.system`) and plain files are silently excluded;
- symlinks pointing outside the master store are listed with
  `foreign_link=True` and are never adoptable;
- plain directories are listed and adoptable.

Surfaced fields (`UnmanagedView` in `application/skill/unmanaged_ops.py`):

| Field          | Type          | Notes                                                                     |
| -------------- | ------------- | ------------------------------------------------------------------------- |
| `name`         | `str`         | folder name                                                               |
| `path`         | `str`         | absolute path on disk                                                     |
| `location`     | `str`         | `"skills"` (`<config_dir>/skills`) or `"agents_dir"` (`~/.agents/skills`) |
| `valid`        | `bool`        | passes AgentSkills validation (see "Validate imported skill folders against AgentSkills") |
| `reason`       | `str \| None` | validation failure reason when invalid                                    |
| `foreign_link` | `bool`        | symlink targeting outside the master store — surfaced, never adoptable    |

### Delivery predicate (owned entirely by the skill resource) — workspace amendment

Delivery has exactly one input pair, both on the `skill` resource itself: the
framework-level `enabled` flag and the framework-level `scope`
([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)).
`scope` is one allow-list of agents, `null` meaning unrestricted, so the answer
depends on the agent asking and on nothing else:

```
delivered(skill, agent)  ⟺  skill.enabled
                         AND is_active(skill.scope, agent)
```

`is_active` is the free function in `domain/scope.py`. There is no evaluator
object to construct at the composition root and no machine id to bind into one;
the delivery call sites call the predicate directly. The pair it reads is the
skill's reach, and reach never leaves this machine (spec vault-sync
"Keep reach machine-local") — so a skill dormant here and delivered on the laptop
is two rows with two answers, not one scope with two axes.

The agent resource carries **no** skill-delivery policy: `follow_all_skills`
and `skill_exclusions` are gone from `AgentConfig` (spec agent-registry's schema), and
migration `0058` strips both keys from every stored agent row. There is no
load-time shim and no back-compat default — a stored row simply no longer has
them.

`application/skill/delivery_ops.py` holds the reconciler,
`apply_scope_for_agent(agent_uid)`. A scope's `agents` list holds agent uids
([ADR resource-identity-is-an-immutable-uid](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)),
so the reconciler computes

```
wanted = {s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}
```

then delivers `wanted - bound` and reclaims `bound - wanted`, where `bound` is
the set of skills whose `skill_agent_bindings` row says this agent currently
holds a delivered copy. It runs on: a skill being enabled or disabled, a
skill's scope being edited, a skill being imported, a skill being removed, an
agent being registered, an agent's `config_dir` changing, and the sync
post-import hook. The skill/agent enable and scope edits reach it through the
kind hooks `on_enabled_changed` and `on_scope_changed`, so skill code still
never imports agent-kind code (Contract 5c).

**Wire shapes.** `SkillOut` gains `scope` (`ScopeOut | None`, always emitted,
placed right after `enabled`) — the allow-list `{agents}` this skill is
delivered under, `null` on the whole field meaning every agent, and `[]`
meaning no agent matches. `SkillBindingOut` carries no `enabled`: it carries
`agent_uid`, `agent_name`, `last_linked_at`, `last_link_path`, and `link_mode`,
and a row present at all means "this agent currently holds a delivered copy". The per-`(skill, agent)`
`POST /skills/{name}/enable` and `/disable` routes (and their
`SkillEnableRequest` / `SkillDisableRequest` bodies) are removed.

## SQLite schema additions

Migration `20260526_0005_skill_tables.py` (revision `0005`, down_revision `0004`) adds the skill binding table. Agents themselves live in the shared `resources` tables, so spec agent-registry needs no dedicated agent-tables migration.

### `skill_agent_bindings`

| Column              | Type                                     | Constraints                                                            |
| ------------------- | ---------------------------------------- | ---------------------------------------------------------------------- |
| `skill_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                                 |
| `agent_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                                 |
| `enabled`           | `bool`                                   | not null, default `0`; internal bookkeeping — `1` means this agent currently holds a delivered copy |
| `last_linked_at`    | `timestamp`                              | nullable                                                               |
| `last_link_path`    | `text`                                   | nullable                                                               |
| `link_mode`         | `text`                                   | nullable; one of `symlink`, `junction`, `copy_fallback` when populated |
| primary key         | `(skill_resource_id, agent_resource_id)` |                                                                        |

Index: `idx_bindings_agent` on `(agent_resource_id, enabled)` — supports "which skills does this agent currently hold" queries.

### Reuse of existing tables

- `resources`: new rows with `kind='skill'`. No schema change.
- `audit_log`: new event types written (see below).

## Audit event types added

Add to `AuditEventType`:

| Value                  | When emitted                                                               |
| ---------------------- | -------------------------------------------------------------------------- |
| `skill_imported`       | Local-path import succeeds                                                 |
| `skill_updated`        | An overwrite re-import replaced the skill (details: the new `version_hash`), or an in-app file save changed one file (details: `path`, `edited_file: true`) |
| `skill_bound`          | A copy was delivered to an agent (symlink created)                         |
| `skill_unbound`        | A delivered copy was reclaimed from an agent (symlink removed)             |

The workspace amendment adds:

| Value                     | When emitted                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `skill_adopted`           | An unmanaged skill folder was adopted into the master store (see "Adopt an unmanaged skill")                                       |
| `skill_unmanaged_deleted` | An unmanaged skill folder was deleted from an agent's workspace (see "Delete an unmanaged skill on explicit request")                                   |
| `skill_relinked`          | A delivered copy's managed link was re-created at a new delivery path (e.g. after a `config_dir` change) |
| `skill_drift_remediated`  | A drift entry was re-delivered from master by repair — on demand or by the boot heal (see "Repair repairable drift from master"); details `{agent, kind}` |

Skill **removal** has no dedicated event — deleting a skill goes through
`ResourceService.delete`, which emits the generic `resource_deleted` event
(with a pre-delete snapshot in `details`), the same as any other resource kind.

## On-disk layout

```
~/.coffer/
  skills/
    <skill-name>/           # canonical master, one per skill
      SKILL.md
      scripts/ ...           # optional
      references/ ...        # optional
      assets/ ...            # optional
      .coffer.meta.json      # source provenance redundancy; not authoritative
```

`.coffer.meta.json` records provenance for forensic recovery if the DB is lost.
`MasterStore` writes it whenever the master folder is (re)created — `copy_in` /
`atomic_replace` on import, overwrite re-import and the builtin seed. A rename
or an in-app file edit never rewrites it.
It is **not** read by Coffer at runtime; the DB is authoritative and wins on
any disagreement.

Keys persisted:

| Key                          | Source                                   | Notes                                        |
| ---------------------------- | ---------------------------------------- | -------------------------------------------- |
| `source`                     | `SkillConfig.source`                     | the source model (`local_import` with `original_path`, or `builtin`) |
| `name`                       | `Resource.name`                          | the master folder's name at write time       |
| `imported_at`                | import timestamp                         | ISO-8601 UTC; imported skills only           |
| `version_hash`               | `SkillConfig.version_hash`               | sha256 of SKILL.md at import; imported skills only |

The builtin seed writes only `name` and `source`.

Per-agent symlink targets land at:

```
<config_dir>/skills/<skill-name>  → symlink/junction to  ~/.coffer/skills/<skill-name>
```

### Per-agent delivery targets

Skill delivery has exactly one model: Coffer symlinks (copy fallback) the master
skill folder into the agent's skills directory. Each agent declares _where_ that
directory is via the capability manifest (`domain/agent/descriptor.py`) — a
`skill_subpath` under the agent's config dir. The skill service resolves the
target dir through a composition-root resolver (Contract 5: the service never
imports the descriptor).

| Agent       | Folder target                | Status    |
| ----------- | ---------------------------- | --------- |
| Claude Code | `<config_dir>/skills/<name>` | Delivered |
| Codex       | `<config_dir>/skills/<name>` | Delivered |

The link points at the master folder, so the agent reads the canonical
`SKILL.md` at `<config_dir>/skills/<name>/SKILL.md`.

## Application service contracts (`backend/coffer/application/skill/`)

### `SkillService`

Keyword-only arguments; skills and agents are addressed by uid.

| Method | Purpose |
| ------ | ------- |
| `import_local(*, path, actor, overwrite=False) -> Resource` | Validate the folder (`SkillValidationError` → 422 `SKILL_INVALID`), copy to master, register the Resource (or, with `overwrite`, replace the master folder and update the same row, keeping its uid and deliveries), audit, then reconcile a new skill so it lands wherever its scope grants it. |
| `enable_for(*, skill_uid, agent_uid, force=False, actor) -> BindingState` | INTERNAL delivery primitive driven by `apply_scope_for_agent` and repair: upsert the delivery row, create the symlink (or copy fallback). |
| `disable_for(*, skill_uid, agent_uid, actor) -> BindingState` | INTERNAL reclaim primitive driven by `apply_scope_for_agent`: remove the link, clear the delivery row. |
| `apply_scope_for_agent(agent_uid, *, actor) -> list[str]` | Reconcile one agent against the delivery predicate (see "Delivery predicate" above). |
| `verify() -> DriftReport` | Walk every delivered copy; classify drift per `DriftKind`. |
| `repair_drift(*, actor) -> RepairResult` | Re-deliver the repairable drift (`missing_link`, `tampered_link`) from master, auditing each as `skill_drift_remediated`; returns what was remediated and the residual report. Backs `verify --fix`, `POST /skills/repair` and the boot heal. |
| `remove(*, uid, actor) -> None` | Delegate to `ResourceService.delete`; the teardown runs in the skill kind's `on_delete`. |
| `cleanup_bindings_for_skill(skill) -> None` | The skill kind's `on_delete` hook: remove every binding and link, then delete the master folder. |
| `move_master_folder(skill, new_name) -> None` | The skill kind's rename hook: move the master folder and re-point every delivered link before the row is renamed. |
| `cleanup_bindings_for_agent(agent: Resource) -> None` | Called by spec agent-registry's `agent.on_delete` hook; removes all bindings + symlinks for that agent. |
| `relink_for_agent(agent_uid, *, actor) -> None` | The agent's config-dir-changed hook: re-create the agent's delivered links under its new `<config_dir>/skills`. |

Workspace-amendment additions (implemented as free functions in
`unmanaged_ops.py` / `delivery_ops.py`, with `binding_ops.py` split out of
`service.py` for the deliver/reclaim primitives — all conceptually private
to the skill subpackage, same style as `lifecycle_ops.py`):

| Method                                                                 | Purpose                                                                                                                                                                          |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_unmanaged(agent_uid) -> list[UnmanagedView]`                     | Read-only scan ("List unmanaged skills in an agent's skill locations") over the agent's skill locations (see Unmanaged Skill above).                                                                                              |
| `adopt_unmanaged(agent_uid, skill_name, location, actor) -> Resource`  | "Adopt an unmanaged skill": validate → move to `~/.coffer/skills/<name>/` → register → deliver the managed link to `<config_dir>/skills/<name>` → record an enabled binding; audits `skill_adopted`. |
| `delete_unmanaged(agent_uid, skill_name, location, actor) -> None`     | "Delete an unmanaged skill on explicit request": delete only that folder from disk; audits `skill_unmanaged_deleted`.                                                                                                     |
| delivery reconciliation (`delivery_ops.py`)                            | "Reconcile deliveries per agent on every trigger": `apply_scope_for_agent` — recompute the agent's wanted set from `skill.enabled AND is_active(skill.scope, agent)`, deliver what is missing, reclaim what is no longer wanted.                                 |

### File viewer (`application/skill/file_ops.py`)

Stateless helpers beside `service.py` (same pattern as
`verify_ops.py`) that expose a skill's master folder to
surfaces. The **read** helpers (`build_file_tree`, `read_skill_file`) back the
in-app viewer and surface each node's absolute on-disk path so the UI can offer
open-in-external-editor / reveal-in-file-manager affordances (spec.md
`## Purpose`). A
**write** helper (`write_skill_file`) is the only mutation here, and it serves
the in-app editor and programmatic clients alike ("Save an existing skill file conditionally") — one
endpoint, one code path. The conditional half of that write (comparing the
caller's `expected_fingerprint` against the bytes on disk and raising for a 409)
lives one layer up in `content_ops.py`, so the containment helpers stay free of
request semantics.
No DB; a write is audited as `skill_updated` by `content_ops.py`, reads audit
nothing. Containment is enforced by resolving every candidate path and
requiring it to stay inside the resolved master folder, reusing the path-escape
approach from `domain/skill/validator.py`.

| Function                                                           | Purpose                                                                                                                                                                                                                                            |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_file_tree(master_folder) -> FileNode`                       | Recursively list the master folder; skip symlinks whose real target escapes the folder; never descend symlinked dirs. Each node carries its absolute on-disk path.                                                                                 |
| `read_skill_file(master_folder, relpath) -> FileContent`           | Resolve `master_folder/relpath`, verify it stays inside the folder (else `ValueError`), read with a size cap, detect binary; returns the file's absolute path and containing folder's absolute path.                                               |
| `write_skill_file(master_folder, relpath, content) -> FileContent` | Overwrite ("Save an existing skill file conditionally") of an existing text file under the same containment guard and size cap; refuses to create new files/dirs, write outside the folder, or overwrite a binary file; atomic. Returns the NEW fingerprint, so an editor holding the buffer open can save again without a re-read. |

#### File-node shape (`FileNode` / `SkillFileNodeOut`)

One node in the recursive tree. The root node has `path == ""`.

| Field      | Type              | Notes                                                                      |
| ---------- | ----------------- | -------------------------------------------------------------------------- |
| `name`     | `str`             | entry's base name                                                          |
| `path`     | `str`             | POSIX path relative to the master folder root (`""` for the root)          |
| `abs_path` | `str`             | absolute on-disk path (for open-in-editor / reveal); surface-only (`SkillFileNodeOut`) |
| `folder_abs_path` | `str`      | absolute path of the entry's containing folder; surface-only (`SkillFileNodeOut`) |
| `type`     | `"file" \| "dir"` | node kind                                                                  |
| `size`     | `int \| None`     | byte size for files; `null` for directories                                |
| `truncated` | `bool`           | true on a directory whose descendants were clipped at the walk depth cap (`MAX_TREE_DEPTH` = 64) |
| `children` | `list[FileNode]`  | populated for directories (sorted dirs-first then by name); `[]` for files |

#### File-content shape (`FileContent` / `SkillFileContentOut`)

A single file's contents — what the in-app viewer renders and edits, and what
the write returns (see "Save an existing skill file conditionally").

| Field             | Type   | Notes                                                                            |
| ----------------- | ------ | -------------------------------------------------------------------------------- |
| `path`            | `str`  | POSIX path relative to the master folder root                                    |
| `abs_path`        | `str`  | absolute on-disk path of the file                                                |
| `folder_abs_path` | `str`  | absolute on-disk path of the file's containing folder                            |
| `content`         | `str`  | file text; empty (`""`) when `binary` is true                                    |
| `truncated`       | `bool` | true when the file exceeded the 256 KiB read cap and only the prefix is returned |
| `binary`          | `bool` | true when the file is non-UTF-8 or contains a NUL byte (content is empty)        |
| `size`            | `int`  | true byte size of the file on disk (independent of any truncation)               |
| `fingerprint`     | `str`  | digest of the file's RAW BYTES on disk — never of the returned `content`, so an oversized or binary file's fingerprint still round-trips and an edit past the truncation point is still detected. A write carries it back to be conditional (409 on mismatch); omitting it stays last-writer-wins |

### `SyncEngine` (`infrastructure/skill/sync_engine.py`)

Cross-platform directory-link helper. Lives in `infrastructure/` because its
implementation talks directly to the host filesystem (and on Windows, to
`cmd.exe /c mklink`); the application layer accesses it through a port
defined in `application/skill/ports.py`.

| Method                                                               | Purpose                                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make_directory_link(target: Path, link: Path) -> LinkMode`          | POSIX: `os.symlink(target, link, target_is_directory=True)`. Windows: try `os.symlink` first; on `OSError(WinError 1314)` fall back to `subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)])` (junction). Returns `LinkMode.SYMLINK \| LinkMode.JUNCTION \| LinkMode.COPY_FALLBACK`. |
| `remove_directory_link(link: Path) -> None`                          | Detect type then remove correctly (junction vs symlink vs copy-tree).                                                                                                                                                                                                                                 |
| `classify_target(link: Path, expected_master: Path) -> TargetStatus` | Returns the right `DriftKind` (or `OK`).                                                                                                                                                                                                                                                              |

### `validate_skill_folder` (`domain/skill/validator.py`)

Pure function `validate_skill_folder(folder, *, size_limit_bytes=50 MiB)`:
returns `ValidationOk(frontmatter, total_size_bytes, skill_md_sha256)` or
`ValidationFailure(reason, details)`. Checks: the folder exists and is a
directory, `SKILL.md` exists, its frontmatter is present and parses as
`SkillFrontmatter`, no path-escape symlinks within the folder, total size
within the limit. Reason codes: `folder_missing`, `not_a_directory`,
`skill_md_missing`, `skill_md_frontmatter_missing`,
`skill_md_frontmatter_invalid`, `path_escape_symlinks`, `size_limit_exceeded`
(details `{total_bytes, limit_bytes}`). A failure becomes
`SkillValidationError` (422 `SKILL_INVALID`, `details.reason` naming the
reason).

## Composition root wiring

`surfaces/http/kind_wiring.py` calls
`wire_agent_and_skill_kinds(app, resource_svc, audit, sm, builtin_tools, credential_store, sync)`
from `surfaces/http/agent_skill_wiring.py`, which wires the agent and skill kinds
in lockstep and returns an `AgentSkillWiring`. The wiring function:

1. Builds `SkillBindingRepo`, `MasterStore`, `SyncEngine`, and the `SkillService`,
   plus the agent services, handing `AgentService` the skill side's
   `relink_for_agent` as its config-dir-changed hook.
2. Builds the agent `Kind` fresh via `make_agent_kind(on_delete=...)`, whose
   `on_delete` awaits `skill_svc.cleanup_bindings_for_agent(agent)` before the
   agent row is removed.
3. Builds the skill `Kind` via `make_skill_kind(cleanup_bindings_for_skill,
   move_master_folder, on_scope_changed=..., on_enabled_changed=...)`, the two
   hooks re-running delivery for every registered agent.
4. Registers both into `app.state.kinds["agent"]` / `app.state.kinds["skill"]`.
5. Returns `AgentSkillWiring` — the agent and skill services, the
   `boot_heal` and `builtin_seed` the lifespan runs once every kind is wired,
   and the transcript reader. Routers are mounted elsewhere (`surfaces/http/routing.py`).

Passing the hooks as callables keeps both kinds independent at the application
layer (neither imports the other) and centralises cross-kind glue at the
composition root.

## Constraints summary

- All HTTP loopback-only.
- File-size limit: 50 MB total per skill folder, enforced by `validate_skill_folder`. The limit is a `SkillService` constructor default (`size_limit_bytes`) that the composition root does not override, and no setting adjusts it.
