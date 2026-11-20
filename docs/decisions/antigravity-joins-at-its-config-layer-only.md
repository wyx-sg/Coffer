# Antigravity Joins Coffer Through Its Config Layer Only

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md), [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), spec agent-registry "Support exactly the Claude Code, Codex, Antigravity, Cursor, OpenCode and DeepSeek Harness agent types", spec agent-registry/antigravity

## Context

Google Antigravity is an agent product with three surfaces: the Antigravity 2.0
desktop App, the `agy` CLI and the Antigravity IDE (a VS Code fork). The owner
uses the App and asked for Coffer to support it.

What Antigravity offers, read on 2026-11-19 from its documentation
(`antigravity.google/docs`: mcp, skills, rules, hooks, plugins, permissions,
models, cli/headless, customization-discovery, commands/learn, sdk) and from the
offline guide its App ships (`~/.gemini/antigravity/builtin/skills/agy-customizations/`,
App 2.32.2 on the owner's Mac mini):

- **One personal config layer for all three surfaces.** `~/.gemini/config/`
  "applies to every project, in both the Antigravity App and the Antigravity
  CLI": `mcp_config.json` (a JSON `mcpServers` map, `command`/`args`/`env` for
  stdio, `url` for Streamable HTTP), `skills/<name>/SKILL.md`, `rules/*.md`,
  `hooks.json`, `plugins/`, and `config.json` (plugin switches and permission
  preferences). Each surface keeps its own data beside it:
  `~/.gemini/antigravity/` (App), `antigravity-cli/`, `antigravity-ide/`.
  Antigravity 1.x used other paths (`~/.gemini/antigravity/mcp_config.json`);
  the App leaves a `.migrated` marker in `~/.gemini/config/` after moving them.
- **Models.** Only the Google-hosted list (Gemini, plus Claude models Google
  hosts). Neither the App nor the CLI documents a custom endpoint, base URL or
  API key.
- **Memory.** No store of learned memories. `/learn` writes what it learned as
  rules or skills, after the person approves a proposal.
- **Sessions.** Per-conversation SQLite files holding undocumented protobuf
  blobs, a summaries database, and `brain/<id>/.system_generated/logs/transcript.jsonl`.
  Only the transcript path is documented (as a hook payload field).
- **Running it.** `agy -p … --output-format stream-json` is a headless mode. A
  Google forum answer that states it "reflects our current policy … and
  supersedes earlier forum comments" (discuss.ai.google.dev thread 189905,
  2026-10-16) says running `agy` from your own scripts and CI is permitted, but
  wrapping it inside third-party agents or tools "is not supported under
  consumer plans", and recommends a Gemini Enterprise or AI Studio API key for
  third-party orchestrators. Another answer cites the Antigravity Additional
  Terms of Service, section 6, against "extracting, proxying, or reusing
  Antigravity OAuth credentials inside third-party harnesses".
- **SDK.** `google-antigravity` (Python, Apache-2.0, 0.1.x) runs its own
  harness binary, authenticates only with a Gemini API key or Vertex, and reads
  skills, MCP servers and hooks from what the calling code passes, not from
  `~/.gemini/config`.
- **Permissions.** An MCP tool Antigravity has not been told about is in Ask
  mode; `mcp(server/*)` rules allow it.

How comparable tools join Antigravity: amtiYo/agents (one `.agents` source
synced to Codex, Claude Code, Gemini CLI, Cursor, Copilot and Antigravity)
writes MCP servers, skills and instructions only; claude-mem adds hooks and
instruction files; session search tools read the transcript JSONL; Antigravity's
own built-in `migrate-agent-settings` skill imports MCP servers, skills,
commands and instructions from Claude Code and Codex. None of them drives
Antigravity or points it at another model. Several GitHub projects turn the
Antigravity sign-in into an OpenAI- or Anthropic-compatible API; that is the
credential reuse the terms forbid.

## Options Considered

### Option A — The config layer only (chosen)

Antigravity is a third agent type whose descriptor names `~/.gemini/config` as
its config directory, `agy` as its program and `Antigravity.app` as its app
bundle. It has a projection with two entries — Coffer's MCP entry in
`mcp_config.json` and skills linked into `skills/` — a config-file allowlist,
and a dependency probe. It has no provider projection, no driver, no memory
reader and no session source.

Pros: it delivers what Coffer is for — one MCP endpoint and one skill library
for every agent — through files Antigravity documents for all three surfaces;
everything it writes is the same shape as what Claude Code receives (a JSON
`mcpServers` command map), so no new mechanism is needed; it stays inside
Antigravity's terms. Cons: Antigravity gets no Coffer chat, channels,
scheduled tasks, model connections or memory sync, and its agent page shows
tabs with nothing in them until a rule for missing facets lands. It wins
because each of those gaps is either impossible (models), not allowed (driving
`agy` on a personal plan) or has nothing to read (memory), and the remaining
gap — sessions — is something Antigravity's own App already shows.

### Option B — Config layer plus sessions read from its local storage

Add a session source over `conversation_summaries.db` and the transcript JSONL.

Pros: Antigravity sessions would appear in Coffer's all-agents session list.
Cons: the summaries database and the per-conversation files are undocumented
and have already moved once between versions; a reader is a parser of a closed
product's internal state that breaks silently on an update; Coffer could list
but never resume or rename a session, because both need the agent. It lost on
fragility for a view the App already has. It is kept in `docs/TODO.md` for when
Google documents the store.

### Option C — Full support: drive `agy` headless for chat, channels and scheduled tasks

Write a driver that runs `agy -p --output-format stream-json`, like the Codex
driver over `codex app-server`.

Pros: Antigravity would be a chat agent like the other two, and would answer in
Telegram and SeaTalk. Cons: Google's stated policy is that wrapping `agy` inside
a third-party tool is not supported on consumer plans, which is the plan the
owner uses; the risk is the owner's account. MCP tools also start in Ask mode,
which a headless turn cannot answer. It lost on the terms.

### Option D — Drive Antigravity through its Python SDK with an API key

Add a driver over `google-antigravity`, authenticated with a Gemini API key the
person stores as a Coffer secret.

Pros: this is the route Google names for third-party orchestration; the SDK
streams thoughts and tool calls and is Python, like the daemon. Cons: it is a
second agent, not the person's Antigravity — it does not read
`~/.gemini/config`, so its skills, rules and MCP servers would have to be
passed in by Coffer, and its usage is billed to the API key rather than the
person's subscription. Nothing in use needs it today. It is the path to take if
Coffer chat on Antigravity is wanted, and is recorded in `docs/TODO.md`.

### Option E — Do not support Antigravity

Pros: no new type to maintain. Cons: serving every agent the person uses
through one Coffer is what the project is for, and the config layer costs one
descriptor record and one allowlist. It lost because the cost is small and the
format is documented.

## Decision

Support Antigravity as a third agent type through its config layer only
(Option A). The descriptor gains one value, `app_bundle`, so a product that
ships as a desktop app reads installed without its CLI on the `PATH`; the
dependency probe looks for the bundle where the operating system keeps
applications only when the program is not found. The facet contract test treats
a missing provider projection, driver or memory reader as an absent facet, as
the facets ADR already intends; only the dependency probe is required of every
agent.

Two details follow from what Antigravity does:

- Coffer's MCP entry carries `"timeoutSeconds": 86400`, because Antigravity cuts
  a tool call off after 180 seconds and a Coffer tool can wait on the person.
- Coffer writes no permission rule. Allowing `coffer` in Antigravity's Ask
  prompt is the person's choice, and the App's permission store is not
  documented.

## Consequences

- `AgentType` has three members, the Agents page three rows, and the first-run
  action connects every connectable agent ("Connect all") instead of exactly
  two.
- Antigravity never appears in the chat picker, channel agent pickers or
  scheduled tasks, and no model connection reaches it: those lists already come
  from the bound driver and provider facets.
- Memory sync neither reads from nor writes to Antigravity. Writing hub
  memories as a global `trigger: glob` rule per project is possible and is left
  for a separate decision.
- Nothing is read from `~/.gemini/antigravity*/`, including its OAuth tokens.
- Antigravity's paths changed once already. Detection reports the App's version,
  and a future move is a change to one descriptor record.
