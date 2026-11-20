# Cursor, OpenCode and DeepSeek Harness Are Supported Agents, Each With Every Facet It Offers

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Behaviour Lives in One Descriptor Record per Agent](agent-descriptor-manifest.md), [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [A Shared Skills Directory Holds One Link for Every Agent That Reads It](a-shared-skills-directory-holds-one-link-for-every-reader.md), [DeepSeek Harness's MCP Row Lives in a Block Coffer Owns](deepseek-harness-mcp-row-lives-in-a-block-coffer-owns.md), [OpenCode Gets Its MCP Entry in the 1.x Shape](opencode-gets-its-mcp-entry-in-the-1x-shape.md), spec agent-registry "Support exactly the Claude Code, Codex, Antigravity, Cursor, OpenCode and DeepSeek Harness agent types", PR #87, PR #309

## Context

Coffer's job is to serve every coding agent a person uses from one vault: one
MCP gateway, one skill library, one set of model connections. In 2026-09
PR #309 narrowed the agent set to Claude Code and Codex. The four types it
removed (Cursor, OpenCode, OpenClaw, Hermes) "were never installed on the
maintainer's machine, so every facet was written against upstream docs and
one-off probes and could never be regression-tested locally".

On 2026-11-19 the owner asked for Cursor, OpenCode and DeepSeek Harness (`dsh`,
DeepSeek's open-source agent runtime, first released 2026-08-13) to be
supported, with as many features as each can take. The research behind this
ADR is `agent-support-deepseek-cursor-opencode/讨论稿.md` in the project files;
DeepSeek Harness facts were read from the documentation its npm package ships
(`@deepseek-ai/dsh` 0.2.2-rc.5), not from articles about it.

What each agent offers Coffer:

| Facet | Cursor | OpenCode | DeepSeek Harness |
| --- | --- | --- | --- |
| MCP entry | `~/.cursor/mcp.json`, `mcpServers` | `opencode.json`, `mcp` | `$DSH_HOME/cordis.patch.yml`, a `@deepseek-ai/dsh-mcp-client` row |
| Skills | reads `~/.agents/skills`, `~/.cursor/skills`, `~/.claude/skills`, `~/.codex/skills` | reads `~/.agents/skills`, `~/.config/opencode/skills`, `~/.claude/skills` | reads `~/.agents/skills`, `~/.dsh/skills` |
| Model connection | none: no custom endpoint | `provider` block with a base URL | `llm-pi-ai` providers, OpenAI or Anthropic protocol |
| Driver | `cursor-agent -p --output-format stream-json` | `opencode run --format json` | `dsh --profile headless --json` |
| Native memory | none on disk | none | none |

How comparable tools treat these agents: CC Switch, the most used multi-agent
manager, manages OpenCode's providers, MCP and `AGENTS.md`, and does not
support Cursor or DeepSeek Harness. Skill-sync tools (cross-agent-skill-sync)
link skills into Cursor and OpenCode through `~/.agents/skills`. None reads
these agents' sessions or memory.

## Options Considered

### Option A — Keep two agents (the design PR #309 left)

- Pro: every facet stays exercised on a real install; nothing new to maintain.
- Con: Coffer does not serve agents the owner now wants served, which is what
  Coffer is for.
- Why it loses: the owner asked for these agents. PR #309's objection was the
  missing regression signal, and that can be supplied another way (below).

### Option B — Add them with the MCP entry and skills only

- Pro: the two things every agent needs from Coffer, with the least code.
- Con: OpenCode and DeepSeek Harness could also take model connections and be
  driven from chat, channels and scheduled tasks; stopping at MCP leaves those
  out for no reason the agents impose.
- Why it loses: the owner asked for every feature each agent can take.

### Option C — Add them with every facet each one offers (chosen)

Each type is one descriptor record. A facet the agent offers is implemented;
a facet it lacks is absent (`None`), and the surfaces hide what an agent does
not have rather than showing a disabled control. The work lands in steps:
registration, detection, MCP entry and skills first; then model connections
(OpenCode, DeepSeek Harness); then drivers; then OpenCode sessions and Cursor
hooks.

To answer PR #309's objection, the regression signal comes from CI rather
than from the owner's Mac: a job installs each agent's real command line and
checks that it reads what Coffer wrote (`opencode mcp list`, `dsh --profile web
--dump-config`, `cursor-agent mcp list`).

- Pro: Coffer serves every agent the owner uses, as far as each agent allows.
- Con: three more config formats to keep correct as the agents change; the
  agents' surfaces move fast (OpenCode has a 1.x and a 2.x line side by side;
  DeepSeek Harness is a developer preview).
- Why it wins: it is what Coffer exists for, and the CI check removes the
  reason the earlier attempt was withdrawn.

## Decision

Option C. `AgentType` gains `cursor`, `opencode` and `deepseek_harness`. The
agent-registry spec no longer says a facet a type lacks is a reason not to add
the type: a type is added when it is in use and its facets can be exercised on
a real install, which a CI job may provide.

## Consequences

- Each new type has a child spec under `openspec/specs/agent-registry/`.
- Agent surfaces render from the facets an agent has; none names an agent type.
- The CI smoke job must keep passing against each agent's current release; when
  an agent changes its format, the job is where Coffer learns it.
- What an agent lacks is listed in the docs site's agent pages, so the person
  knows why a tab is not there.
