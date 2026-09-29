## Context

`agent` rows were ordinary resources: any name, an optional title and description, and one rule — one agent per config directory. Two agents of one type were allowed on two directories, and the model catalogue picked the one first by name. Every cross-kind reference to an agent already holds its uid (migration 0096), and the channel runtime routes by agent *key* (the type). `mcp_server` and `skill` declared their names fixed (ADR names-visible-to-agents-are-fixed) and gained an editable `title` in migration 0106.

## Goals / Non-Goals

**Goals:** one agent per type, named by it, with the config directory as its only per-agent setting besides the type (and the model binding, unchanged); addressing by type on REST and the CLI; a per-type detection read for a two-row Agents page; no title on agents, MCP servers and skills; a migration that leaves no load-time shim.

**Non-Goals:** the Agents page redesign (a separate web-ui change); several configurations of one type (deferred past 1.0); changes to the model binding.

## Decisions

### The name is derived from the type, declared on the kind

`Kind.name_from_config` returns the one name a row may carry; `ResourceService.register` refuses any other (422). `agent` supplies it (`claude_code` → `claude-code`) and also declares `name_fixed`, so a rename is `409 NAME_IMMUTABLE` with a message saying the name is the type. Name uniqueness within the kind then *is* one agent per type — no second index. `AgentService.register` checks the type first so the refusal says what it is (`409 AGENT_TYPE_REGISTERED`), then the existing one-per-directory rule.

*Rejected:* keeping a free name and adding a unique index on the type — two identifiers for one agent, which is the confusion being removed.

### Addressing by type is one router dependency

Every agent router carries `resolve_agent_path`, which rewrites a `{uid}` path parameter that spells a type into the registered agent's uid before the handler runs. FastAPI solves router dependencies before it reads path parameters, so every handler keeps receiving the uid it expects, and the uid form keeps working. The CLI already resolved names to uids; a name is now a type, and `claude_code` is normalised to `claude-code` in the one resolver.

*Rejected:* renaming every path parameter and threading a resolver through each handler — nine route files of churn for the same result.

### Titles are a per-kind declaration

`Kind.titled` (default `True`) is `False` for `agent`, `mcp_server` and `skill`. `checked_title` refuses a non-empty title for such a kind on register and on edit; clearing is a no-op. `ResourceOut.title` stays on the generic resource read (other kinds use it) and is always `null` for these three. The sync applier drops a title an older build still writes for them instead of refusing the document.

### Detection is a per-type listing

`AutoDetectService.types()` returns one row per descriptor: the registered agent's directory, or the directory Add would register — the standard one unless only the one the type's environment variable names exists — with the other existing directory as `other_config_dir`. `candidates` is the unregistered rows seen by either signal. `addable` is "not registered and the program is installed", so `installed_never_run` is addable: the route asks detection, and when the type is installed but never run and the target is its standard directory, `AgentService.register` creates it (privileged-path check first) and then the `skills` leaf, as for every agent. Any other missing directory is still refused.

### Migration 0108 keeps the agent the user actually uses

Per type with duplicates the kept row is, in order: the one whose own Coffer MCP entry carries its `--agent-uid` (read-only, best effort — a read failure counts as not connected), the enabled one, the most recently used (latest of `updated_at` and its newest audit entry), the one on the standard directory, the oldest. Dropped uids are replaced by the kept uid in every `scope_json` agents list (deduplicated, never widened to `NULL`) and in channel `default_agent`; a dropped row's `skill_agent_bindings` go with it. Nothing is written into the dropped agent's directory. The kept row is renamed to its type and loses its description; titles are cleared for the three kinds. The downgrade restores nothing: dropped rows and titles are not recoverable, and the collapsed rows are valid to an older build.

## Risks / Trade-offs

- A user with two Claude Code installs loses one registration on upgrade → the migration logs each dropped agent with its directory and the uid kept in its place, and the directory can be re-used by moving the one agent to it.
- The dropped agent's directory keeps Coffer's MCP entry and skill links → they point at a uid that no longer exists and do nothing harmful; removing them would mean a migration writing into agent files.
- Two machines that each registered `claude-code` under different uids still collide by name when syncing — as they did before, when both used the default name.
- The in-flight web-ui change `revise-web-ui-ia` edits several of the same agent-registry requirements; it rebases its deltas onto these.
