# A Skill's Tool Is Checked Against Each Agent That Gets the Skill

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Per-Agent Resource Scope](per-agent-resource-scope.md), [A Search Names the Server the Agent Is Not Reached By](a-search-that-finds-nothing-names-the-unreached-server.md), spec skill-manager "Declare the tools a skill requires"

## Context

A skill names the MCP servers and custom-tool groups it calls under `requires: tools:`. Coffer reported each as healthy, off or failing. That state belongs to the server alone. A skill delivered to Claude Code and Codex whose Grafana server reached only Codex read as healthy, and Claude Code found out when the skill's first call found no tool. A skill and a tool each carry their own reach, and nothing compared them.

The same gap between two skills was already closed: a skill that loads another skill which some of its agents do not get is under Needs attention as "Needs skill pdf · not on Codex".

## How comparable products answer

- **Agent Skills specification** (agentskills.io): `compatibility` "indicates environment requirements" and `allowed-tools` lists pre-approved tools. Neither is checked; the spec asks no client to verify a skill's tools are available.
- **Claude Code plugins**: a plugin ships its skills and its `mcpServers` together, so they are installed and enabled as one unit. Its `dependencies` field covers other plugins only; there is no check from a skill to a server.
- **Claude Code skills**: `allowed-tools` pre-approves tools for the turn. It does not check they exist.

So the products either bundle the two so they cannot drift (plugins) or do not check at all. Coffer cannot bundle: its servers are shared by many skills and reached per agent on purpose.

Sources: agentskills.io/specification, code.claude.com/docs/en/plugins-reference, code.claude.com/docs/en/skills (read 2026-11-13).

## Options Considered

### Option A — Report it, change nothing (chosen)

Each declared tool carries `missing_agent_names`: the agents the skill is delivered to that the tool's reach leaves out. A tool with any puts the skill under Needs attention ("Needs grafana · not on Claude Code", pill "Tool not shared") with a banner that opens the tool. Delivery and both reaches stay as the developer set them.

Pros: the mismatch is visible where the developer already looks, in the same words as the skill-to-skill case. Nothing is widened behind their back. Cons: it is a report; an agent can still be handed a skill it cannot fully run until the developer acts.

### Option B — Widen the tool's reach to match the skill

Makes the skill work at once. But a reach is the developer's gate on what an agent may call, and importing a skill would silently lift it.

### Option C — Do not deliver the skill to an agent that misses a tool

Keeps agents from half-working skills. But a skill often works without one of its tools, `requires` already never blocks delivery for a missing command, secret or switched-off tool, and a skill that vanishes from one agent is harder to explain than a line under Needs attention.

### Option D — Leave it to the call

The gateway already refuses the call, and a search now names the unreached server. That tells the agent, in the middle of a task. The developer, who can fix it, hears nothing until an agent complains.

## Decision

Option A. A declared tool is compared with the agents its skill is delivered to and the difference is reported. Coffer never changes a reach or a delivery because of a `requires:` entry. A tool that is off is reported as off only.

## Consequences

- The Requires state of a tool now depends on which skill is asking.
- Widening the tool's reach, or narrowing the skill's, clears the item on the next read.
- Enforced in `domain/skill/tool_state.py` (`ToolState.misses`) and `surfaces/http/skill_requires_view.py`; shown by `frontend/src/lib/skills/attention.ts`.
