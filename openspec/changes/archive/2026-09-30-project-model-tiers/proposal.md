## Why

The model keys Coffer projected into Claude Code were the wrong ones. `env.ANTHROPIC_MODEL` outranks the top-level `model` key that `/model` saves, so every launch undid the user's own model choice. The "fast model" slot wrote `env.ANTHROPIC_SMALL_FAST_MODEL`, which is deprecated and still read ahead of the Haiku pin that replaced it. Claude Code asks for models by tier (Opus, Sonnet, Haiku, Fable), and a tier left unpinned on an endpoint that serves no Claude ids sends a Claude id and fails. Behind a custom base URL the background model is the main model unless Haiku is pinned.

Codex had two gaps. The catalogue Coffer wrote declared no effort levels, so Codex never sent the effort the agent was set to. It also declared no context window, so a gateway or local model with a smaller window than Codex's 272k fallback was never compacted in time.

## What Changes

- The agent's model binding carries `model`, `effort` and `tier_models` (Claude Code's `opus`, `sonnet`, `haiku`, `fable`) instead of `fast_model`. A migration moves every Claude Code agent's `fast_model` into its Haiku tier and strips the key from every agent row.
- `PATCH /api/v1/agents/{uid}` takes `effort` and `tier_models`; `coffer agent edit` gains `--effort`, `--clear-effort`, `--tier <tier>=<model>` (repeatable) and `--clear-tiers`, replacing `--fast-model` and `--clear-fast-model`.
- Claude Code gets the top-level `model` and `effortLevel`, `env.ANTHROPIC_DEFAULT_<TIER>_MODEL` for each pinned tier (Coffer's suggestion when the agent stores none), a `modelPicker` listing the connection's curated models (replacing the built-in rows on an endpoint that serves no Claude ids), and, for a local runtime, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` and `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. Every write deletes `env.ANTHROPIC_SMALL_FAST_MODEL` and `env.ANTHROPIC_MODEL`.
- Each curated model can record its context window and its effort levels. Codex's catalogue entries carry the window, a 90% auto-compact limit and the levels, and `model_reasoning_effort` is written only when the chosen model has levels.
- Switching back to the built-in login removes every key Coffer wrote. A `model` or `effortLevel` the user has changed since stays, and so does a `modelPicker` Coffer did not write.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: the model binding carries effort and tier pins in place of the fast model.
- `provider-switching`: what the Claude Code and Codex projections write for the binding, the tier suggestion, the curated models' windows and levels, and what switching back removes.

## Impact

- Backend: `domain/agent/{config,tiers}.py`, `domain/provider/{projection,codex_projection,agent_projection,model_binding,config}.py`, `application/provider/{projector,projection_reconcile}.py`, `application/agent/service.py`, `surfaces/http/{agent_routes,provider_routes,provider_schemas}.py`, `surfaces/cli/agent_cmd.py`, migration `0110`.
- Frontend: generated types; the agent connection draft stores the old fast slot as the Haiku tier.
- Docs: the providers guide and the agent CLI reference.
