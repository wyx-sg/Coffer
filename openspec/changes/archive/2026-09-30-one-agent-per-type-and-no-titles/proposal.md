## Why

A machine could hold several agents of one type, each with a name, a title and a description a person made up. Nobody runs two Claude Codes from one Coffer, and the extra fields were one more thing to get wrong: which of two Claude Codes answered for the type depended on their names, the Agents page had to invent rows for types it did not know about, and a channel or a reach list could name a duplicate nobody used. The Agents page being redesigned shows exactly two fixed rows — Claude Code and Codex — which the registry has to support.

MCP servers and skills carry a fixed name that agents see, plus an editable `title` added days ago as the cosmetic alternative to renaming. Two names for one thing made every surface decide which to show, and the title has no reader outside Coffer. A server's description and a skill's SKILL.md description already say what each is.

## What Changes

- **One agent per type per machine, named by the type.** An agent's name is `claude-code` or `codex`, derived from its type and fixed; it has no title and no description. Registration takes only the type and, optionally, a config directory (the standard one by default); a second agent of a registered type is refused with `409 AGENT_TYPE_REGISTERED`, and moving the agent is its config-directory edit.
- **Agents are addressed by type.** Every `/api/v1/agents/{uid}/…` route also takes the type (`claude-code` or `claude_code`); every `coffer agent …` command, `coffer path agent`, `coffer scan --agent` and a scope's `--agents` take it.
- **Every type's detection state, always.** `GET /api/v1/agents/types` lists each supported type — registered or not — with its state (`installed_active`, `installed_never_run`, `config_only`, `missing`), version, directory, standard directory, whether it can be added, and the other directory its environment variable names. Candidates are at most one per type.
- **An agent installed but never run can be added.** Registering it at its standard directory creates that directory holding only what Coffer needs. A `config_only` type cannot be added.
- **No title on agents, MCP servers or skills.** A non-empty title on those kinds is refused (422) on every surface; `coffer mcp add|edit` and `coffer skill add` lose `--title`, and `coffer skill edit` is removed because nothing on a skill record is editable. The web UI shows their names. The other kinds keep their titles. A synced document from an older build that still carries a title for these kinds is applied with the title ignored.
- **Migration 0109** collapses existing agents to one per type — keeping the connected one, then an enabled one, then the most recently used, then the one on the standard directory — re-points every reach list and channel default at the kept agent, renames it to its type, clears the three kinds' titles and agents' descriptions, and logs each dropped duplicate.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: one agent per type, named by it; addressing by type; the per-type detection listing; `installed_never_run` is addable; the model catalogue no longer chooses between two agents of a type; the lifecycle loses name, title and description.
- `resource-framework`: the title requirement is limited to the kinds that carry one; `agent` joins the fixed-name kinds; `edit --title` exists only where a title does.
- `mcp-gateway`: a server has a fixed name and a description, no title.
- `skill-manager`: a skill has a fixed name and its SKILL.md description, no title; `coffer skill edit` is gone.
- `vault-sync`: a kind with no title ignores one an older document carries.
- `web-ui`: the MCP server and skill pages no longer show or edit a title.

## Impact

- Backend: `domain/resource.py` (`Kind.titled`, `Kind.name_from_config`), `application/resource_kind_ops.py`, `resource_service.py`, `resource_title_ops.py`, `resource_rename_ops.py`, the agent, MCP and skill kinds, `application/agent/service.py` and `auto_detect.py`, the agent routes and a router dependency that resolves a type to the agent's uid, the sync applier, attention and reconcile subjects (an agent is labelled by its product name), CLI `agent`, `mcp`, `skill`, `scan`, `_kind_verbs`, `_resolve`, error code `AGENT_TYPE_REGISTERED`, migration `0109`.
- Contracts: agent-registry and skill-manager regenerated.
- Frontend: generated types and minimal compile fixes — add/edit agent forms lose name, title and description; MCP server and skill pages lose the title editor. The two-row Agents page is a separate change.
- Docs: agents, MCP servers and skills guides, the CLI, REST and error-code references, and a note on the ADR that made MCP and skill names fixed.
