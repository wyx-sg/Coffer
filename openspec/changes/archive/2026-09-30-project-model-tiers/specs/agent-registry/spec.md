## MODIFIED Requirements

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `effort`, `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `effort` / `tier_models` / `wire_api`, and `coffer agent edit` exposes them as `--model`, `--effort`, `--tier <tier>=<model>` (repeatable) and `--wire-api`, with `--clear-effort` and `--clear-tiers` for the explicit nulls that unbind them — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. A field the request omits is unchanged; `tier_models`, when sent, replaces the whole mapping. Only `effort` and `tier_models` clear on an explicit null; `model` and `wire_api` have no null that unbinds them, so an explicit null for either is treated as omitted. A tier other than the four is refused. The binding carries no `fast_model`: Claude Code's background model is its Haiku tier, and the migration that removed the field moved each Claude Code agent's fast model into `tier_models.haiku`. Projecting a binding into the agent's native config is provider-switching's; validating a bound value against what one type accepts is that type's child spec (see [agent-registry/codex](codex/spec.md) "Accept only responses as Codex's wire_api" for `wire_api`).

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent edit` with `--model`, `--effort high` and `--tier haiku=<model>`, then again with `--clear-tiers`
- **THEN** the agent record reports the bound `model`, `effort` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` and `effort` are unchanged

#### Scenario: an earlier fast model becomes the Haiku tier
- **GIVEN** a vault whose Claude Code agent was bound with a `fast_model`
- **WHEN** the daemon migrates the vault
- **THEN** the agent's `tier_models.haiku` names that model, unless a Haiku pin was already there, and no agent row carries `fast_model`
