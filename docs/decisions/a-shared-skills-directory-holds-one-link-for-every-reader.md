# A Shared Skills Directory Holds One Link for Every Agent That Reads It

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Codex Skills Go to `~/.agents/skills`](codex-skills-go-to-agents-skills.md), [Skills Reach an Agent as a Directory Link to One Master Folder](cross-platform-skill-delivery.md), [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), spec skill-manager "Deliver a skill as a directory link"

## Context

A skill reaches an agent as a link `<agent skills dir>/<skill>` to its master
folder, one binding row per (skill, agent), and a skill's scope says which
agents get it. Codex reads `~/.agents/skills`; so do Cursor, OpenCode and
DeepSeek Harness. Once more than one registered agent reads the same
directory, one path is wanted by several bindings.

If each binding were decided on its own, a skill scoped to Codex only would be
wanted for Codex and not for Cursor: the reconciler would create the link for
Codex and remove it for Cursor in the same pass, and the two would undo each
other every pass. And whatever the scope says, Cursor would still read the
link Codex's binding put there.

## Options Considered

### Option A — Decide each binding alone

- Pro: no new rule.
- Con: the flapping above; a scope that excludes one reader of a shared
  directory cannot be honoured, yet the surface would claim it is.

### Option B — Give each agent its own directory instead of the shared one

Cursor reads `~/.cursor/skills`, OpenCode `~/.config/opencode/skills`,
DeepSeek Harness `~/.dsh/skills`.

- Pro: per-agent scope works.
- Con: these agents read `~/.agents/skills` too, so a skill delivered to
  Codex's place is read by all of them anyway, and a skill delivered to both
  places shows twice and spends the agent's skill-description budget twice
  (the reason [Codex Skills Go to `~/.agents/skills`](codex-skills-go-to-agents-skills.md)
  rejected delivering to two places).

### Option C — One link per shared directory, wanted if any reader is in scope (chosen)

A skill is wanted in a directory when it is enabled and its scope reaches any
agent that reads the directory; then it is wanted for every reader, and each
reader's binding records the same link.

- Pro: one link, no flapping, and the bindings say truthfully which agents get
  the skill.
- Con: a skill cannot reach Codex without also reaching Cursor, OpenCode and
  DeepSeek Harness when they are registered. The surfaces say so ("also read
  by …") instead of offering a scope they cannot honour.

## Decision

Option C, in `application/skill/link_reconcile.py`: agents are grouped by
their resolved skills directory, and a skill in scope for one reader of a
directory is delivered for all of them.

## Consequences

- Removing one reader's binding (an agent removed) can remove a link another
  reader still wants; the next pass sees it missing and links it again.
- Unmanaged-skill discovery scans the shared directory and each agent's own
  directory (`domain/agent/scan.py`).
