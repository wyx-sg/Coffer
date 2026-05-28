# Data Model — 004 Agent Registry

Entities, fields, relationships, and SQLite additions for the agent registry.
Builds on the kind-agnostic Resource framework from spec 001.

## Domain entities (`backend/coffer/domain/agent/`)

### `AgentType` (`domain/agent/types.py`)

A string-valued enum (`StrEnum`).

| Value            | Display name     | Default `skill_dir` (POSIX expansion)                                                                                      |
| ---------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `claude_code`    | Claude Code      | `~/.claude/skills`                                                                                                         |
| `claude_desktop` | Claude Desktop   | macOS: `~/Library/Application Support/Claude/skills`; Linux: `~/.config/Claude/skills`; Windows: `%APPDATA%/Claude/skills` |
| `cursor`         | Cursor           | `~/.cursor/skills`                                                                                                         |
| `codex_cli`      | OpenAI Codex CLI | `~/.codex/skills`                                                                                                          |

Each enum value carries:

- `display_name: str`
- `default_skill_dir() -> Path` (computed per host platform)
- `detect_marker() -> Path` (the path checked during auto-detect; usually the parent of `default_skill_dir`)

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`. The kind-specific config schema registered with `ResourceService`.

| Field           | Type           | Notes                                                                  |
| --------------- | -------------- | ---------------------------------------------------------------------- |
| `type`          | `AgentType`    | required; enum value                                                   |
| `skill_dir`     | `Path \| None` | optional override; defaults to `type.default_skill_dir()` at read time |
| `auto_detected` | `bool`         | provenance; default `False`                                            |

Validators:

- `skill_dir` (when set) must resolve to an existing, writable directory.
- `skill_dir` must not point inside `/etc`, `/usr`, `/bin`, `/sbin`, `/System` (POSIX) or `C:\Windows`, `C:\Program Files` (Windows).
- `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected.

## SQLite schema additions

Migration `20260525_0005_agent_tables.py` adds:

### `suppressed_agent_types`

A small table recording agent types the user removed after auto-detection, so future scans don't recreate them.

| Column          | Type        | Constraints                   |
| --------------- | ----------- | ----------------------------- |
| `agent_type`    | `text`      | primary key; one row per type |
| `suppressed_at` | `timestamp` | UTC, set on insert            |

No FK to `resources`. A user re-registering an agent of a suppressed type lifts the suppression (the row is deleted on register).

### Reuse of existing tables

- `resources`: new rows with `kind='agent'`. No schema change.
- `audit_log`: new event types written (see below). No schema change.

## Audit event types added

Add to `AuditEventType` (`domain/audit.py`) — only the two agent-specific events that have no kind-agnostic equivalent:

| Value                   | When emitted                                                                                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `agent_auto_registered` | Auto-detect registers a new agent on daemon startup                                                                          |
| `agent_type_suppressed` | Internal: paired with the resource removal of an auto-detected agent, records the `agent_type` added to the suppression list |

The other lifecycle steps required by FR-011 — manual registration, update, enable, disable, and removal — are emitted as the existing kind-agnostic `resource_created`, `resource_updated`, `resource_enabled`, `resource_disabled`, and `resource_removed` events (each carrying the affected `agent:<name>` reference). No `agent_*` duplicates are added for these; surfaces filter by `kind='agent'` plus the kind-agnostic event type.

## Application service contracts (`backend/coffer/application/agent/`)

### `AgentService`

| Method                                                                      | Purpose                                                                                                                                  |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `register(type, name, skill_dir=None, description=None, actor) -> Resource` | Validate + delegate to `ResourceService.register(kind='agent', ...)`. On register, if a suppression row exists for `type` it is removed. |
| `update_skill_dir(ref, new_path, actor) -> Resource`                        | Delegate to `ResourceService.update_config`.                                                                                             |
| `list() -> list[Resource]`                                                  | Delegate to `ResourceService.list(kind='agent')`.                                                                                        |
| `remove(ref, actor) -> None`                                                | If `config.auto_detected=True`, insert a row in `suppressed_agent_types` for the type before deleting via `ResourceService.delete`.      |

### `AutoDetectService`

| Method                                       | Purpose                                                                                                                                                                                                                                                                                    |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `run_once(actor='system') -> list[Resource]` | Scan install markers for each `AgentType`; for any type not present in `resources` and not in `suppressed_agent_types`, register a new agent with `auto_detected=True`. Returns the newly-registered agents. Called once at daemon startup (and exposed via `POST /api/v1/agents/detect`). |

## Kind wiring (`backend/coffer/application/agent/kind.py`)

`make_agent_kind(...)` returns a `Kind` with:

- `name='agent'`
- `display_name='Agent'`
- `config_schema=AgentConfig`
- `on_delete=...` — cascade hook invoked by `ResourceService.delete` to call the **skill-side** binding cleanup (skill module provides the callback; agent kind does not import the skill module directly — wiring is via a setter on the kind module at composition root).

## Composition root wiring

In `surfaces/http/app.py`, a new helper `_wire_agent_kind(app, resource_svc, audit, sm)` (mirrors `_wire_mcp_kind`):

1. Build `AgentService` + `AutoDetectService`.
2. Construct the `Kind` via `make_agent_kind(on_delete_hook)`.
3. Register into `app.state.kinds['agent']`.
4. Mount `agent_routes` and `agent_detect_routes`.
5. Call `AutoDetectService.run_once(actor='system')` during startup lifespan.

The `on_delete_hook` is bound to a callable supplied by the skill module (spec 005), so that removing an agent triggers `SkillService.cleanup_bindings_for_agent(...)` synchronously before the resource row is deleted — once spec 005 wires the callback. Spec 004 only exposes the hook seam; PR #25 leaves it as a no-op until spec 005 supplies the callable.

## Constraints summary

- All HTTP routes bind `127.0.0.1`, share `X-Coffer-Token` auth (per spec 001).
- No new keychain entries — `agent` config has no credentials.
- No file content written outside `~/.coffer/` for spec 004 alone; spec 005 may write to agent `skill_dir`s.
