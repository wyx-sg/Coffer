# Data Model — 005 Skill Manager

Entities, fields, relationships, and SQLite additions for the skill manager.
Depends on the agent kind from spec 004 and the kind-agnostic Resource
framework from spec 001.

## Domain entities (`backend/coffer/domain/skill/`)

### `SkillSource` (`domain/skill/source.py`)

A Pydantic model recording where a managed skill came from. In v1, only local-folder import is supported.

#### `LocalImportSource`

| Field           | Type                      | Notes                                                 |
| --------------- | ------------------------- | ----------------------------------------------------- |
| `type`          | `Literal["local_import"]` | source type                                           |
| `original_path` | `str`                     | informational only; not retained as a live dependency |

### `SkillConfig` (`domain/skill/config.py`)

Pydantic v2 `BaseModel`.

| Field                        | Type               | Notes                                               |
| ---------------------------- | ------------------ | --------------------------------------------------- |
| `source`                     | `LocalImportSource` | single local_import source                         |
| `skill_md_name`              | `str`              | SKILL.md frontmatter `name`; equals `Resource.name` |
| `skill_md_description`       | `str`              | frontmatter `description`                           |
| `version_hash`               | `str`              | sha256 of SKILL.md content at last sync             |
| `last_synced_from_source_at` | `datetime \| None` | UTC; set on import                                  |
| `scan_verdict`               | `str \| None`      | trust layer L2 (FR-028): worst severity, or none    |
| `scan_findings_count`        | `int`              | number of scan findings (default 0)                 |
| `scan_ruleset_version`       | `str \| None`      | ruleset version the verdict was produced under      |
| `last_scanned_at`            | `datetime \| None` | UTC; set on each scan                               |
| `risk_acknowledged`          | `bool`             | FR-029; set by acknowledge, reset on content change |

The trust-layer fields are all optional with defaults, so they serialize into
the existing opaque `config_json` with no migration and pre-trust-layer rows
still validate.

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

Plain dataclass; in-memory representation of one row from `skill_agent_bindings`.

| Field               | Type               | Notes                                                                                                                 |
| ------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `skill_resource_id` | `int`              | FK                                                                                                                    |
| `agent_resource_id` | `int`              | FK                                                                                                                    |
| `enabled`           | `bool`             |                                                                                                                       |
| `last_linked_at`    | `datetime \| None` | last successful link op                                                                                               |
| `last_link_path`    | `str \| None`      | absolute path where the link was created                                                                              |
| `link_mode`         | `LinkMode \| None` | `symlink`, `junction`, or `copy_fallback`; mirrors `SkillBindingOut.link_mode` and lets the UI flag degraded bindings |

### `DriftKind` (`domain/skill/drift.py`)

String-valued enum.

| Value                   | Meaning                                       | Suggested remedy                      |
| ----------------------- | --------------------------------------------- | ------------------------------------- |
| `missing_link`          | binding enabled but no target on disk         | re-enable to re-link                  |
| `tampered_link`         | symlink target is not Coffer's master         | disable + re-enable, or use `--force` |
| `replaced_with_regular` | path is a regular file/dir instead of a link  | same as above                         |
| `missing_master`        | binding refers to a master folder that's gone | re-import                             |
| `orphan_master`         | master folder on disk has no DB record        | adopt or remove                       |

### Unmanaged Skill (`domain/skill/scan.py` + `domain/agent/scan.py`) — workspace amendment

A derived (never stored) view of a skill-shaped entry found in an agent's
skill locations that Coffer does not manage (FR-022). The filesystem is the
source of truth; adoption or deletion are the only mutations.

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
| `valid`        | `bool`        | passes AgentSkills validation (FR-004)                                    |
| `reason`       | `str \| None` | validation failure reason when invalid                                    |
| `foreign_link` | `bool`        | symlink targeting outside the master store — surfaced, never adoptable    |

### Follow Policy (stored on the agent resource's config, spec 004) — workspace amendment

Per-agent skill-delivery policy (FR-025): `follow_all_skills: bool` (default
`True`, preserving the pre-amendment trust mode) plus `skill_exclusions:
list[str]`. The fields live on `AgentConfig` (spec 004's schema, updatable via
`PATCH /agents/{name}` / `coffer agent follow`); this spec owns their delivery
semantics. While following, the agent's effective skill set is the entire
master store minus its exclusions; bindings remain the persistent delivery
record. `application/skill/follow_ops.py` reconciles deliveries when the flag
flips, when a skill is registered or removed, and when the exclusion list
changes; disabling the flag preserves the currently delivered skills as
explicit per-skill bindings. The policy is read through an injected
`agent_skill_policy_resolver` so skill code never imports agent-kind code
(Contract 5c).

## SQLite schema additions

Migration `20260526_0005_skill_tables.py` (revision `0005`, down_revision `0004`) adds the skill binding table. Agents themselves live in the shared `resources` tables, so spec 004 needs no dedicated agent-tables migration.

### `skill_agent_bindings`

| Column              | Type                                     | Constraints                                                            |
| ------------------- | ---------------------------------------- | ---------------------------------------------------------------------- |
| `skill_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                                 |
| `agent_resource_id` | `int`                                    | FK → `resources(id)` ON DELETE CASCADE                                 |
| `enabled`           | `bool`                                   | not null, default `0`                                                  |
| `last_linked_at`    | `timestamp`                              | nullable                                                               |
| `last_link_path`    | `text`                                   | nullable                                                               |
| `link_mode`         | `text`                                   | nullable; one of `symlink`, `junction`, `copy_fallback` when populated |
| primary key         | `(skill_resource_id, agent_resource_id)` |                                                                        |

Index: `idx_bindings_agent` on `(agent_resource_id, enabled)` — supports "which skills are enabled for this agent" queries.

### Reuse of existing tables

- `resources`: new rows with `kind='skill'`. No schema change.
- `audit_log`: new event types written (see below).

## Audit event types added

Add to `AuditEventType`:

| Value                  | When emitted                                                               |
| ---------------------- | -------------------------------------------------------------------------- |
| `skill_imported`       | Local-path import succeeds                                                 |
| `skill_updated`        | In-place file edit changes skill content (with before/after hashes)        |
| `skill_bound`          | Per-agent binding enabled (symlink created)                                |
| `skill_unbound`        | Per-agent binding disabled (symlink removed)                               |
| `skill_drift_detected` | `verify` op reported drift (count + categories in details)                 |

The workspace amendment adds:

| Value                     | When emitted                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `skill_adopted`           | An unmanaged skill folder was adopted into the master store (FR-023)                                       |
| `skill_unmanaged_deleted` | An unmanaged skill folder was deleted from an agent's workspace (FR-024)                                   |
| `skill_autobind_skipped`  | Auto-bind / follow reconciliation skipped an agent (e.g. target conflict; best-effort)                     |
| `skill_relinked`          | An enabled binding's managed link was re-created at a new delivery path (e.g. after a `config_dir` change) |

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

`.coffer.meta.json` mirrors a subset of `SkillConfig` for forensic recovery
if the DB is lost. The file is written by `MasterStore` immediately after the
master folder content is copied (i.e. at the end of import) and is rewritten
in place on every subsequent successful sync.
It is **not** read by Coffer at runtime; the DB is authoritative and wins on
any disagreement.

Keys persisted:

| Key                          | Source                                   | Notes                                        |
| ---------------------------- | ---------------------------------------- | -------------------------------------------- |
| `source`                     | `SkillConfig.source`                     | local_import source with original_path       |
| `skill_md_name`              | `SkillConfig.skill_md_name`              | matches the master folder name at write time |
| `skill_md_description`       | `SkillConfig.skill_md_description`       |                                              |
| `version_hash`               | `SkillConfig.version_hash`               | sha256 of SKILL.md at last sync              |
| `last_synced_from_source_at` | `SkillConfig.last_synced_from_source_at` | ISO-8601 UTC                                 |

Per-agent symlink targets land at:

```
<config_dir>/skills/<skill-name>  → symlink/junction to  ~/.coffer/skills/<skill-name>
```

### Per-agent delivery targets

Each agent declares _how_ and _where_ Coffer delivers a skill via the capability
manifest (`domain/agent/descriptor.py`): a `skill_delivery_mode`
(`SkillDeliveryMode` — `folder` / `rules_mdc` / `external_dir`) plus, for the
folder model, a `skill_subpath` under the agent's config dir. The skill service
reads the mode through a composition-root resolver that returns a plain string
(Contract 5: the service never imports the descriptor).

| Agent       | Delivery mode  | Folder target                           | Status                                          |
| ----------- | -------------- | --------------------------------------- | ----------------------------------------------- |
| Claude Code | `folder`       | `<config_dir>/skills/<name>`            | Delivered                                       |
| Codex       | `folder`       | `<config_dir>/skills/<name>`            | Delivered                                       |
| OpenCode    | `folder`       | `<config_dir>/skills/<name>`            | Delivered                                       |
| OpenClaw    | `folder`       | `<config_dir>/workspace/skills/<name>`  | Delivered                                       |
| Hermes      | `external_dir` | `~/.coffer/agent-skills/<agent>/<name>` | Delivered (folder + `config.yaml` registration) |
| Cursor      | `rules_mdc`    | —                                       | Recognized extension point (deferred)           |

Folder delivery symlinks (copy-fallback) the master folder into the target, so
the agent reads the canonical `SKILL.md` (e.g. OpenClaw sees
`workspace/skills/<name>/SKILL.md`).

**`external_dir` (Hermes).** Hermes scans directories listed under
`skills.external_dirs` in `~/.hermes/config.yaml`. Coffer folder-delivers each
enabled skill into a Coffer-owned, agent-named directory and registers that
directory in the config file (round-trip YAML, idempotent, de-duplicated by
resolved path). The registration is pruned when the agent's last delivered
skill is removed and when the agent is deleted. Because this is folder-style
delivery, it reuses the symlink/copy primitive and flows through the same
enable/disable/verify/relink/follow lifecycle as `folder` agents — only the
target dir (resolved by the composition root) and the config registration
differ.

**`rules_mdc` (Cursor) — deferred.** Cursor's `.mdc` rules are project-scoped
(`<project>/.cursor/rules/`); there is no officially-supported global/agent-level
`.mdc` location to deliver an agent-wide skill into (global User Rules live in
Cursor's internal settings, not files). Delivering an agent-level skill as an
`.mdc` would therefore have no reliable target, so it stays a recognized
extension point. Enabling a skill for a `rules_mdc` agent raises
`SkillDeliveryUnsupported` (HTTP 422) before any filesystem write; the follow /
relink reconcilers skip it so registration, config-dir-change, and policy-change
flows never fail.

## Application service contracts (`backend/coffer/application/skill/`)

### `SkillService`

| Method                                                         | Purpose                                                                                                                        |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `import_local(path, actor) -> Resource`                        | Read SKILL.md, validate, copy to master, register Resource, audit, return. Auto-binds for every registered agent (trust mode). |
| `enable_for(skill_ref, agent_ref, force=False, actor) -> None` | Upsert binding, create symlink (or copy fallback on FAT32).                                                                    |
| `disable_for(skill_ref, agent_ref, actor) -> None`             | Mark binding disabled, remove link.                                                                                            |
| `verify() -> DriftReport`                                      | Walk every enabled binding; classify drift per `DriftKind`.                                                                    |
| `remove(ref, actor) -> None`                                   | Cascade-cleanup symlinks, delete master, delegate to `ResourceService.delete`.                                                 |
| `cleanup_bindings_for_agent(agent_ref) -> None`                | Called by spec 004's `agent.on_delete` hook; removes all bindings + symlinks for that agent.                                   |

Workspace-amendment additions (implemented as free functions in
`unmanaged_ops.py` / `follow_ops.py`, with `binding_ops.py` split out of
`service.py` for the per-agent enable/disable flow — all conceptually private
to the skill subpackage, same style as `lifecycle_ops.py`):

| Method                                                                 | Purpose                                                                                                                                                                          |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_unmanaged(agent_name) -> list[UnmanagedView]`                    | FR-022 read-only scan over the agent's skill locations (see Unmanaged Skill above).                                                                                              |
| `adopt_unmanaged(agent_name, skill_name, location, actor) -> Resource` | FR-023: validate → move to `~/.coffer/skills/<name>/` → register → deliver the managed link to `<config_dir>/skills/<name>` → record an enabled binding; audits `skill_adopted`. |
| `delete_unmanaged(agent_name, skill_name, location, actor) -> None`    | FR-024: delete only that folder from disk; audits `skill_unmanaged_deleted`.                                                                                                     |
| follow reconciliation (`follow_ops.py`)                                | FR-025: reconcile deliveries on flag/exclusion changes and on skill register/remove; disabling preserves delivered skills as explicit bindings.                                  |

### File viewer (`application/skill/file_ops.py`)

Stateless helpers beside `service.py` (same pattern as
`verify_ops.py`) that expose a skill's master folder to
surfaces. The **read** helpers (`build_file_tree`, `read_skill_file`) back the
read-only in-app viewer and surface each node's absolute on-disk path so the UI
can offer open-in-external-editor / reveal-in-file-manager / copy-path
affordances (FR-027); the UI viewer never edits content. A separate **write**
helper (`write_skill_file`) backs the programmatic REST/CLI overwrite (FR-028)
and is the only mutation here — the in-app UI does not call it to edit content.
No DB, no audit; containment is enforced by resolving every candidate path and
requiring it to stay inside the resolved master folder, reusing the path-escape
approach from `domain/skill/validator.py`.

| Function                                                           | Purpose                                                                                                                                                                                                                                            |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_file_tree(master_folder) -> FileNode`                       | Recursively list the master folder; skip symlinks whose real target escapes the folder; never descend symlinked dirs. Each node carries its absolute on-disk path.                                                                                 |
| `read_skill_file(master_folder, relpath) -> FileContent`           | Resolve `master_folder/relpath`, verify it stays inside the folder (else `ValueError`), read with a size cap, detect binary; returns the file's absolute path and containing folder's absolute path.                                               |
| `write_skill_file(master_folder, relpath, content) -> FileContent` | FR-028 programmatic (REST/CLI) overwrite of an existing text file under the same containment guard and size cap; refuses to create new files/dirs, write outside the folder, or overwrite a binary file; atomic. Not used by the in-app UI viewer. |

#### File-node shape (`FileNode` / `SkillFileNodeOut`)

One node in the recursive tree. The root node has `path == ""`.

| Field      | Type              | Notes                                                                      |
| ---------- | ----------------- | -------------------------------------------------------------------------- |
| `name`     | `str`             | entry's base name                                                          |
| `path`     | `str`             | POSIX path relative to the master folder root (`""` for the root)          |
| `abs_path` | `str`             | absolute on-disk path (for open-in-editor / reveal / copy-path, FR-027)    |
| `type`     | `"file" \| "dir"` | node kind                                                                  |
| `size`     | `int \| None`     | byte size for files; `null` for directories                                |
| `children` | `list[FileNode]`  | populated for directories (sorted dirs-first then by name); `[]` for files |

#### File-content shape (`FileContent` / `SkillFileContentOut`)

A single file's contents. The in-app viewer renders these read-only; the same
shape is returned by the programmatic write (FR-028).

| Field             | Type   | Notes                                                                            |
| ----------------- | ------ | -------------------------------------------------------------------------------- |
| `path`            | `str`  | POSIX path relative to the master folder root                                    |
| `abs_path`        | `str`  | absolute on-disk path of the file (FR-027)                                       |
| `folder_abs_path` | `str`  | absolute on-disk path of the file's containing folder (FR-027)                   |
| `content`         | `str`  | file text; empty (`""`) when `binary` is true                                    |
| `truncated`       | `bool` | true when the file exceeded the 256 KiB read cap and only the prefix is returned |
| `binary`          | `bool` | true when the file is non-UTF-8 or contains a NUL byte (content is empty)        |
| `size`            | `int`  | true byte size of the file on disk (independent of any truncation)               |

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

### `AgentSkillsValidator` (`domain/skill/validator.py`)

Pure validator: given a folder path, returns `ValidationOk(name, description)` or
`ValidationError(reason, details)`. Checks: `SKILL.md` exists, frontmatter parses,
`name` and `description` non-empty, no path-escape symlinks within the folder,
total size ≤ 50 MB.

## Composition root wiring

`surfaces/http/app.py` calls `wire_agent_and_skill_kinds(app, resource_svc, audit, sm)` from `surfaces/http/agent_skill_wiring.py`. The wiring function:

1. Builds `SkillBindingRepo`, `MasterStore`, `SyncEngine`, and the `SkillService` (plus its `verify_ops` collaborator).
2. Constructs the skill `Kind` via `make_skill_kind(...)` and registers it into `app.state.kinds["skill"]`.
3. Reads the existing agent `Kind` already registered by `_wire_agent_kind` and builds a new `Kind` whose `on_delete` is a closure: first `await skill_svc.cleanup_bindings_for_agent(ref)`, then delegate to the original agent `on_delete`. The wrapped agent kind replaces the previous entry in `app.state.kinds["agent"]`.
4. Mounts the `skill_routes` router.

This closure-based composition keeps both kinds independent at the application layer (neither imports the other) and centralises cross-kind glue at the composition root.

## Constraints summary

- All HTTP loopback-only.
- File-size limit: 50 MB total per skill folder, enforced by `validate_skill_folder`. The limit is a `SkillService` constructor default (`size_limit_bytes`); it is not yet plumbed to a config file, so v1 always uses the hardcoded 50 MB.
