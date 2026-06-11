# Data Model — 005 Skill Manager

Entities, fields, relationships, and SQLite additions for the skill manager.
Depends on the agent kind from spec 004 and the kind-agnostic Resource
framework from spec 001.

## Domain entities (`backend/coffer/domain/skill/`)

### `SkillSource` (`domain/skill/source.py`)

A discriminated Pydantic union recording where a managed skill came from.

```
SkillSource = Annotated[LocalImportSource | GitSource, Discriminator("type")]
```

#### `LocalImportSource`

| Field           | Type                      | Notes                                                 |
| --------------- | ------------------------- | ----------------------------------------------------- |
| `type`          | `Literal["local_import"]` | discriminator                                         |
| `original_path` | `str`                     | informational only; not retained as a live dependency |

#### `GitSource`

| Field         | Type             | Notes                                                  |
| ------------- | ---------------- | ------------------------------------------------------ |
| `type`        | `Literal["git"]` | discriminator                                          |
| `git_url`     | `HttpUrl`        | must pass SSRF guard (per spec 001 constitution)       |
| `git_ref`     | `str`            | branch / tag / commit ref, e.g. `main`                 |
| `git_subpath` | `str`            | path relative to repo root; `""` if skill sits at root |

### `SkillConfig` (`domain/skill/config.py`)

Pydantic v2 `BaseModel`.

| Field                        | Type               | Notes                                               |
| ---------------------------- | ------------------ | --------------------------------------------------- |
| `source`                     | `SkillSource`      | discriminated union                                 |
| `skill_md_name`              | `str`              | SKILL.md frontmatter `name`; equals `Resource.name` |
| `skill_md_description`       | `str`              | frontmatter `description`                           |
| `version_hash`               | `str`              | sha256 of SKILL.md content at last sync             |
| `last_synced_from_source_at` | `datetime \| None` | UTC; set on import/fetch/update                     |

### `SkillFrontmatter` (`domain/skill/frontmatter.py`)

Pydantic v2 model used during validation of an imported/fetched folder.
Mirrors agentskills.io minimum: `name`, `description`. Extra fields tolerated
under `extra='allow'`.

The frontmatter `description` is stored on the skill kind's config as
`SkillConfig.skill_md_description` (see above) — this is the authoritative
copy and is what frontmatter renames will overwrite. The `resources` row has
its own `description` column inherited from the kind-agnostic Resource
framework; on import/fetch it is seeded from the frontmatter `description`
for parity with other kinds, but it is not re-synced on subsequent updates
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
| `missing_master`        | binding refers to a master folder that's gone | re-import or re-fetch                 |
| `orphan_master`         | master folder on disk has no DB record        | adopt or remove                       |

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

| Value                  | When emitted                                                     |
| ---------------------- | ---------------------------------------------------------------- |
| `skill_imported`       | Local-path import succeeds                                       |
| `skill_fetched`        | Git fetch succeeds                                               |
| `skill_updated`        | Git update changes content (with before/after hashes in details) |
| `skill_update_noop`    | Update found no change                                           |
| `skill_renamed`        | Frontmatter rename applied with `--allow-rename`                 |
| `skill_bound`          | Per-agent binding enabled (symlink created)                      |
| `skill_unbound`        | Per-agent binding disabled (symlink removed)                     |
| `skill_drift_detected` | `verify` op reported drift (count + categories in details)       |

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
master folder content is copied/replaced (i.e. at the end of import, fetch,
and update) and is rewritten in place on every subsequent successful sync.
It is **not** read by Coffer at runtime; the DB is authoritative and wins on
any disagreement.

Keys persisted:

| Key                          | Source                                   | Notes                                        |
| ---------------------------- | ---------------------------------------- | -------------------------------------------- |
| `source`                     | `SkillConfig.source` (discriminated)     | full union including `type` + variant fields |
| `skill_md_name`              | `SkillConfig.skill_md_name`              | matches the master folder name at write time |
| `skill_md_description`       | `SkillConfig.skill_md_description`       |                                              |
| `version_hash`               | `SkillConfig.version_hash`               | sha256 of SKILL.md at last sync              |
| `last_synced_from_source_at` | `SkillConfig.last_synced_from_source_at` | ISO-8601 UTC                                 |

Per-agent symlink targets land at:

```
<config_dir>/skills/<skill-name>  → symlink/junction to  ~/.coffer/skills/<skill-name>
```

## Application service contracts (`backend/coffer/application/skill/`)

### `SkillService`

| Method                                                         | Purpose                                                                                                                        |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `import_local(path, actor) -> Resource`                        | Read SKILL.md, validate, copy to master, register Resource, audit, return. Auto-binds for every registered agent (trust mode). |
| `fetch_git(url, ref, subpath, actor) -> Resource`              | SSRF-guarded shallow clone, validate, copy, register. Auto-bind.                                                               |
| `update(ref, allow_rename=False, actor) -> UpdateOutcome`      | Re-fetch git source, compare hash, replace master atomically if changed; reject on rename unless flagged.                      |
| `enable_for(skill_ref, agent_ref, force=False, actor) -> None` | Upsert binding, create symlink (or copy fallback on FAT32).                                                                    |
| `disable_for(skill_ref, agent_ref, actor) -> None`             | Mark binding disabled, remove link.                                                                                            |
| `verify() -> DriftReport`                                      | Walk every enabled binding; classify drift per `DriftKind`.                                                                    |
| `remove(ref, actor) -> None`                                   | Cascade-cleanup symlinks, delete master, delegate to `ResourceService.delete`.                                                 |
| `cleanup_bindings_for_agent(agent_ref) -> None`                | Called by spec 004's `agent.on_delete` hook; removes all bindings + symlinks for that agent.                                   |

### File viewer (`application/skill/file_ops.py`)

Read-only, stateless helpers beside `service.py` (same pattern as
`verify_ops.py` / `update_ops.py`) that expose a skill's master folder to
surfaces. No DB, no audit, no mutation; containment is enforced by resolving
every candidate path and requiring it to stay inside the resolved master
folder, reusing the path-escape approach from `domain/skill/validator.py`.

| Function                                                 | Purpose                                                                                                                      |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `build_file_tree(master_folder) -> FileNode`             | Recursively list the master folder; skip symlinks whose real target escapes the folder; never descend symlinked dirs.        |
| `read_skill_file(master_folder, relpath) -> FileContent` | Resolve `master_folder/relpath`, verify it stays inside the folder (else `ValueError`), read with a size cap, detect binary. |

#### File-node shape (`FileNode` / `SkillFileNodeOut`)

One node in the recursive tree. The root node has `path == ""`.

| Field      | Type              | Notes                                                                      |
| ---------- | ----------------- | -------------------------------------------------------------------------- |
| `name`     | `str`             | entry's base name                                                          |
| `path`     | `str`             | POSIX path relative to the master folder root (`""` for the root)          |
| `type`     | `"file" \| "dir"` | node kind                                                                  |
| `size`     | `int \| None`     | byte size for files; `null` for directories                                |
| `children` | `list[FileNode]`  | populated for directories (sorted dirs-first then by name); `[]` for files |

#### File-content shape (`FileContent` / `SkillFileContentOut`)

A single file's contents, read-only.

| Field       | Type   | Notes                                                                            |
| ----------- | ------ | -------------------------------------------------------------------------------- |
| `path`      | `str`  | POSIX path relative to the master folder root                                    |
| `content`   | `str`  | file text; empty (`""`) when `binary` is true                                    |
| `truncated` | `bool` | true when the file exceeded the 256 KiB read cap and only the prefix is returned |
| `binary`    | `bool` | true when the file is non-UTF-8 or contains a NUL byte (content is empty)        |
| `size`      | `int`  | true byte size of the file on disk (independent of any truncation)               |

### `SourceFetcher` (`infrastructure/skill/source_fetcher.py`)

Provides `fetch_git(url, ref, subpath) -> Path` returning a tmp directory with
the cloned content at `subpath`. Uses `git` subprocess via SSRF-guarded
`httpx.AsyncClient`-like predicate: validates URL host is not loopback /
RFC1918 / link-local before invoking `git clone --depth=1 --branch=<ref> --filter=blob:none`.

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

1. Builds `SkillBindingRepo`, `MasterStore`, `SyncEngine`, `SourceFetcher`, and the `SkillService` (plus its `update_ops` / `verify_ops` collaborators).
2. Constructs the skill `Kind` via `make_skill_kind(...)` and registers it into `app.state.kinds["skill"]`.
3. Reads the existing agent `Kind` already registered by `_wire_agent_kind` and builds a new `Kind` whose `on_delete` is a closure: first `await skill_svc.cleanup_bindings_for_agent(ref)`, then delegate to the original agent `on_delete`. The wrapped agent kind replaces the previous entry in `app.state.kinds["agent"]`.
4. Mounts the `skill_routes` router.

This closure-based composition keeps both kinds independent at the application layer (neither imports the other) and centralises cross-kind glue at the composition root.

## Constraints summary

- All HTTP loopback-only.
- Git fetch through SSRF-guarded URL predicate (loopback / RFC1918 / link-local rejected).
- No keychain entries in v1 (no auth on skill sources).
- File-size limit: 50 MB total per skill folder, enforced by `validate_skill_folder`. The limit is a `SkillService` constructor default (`size_limit_bytes`); it is not yet plumbed to a config file, so v1 always uses the hardcoded 50 MB.
