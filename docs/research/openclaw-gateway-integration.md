# OpenClaw integration design (deferred)

> 中文版: [openclaw-gateway-integration.zh.md](openclaw-gateway-integration.zh.md)
>
> **Status: design-only, not implemented.** [ADR-040](../decisions/ADR-040-re-widen-agent-registry.md) re-added `opencode` / `hermes` / `cursor` as managed leaf agents but deliberately left **openclaw** out of the agent registry. This note is the "separate design track" ADR-040 promised: how Coffer *would* integrate openclaw when there is a real need, and why it is not an `AgentType`.

> **Correction (2026-07-09, [ADR-042](../decisions/ADR-042-context-injection-mechanisms.md)).** The capability table below is **wrong on three of five rows**. A first-principles re-check against openclaw's docs found: MCP servers ARE injectable (`mcp.servers` in `~/.openclaw/openclaw.json`; writing one `coffer` entry is one-directional and creates no cycle — only *also* registering `openclaw mcp serve` as a Coffer upstream would close the loop); native memory IS disableable (`plugins.slots.memory: "none"` or `plugins.entries.memory-core.enabled: false`); and skills ARE drop-in — `~/.openclaw/skills/<name>/SKILL.md`, the same shape Claude Code uses, so Coffer's existing `FOLDER` delivery works unchanged. Provider projection is supported *and* reads keys from `${ENV}`. Only the **hooks** row holds: openclaw's hooks are in-process TS/JS running inside the Gateway, with no session-start event, and context injection requires a typed plugin (`api.on(...)`) — i.e. Coffer's `PLUGIN_DROP` mode.
>
> **The conclusion is therefore reversed: openclaw IS a viable managed leaf agent.** It is planned as one, pending a real install to verify against (it is not installed on the author's machine, and Coffer's spec rule requires real end-to-end use). Two things this document got right and that still matter: openclaw drives Claude Code / Codex / OpenCode as sub-workers, so Coffer's writes to `~/.claude/` are inherited by openclaw-spawned workers; and its headless CLI (`openclaw agent --message … --json --local`) returns one JSON blob with **no streaming**, so it would be Coffer's only non-streaming chat provider.
>
> Read the table below as a historical record of the reasoning ADR-040 relied on, not as current fact.

## What OpenClaw is

OpenClaw (`openclaw/openclaw`, docs.openclaw.ai) is a self-hosted, multi-channel **personal-agent gateway** — not a coding CLI. It is a peer of Coffer, not a leaf under it. It ships its own:

- **agent runtime + multi-agent router** — it *runs* agents and routes between them;
- **coding-agent orchestration** — it itself drives Claude Code CLI, Codex CLI, and OpenCode as sub-tools;
- **persistent memory** — per-agent SQLite (`agents/<id>/agent/openclaw-agent.sqlite`) + `MEMORY.md`, embeddings + sqlite-vec;
- **MCP** — it is both an MCP *host* (consumes servers) and an MCP *server* (`openclaw mcp serve`);
- **hooks** — an internal `HOOK.md` + `handler.ts` system (`agent:bootstrap`, `session:compact:*`, `gateway:startup`…), with no external "session-start" event;
- **channels** — Slack / Discord / Telegram / WhatsApp / … plugins served by one gateway;
- **config** — `~/.openclaw/openclaw.json` (JSON5).

## Why openclaw is NOT a managed leaf agent

Coffer's managed-agent model is "Coffer owns the shared substrate; the agent is a leaf that Coffer projects config into." Concretely a leaf agent gets: **MCP injection** (Coffer writes its `coffer` server into the agent's config), a **session-start hook** (Coffer injects rules/memory at turn start), **provider projection** (Coffer points the agent at a chosen LLM connection), and **native-memory disable** (Coffer becomes the single memory store). None of these map onto openclaw:

| Coffer leaf facet | openclaw reality | verdict |
| --- | --- | --- |
| MCP injection | openclaw is itself an MCP host + server; writing a `coffer` entry into config it owns duplicates/loops | **N/A** |
| Session-start hook (rules/memory) | no external session-start event; hooks are openclaw-authored `HOOK.md`/`handler.ts` inside `~/.openclaw/` | **N/A** |
| Native-memory disable | openclaw's memory (SQLite + embeddings) is core to its runtime and not externally toggleable per turn | **N/A / conflicts** |
| Provider projection | openclaw fully supports a custom base URL + key (`openclaw onboard --custom-base-url … --custom-api-key …`) | **supported, but see below** |
| Skills / plugins | ClawHub skills + `openclaw.plugin.json` — a different model, openclaw-managed | **N/A** |

Forcing openclaw into `AgentType` would mean four of the six facets are permanent gaps, and the memory/MCP layers would actively conflict with openclaw's own. That is the wrong abstraction.

## Recommended integration: an OpenAI-compatible LLM-connection endpoint

The only coherent seam is the one openclaw already exposes for machines: its **gateway's OpenAI-compatible HTTP API**. Run `openclaw gateway` (default port `18789`), enable `gateway.http.endpoints.chatCompletions`, and it answers `POST /v1/chat/completions` (and OpenResponses `POST /v1/responses`) with a Bearer token, selecting the target openclaw agent via the `model` field (`openclaw/<agentId>`), `stream:true` → SSE.

This maps cleanly onto Coffer's **LLM-connection** machinery (the unified connections registry, [ADR-032](../decisions/ADR-032-provider-switching.md)), NOT the agent registry:

- **Add openclaw as a Coffer LLM connection**: `base_url = http://127.0.0.1:18789/v1`, protocol `openai` (chat-completions), credential = the gateway Bearer token stored in the OS keychain (never plaintext). The connection's model list is `openclaw/<agentId>` values.
- **Who consumes it**: exactly what consumes any Coffer connection — the built-in Coffer chat/console and any managed agent the user routes to it. In effect openclaw becomes *one more model provider* Coffer can talk to, backed by a full agent behind the gateway.
- **What Coffer does NOT do**: inject MCP, inject a session hook, disable native memory, or project instructions — openclaw owns those. Coffer treats the gateway as an opaque OpenAI-compatible model.

This keeps the relationship honest: openclaw is a peer control plane, and Coffer consumes it the way it consumes any other OpenAI-compatible endpoint.

## What (if anything) to build later

Nothing is required to make the above work today beyond documentation — a user can already add openclaw's gateway as a custom OpenAI-compatible connection in `/settings/llm-connections` by hand. A future convenience slice *could* add:

1. **A recognizer** so a connection whose `base_url` is an openclaw gateway is labeled "OpenClaw" in the UI and its `model` picker offers `openclaw/<agentId>` values fetched from `GET /v1/models`.
2. **A one-click onboard** that shells out to `openclaw onboard --non-interactive` / reads `~/.openclaw/openclaw.json` to pre-fill the connection.

Both are additive to the connection registry and touch no agent-registry code.

## Deferred decisions / open questions

- **Auth lifetime** — the gateway Bearer token rotation story vs Coffer's keychain reference.
- **Streaming shape** — confirm openclaw's SSE frames match Coffer's OpenAI-chat streaming parser (it already handles `[DONE]`).
- **Trigger to build** — implement the recognizer/onboard only on first real user need (YAGNI); until then, the manual custom-connection path suffices.

## References

- [ADR-040: re-widen the agent registry](../decisions/ADR-040-re-widen-agent-registry.md) — the decision that openclaw stays out of the leaf registry.
- [ADR-032: provider switching](../decisions/ADR-032-provider-switching.md) — the LLM-connection / credential-isolation machinery openclaw would plug into.
- OpenClaw gateway OpenAI HTTP API — `docs.openclaw.ai/gateway/openai-http-api`, `.../gateway/configuration`, `.../cli/onboard`.
