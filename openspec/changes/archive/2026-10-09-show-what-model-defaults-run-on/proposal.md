## Why

Three gaps in how Coffer shows and routes models (user TODOs of 2026-10-07):

- Every "default" choice — Built-in default on an agent, Provider default on a
  channel, `Default model` in a channel's `/model`, `/status` and `/new` — named
  no model, and users do not know what the default is.
- Switching Claude Code to a DeepSeek provider failed every turn with Claude
  Code's "issue with the selected model", which it shows on an upstream 404, and
  the proxy logged nothing about it: it logged transport failures but not an
  upstream that answered with an error status. Users also expected the Claude
  desktop app to follow the switch; it reads its own third-party inference
  settings, never `settings.json`.
- A provider model id Claude Code does not know (`agnes-2.5-pro-alpha`) makes it
  warn and assume a 200k window, because Coffer writes
  `CLAUDE_CODE_MAX_CONTEXT_TOKENS` only for local runtimes and records no window
  for remote models.

## What Changes

- A default names the model it resolves to wherever it appears, and only when
  Coffer can know it: the model the agent's config names (on a provider, the one
  Coffer projected), else the built-in default the agent itself reports (Codex's
  `model/list` marks it). Claude Code decides its built-in default from its
  account at turn time, so a Claude Code agent with no model in its config still
  shows plain "Built-in default". `GET /api/v1/agent-providers/{agent_key}/models`
  gains `builtin_default` and `resolved_default`.
- The model proxy logs an upstream's error status (status, model, endpoint; never
  the body).
- The Change model dialog says that switching Claude Code changes the CLI only;
  the Claude desktop app keeps its own model settings.
- Context windows for provider models (pending the source order decided with
  the user) and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` for any connection whose chosen
  model has one.

## Impact

- Backend: agent model catalogue and Codex discovery, agent-providers route,
  channel command text, model proxy relay.
- Frontend: Agents list and Overview › Model, Change model dialog, channel
  Overview; en/zh copy.
- Specs: provider-switching, channels. Docs: providers guide (en/zh).
- Canvas: Agents (2.1 Overview › Model, Change model dialog), Run (channel
  Overview, `/model` card).
