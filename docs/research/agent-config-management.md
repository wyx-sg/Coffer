# Competitive Research — Unified Multi-Agent Config & Rules Management

> English: this file · 中文版: [agent-config-management.zh.md](./agent-config-management.zh.md)
>
> Internal competitive-research report for Coffer's agent registry + config-file
> management (spec 004). **Date:** 2026-06-16. **Method:** deep-research harness.
> **Provenance caveat:** 1 claim (Ruler's MCP propagation) survived full 3-vote
> adversarial verification; the rest are primary-sourced from project READMEs but
> rate-limiting cut re-verification short — treat as primary-sourced, flag for a
> light fact-check.

## 1. Landscape at a glance

Tools that "unify config across AI coding agents on one machine" split into three
structurally different categories:

| Category                         | What it does                                                | Examples                                                      |
| -------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| **Source-of-truth distributors** | One central dir → generate each agent's native config files | ruler, rulesync, ai-rulez, airul, vibe-rules, ai-agent-config |
| **Shared instruction standards** | A common _output format_ every agent reads (not a manager)  | **AGENTS.md** (25–60k+ projects, 28+ agents)                  |
| **Hosted discovery catalogs**    | Index/browse rules & configs; do not sync                   | cursor.directory                                              |

The dominant pattern is **one-directional generation**: a declarative source
(`.ruler/`, `.rulesync/`, `.ai-rulez/`) is compiled into each agent's native
files. MCP-server config management appears in the advanced tools (ruler,
rulesync, ai-rulez, ai-agent-config) and is absent from rules-only tools (airul,
vibe-rules) and from the AGENTS.md standard.

### The players

- **Ruler** (`intellectronica/ruler`, MIT CLI) — centralizes instructions in a
  `.ruler/` dir and distributes into **28+ agents'** native files (CLAUDE.md,
  AGENTS.md, .clinerules, …). It propagates MCP servers from a central
  `ruler.toml` (`[mcp_servers.<name>]`) into each agent via **merge** (default)
  or **overwrite** strategy, with per-agent overrides
  (`[agents.<agent>.mcp_servers.<name>]`); legacy `.ruler/mcp.json` still works
  with a deprecation warning, TOML taking precedence. **No drift detection, no
  secrets handling, CLI-only; adding a new agent requires TypeScript
  agent-handler code.** [confirmed 2-0 — github.com/intellectronica/ruler]
- **rulesync** (`dyoshikawa/rulesync`, Node CLI) — the broadest feature set
  surveyed: rules, MCP config, ignore files, subagents, slash commands, skills,
  hooks, permissions, generated from one `.rulesync/` dir. Targets Cursor,
  Claude Code, Copilot, Codex, Gemini CLI, Cline, OpenCode, Zed, Goose, Roo,
  Kilo, Junie — **not Windsurf or Aider**. CLI-only, one-directional.
  [github.com/dyoshikawa/rulesync]
- **ai-rulez** (`Goldziher/ai-rulez`) — generates configs for **19+ tools**;
  manages rules/context/skills/agents/slash-commands/MCP, and notably **ships
  its own built-in MCP server that it injects into agents** — conceptually close
  to Coffer's "hub serves one MCP entry to every agent."
  [github.com/Goldziher/ai-rulez]
- **airul / vibe-rules** — lighter CLIs that distribute **rules/instructions
  only** from one source to many agents; no MCP, no secrets, no drift/backup.
- **ai-agent-config** — CLI that syncs config including MCP across tools.
- **AGENTS.md** — an open, vendor-neutral, **per-project** instruction file
  (not a central manager) adopted by 25–60k+ projects and read by 28+ agents
  (Codex reads it before acting). It is the _lingua franca output_, not a tool.
- **cursor.directory** — hosted web registry that indexes rules/MCP for browsing,
  with no local sync.

## 2. Capability comparison

| Capability                       | Ruler                  | rulesync | ai-rulez        | airul / vibe-rules | AGENTS.md    | **Coffer**                             |
| -------------------------------- | ---------------------- | -------- | --------------- | ------------------ | ------------ | -------------------------------------- |
| Rules/instructions distribution  | ✅ 28+ agents          | ✅ 12+   | ✅ 19+          | ✅ rules only      | (the format) | **❌ not a hub asset**                 |
| MCP config management            | ✅ merge/overwrite     | ✅       | ✅ + own server | ❌                 | ❌           | ✅ gateway + adopt                     |
| Subagents / commands             | partial                | ✅       | ✅              | ❌                 | ❌           | read/edit per agent                    |
| Direction                        | one-way (source→files) | one-way  | one-way         | one-way            | n/a          | **bi-directional (adopt)**             |
| Reads agent's REAL state         | ❌                     | ❌       | ❌              | ❌                 | ❌           | **✅ read-time, never stored**         |
| Safe edit (backup / concurrency) | ❌                     | ❌       | ❌              | ❌                 | ❌           | **✅ atomic + .bak + fingerprint 409** |
| Secrets handling                 | ❌                     | ❌       | ❌              | ❌                 | ❌           | **✅ encrypted store + refs**          |
| New agent = data vs code         | code (TS handler)      | code     | code            | code               | n/a          | **✅ manifest data record**            |
| Interface                        | CLI                    | CLI      | CLI             | CLI                | file         | **CLI + REST + desktop GUI**           |
| Per-project scope                | ✅                     | ✅       | ✅              | ✅                 | ✅           | **❌ user-global config_dir only**     |
| Agents covered today             | 28+                    | 12+      | 19+             | several            | 28+          | **2 enabled (4 wired, hidden)**        |

## 3. How Coffer compares

**Where Coffer is structurally ahead.**

1. **Bi-directional, not one-directional.** Every competitor _generates_ config
   one way (source → agent files). Only Coffer also _ingests_ — "adopt" pulls a
   per-agent MCP server (or skill) INTO a shared hub and redistributes it. None
   of these tools have an ingest half.
2. **Reads the agent's real state.** These tools write but never read back what
   the agent actually has, so they have **no drift detection**. Coffer's
   read-time derivation of the agent's actual MCP entries / plugins / dirs _is_
   continuous drift-awareness.
3. **Safe edit is unique.** Atomic write + `.bak` + content-fingerprint
   optimistic concurrency (409 on stale write) has no equivalent — the
   competitors overwrite files with no backup or concurrency guard.
4. **Secrets + GUI + manifest onboarding.** Coffer has an encrypted credential
   store (competitors handle no secrets), a desktop app (they are CLI-only), and
   onboards a new agent via a single capability-manifest record rather than
   Ruler-style per-agent handler code.

**Where Coffer lags / has a real gap.**

1. **It does NOT distribute rules/instructions from one source to many agents —
   the defining feature of this entire category.** Coffer treats CLAUDE.md /
   AGENTS.md as per-agent editable files; it has hub-and-spoke for MCP and
   skills but **no "master instructions → all agents" delivery.** This is the
   single most important gap surfaced by the research.
2. **Breadth.** Ruler covers 28+ agents, ai-rulez 19+, rulesync 12+. Coffer
   enables **2** (4 more wired but hidden). For a "manage all your agents" tool,
   that breadth gap is material.
3. **No per-project scope.** These tools operate per-repository (`.ruler/`,
   project AGENTS.md). Coffer manages only the user-global `config_dir`. A large
   share of real config lives per-project, which Coffer does not touch.
4. **No declarative, version-controllable source.** The competitors' single
   declarative file is a feature (diff-able, committable). Coffer's manage-in-place
   model has no exportable declarative form — relevant to the multi-machine sync
   spec.

## 4. Key takeaways for Coffer

1. **Add "instructions/rules" as a hub-delivered asset kind.** You already do
   ingest→hub→deliver for MCP and skills; a master CLAUDE.md/AGENTS.md delivered
   to every agent (à la ruler/rulesync) closes the one feature this whole
   category is built around — and your bi-directional adopt would make it
   best-in-class.
2. **Align to the AGENTS.md standard** as the shared instruction format so a
   delivered master instruction is portable to 28+ agents verbatim.
3. **Decide on per-project scope.** Repo-scoped config is a whole axis the
   competition owns and Coffer ignores; either embrace it or consciously
   declare it out of scope.
4. **Light up the hidden agents.** The competition supports 12–28; shipping the
   4 wired-but-hidden agents (Cursor/OpenCode/OpenClaw/Hermes) narrows the
   breadth gap cheaply since the manifest mechanism already exists.
5. **Add a declarative export** (ruler.toml-style) of hub state to feed
   version-control and the multi-machine sync spec.

## 5. Sources

Primary (project repos/docs):

- github.com/intellectronica/ruler _(confirmed: MCP propagation)_
- github.com/dyoshikawa/rulesync
- github.com/Goldziher/ai-rulez
- airul, vibe-rules, ai-agent-config (project READMEs)
- agents.md / the AGENTS.md standard; OpenAI Codex docs (AGENTS.md discovery)
- cursor.directory
