## Why

Reasoning effort was a setting Coffer carried in six places: the agent's model
binding, the Change model dialog, a connection's curated models, the files it wrote
into the agents' own config, the Chat composer, and the channel `/model` command.
Each agent already picks its own effort from its own configuration and exposes its
own control for it, so Coffer's copy was a second place to set the same thing, and
the values it wrote into `settings.json` and `config.toml` outlived the choice that
produced them.

Coffer no longer has a reasoning-effort setting. The agent runs at the effort its
own configuration names.

## What Changes

- **BREAKING** The agent's model binding is `model` and `tier_models`.
  `PATCH /api/v1/agents/{uid}` and the Change model dialog take no `effort`, and the
  agent's Overview › Model section has no Effort row.
- **BREAKING** The model catalogue entry carries `id`, `label` and `description`.
  The agent runtime's reasoning levels and defaults are no longer read, and the
  `claude_effort` source of the installed SDK's `EffortLevel` is gone.
- **BREAKING** A curated model records a context window and nothing else.
  `effort_levels` and `default_effort` leave the connection's config and its REST
  schema; an entry written earlier is read without them and the next write drops them.
- Coffer no longer writes `effortLevel` into Claude Code's `settings.json` or
  `model_reasoning_effort` into Codex's `config.toml`, and the Codex catalogue
  carries an empty `supported_reasoning_levels` and no `default_reasoning_level`.
  Keys an earlier version wrote carry no ownership mark, so they stay in the file as
  the user's own.
- The Chat composer has no effort picker, and a conversation's agent config holds
  only its model. The `effort` of a stored conversation is dropped by a migration.
- The channel `/model` command is one step: the model. A word such as `/model high`
  is a model name like any other; `/model default` clears the model. The effort
  cards and the chat thread's remembered effort are gone, and a migration drops the
  stored column.
- Requirements renamed because their scenarios no longer mention effort:
  "Switch the model and reasoning effort from chat" becomes "Switch the model from
  chat"; "Keep a chat's settings across its conversations" becomes "Keep a chat's
  agent, model and directory across its conversations"; "Let the owner set agent,
  model and reasoning level" becomes "Let the owner set agent and model"; "Record a
  context window and effort levels with each curated model" becomes "Record a
  context window with each curated model"; "Project into Codex config without
  clobbering it" becomes "Project into Codex config without overwriting it"; "Offer
  every connection operation on REST and the web" becomes "Offer every connection
  operation over REST and in the web UI"; "Expose every agent operation through REST
  and the Agents page" becomes "Expose every agent operation over REST and on the
  Agents page".
- The guides, reference pages, architecture pages, data-model files and the ADRs that
  described reasoning effort say that the agent decides it.

## Capabilities

### Modified Capabilities
- `agent-registry`: the model binding and catalogue entry carry no effort; three
  effort requirements are removed.
- `agent-registry/claude-code`: the SDK effort-level source is removed.
- `agent-registry/codex`: the per-model effort levels and default are removed.
- `provider-switching`: projection, review, curated models and revert carry no effort.
- `channels`: `/model` sets the model only; the chat's remembered settings drop effort.
- `chat`: the owner sets agent and model; the composer has no effort control.
- `experimental-features`: the read-only Model section shows the model only.
- `web-ui`: a citation follows the renamed provider-switching requirement.
