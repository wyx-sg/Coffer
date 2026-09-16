# One Shared Knowledge Store Across Agents

**Status**: Accepted
**Date**: 2026-06-09
**Deciders**: Yuxing Wu
**Related**: spec [knowledge](../../specs/knowledge/spec.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md) (the store's shape), [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md) (the same prohibition, applied to memory), [Everything Is a Resource Kind](everything-is-a-resource-kind.md), [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md)

This ADR owns exactly one question: **one store for every agent, or one store
per agent.** The store's layout, tool list and retrieval belong to
[Knowledge Is Plain Files](knowledge-is-plain-files.md) and are deliberately not
restated here, so that this file cannot drift from them.

## Context

The first memory design treated each store as a private silo queried over MCP.
In practice a developer runs more than one coding agent (Claude Code, Codex, …)
over the same project. Each agent has its own native memory location — Claude
Code's auto-memory directory, Codex's `memories`, and so on. The same project
fact ("we use squash-merge", "the API base URL is X") then gets written once per
agent and **drifts**: each copy is edited independently and the agents disagree
about the project.

Two forces shape the fix:

1. **A fact about a project is about the project, not about the agent.** It
   should exist once and be visible to every agent working in that project.
2. **Agents load native files ambiently, MCP tools deliberately.** Native files
   (an agent's memory dir, `CLAUDE.md`, `AGENTS.md`) are read into context
   automatically at session start; an MCP tool is only consulted when the agent
   chooses to call it. Whatever we build has to answer for that gap, or a shared
   store is strictly worse than what each agent already does for free.

## Decision

**Coffer holds one shared store, and every agent reads and writes it through
Coffer's own agent-agnostic tools. A fact is written once and is visible to
every agent authorised for it. Coffer keeps no per-agent copy, and does not
write into any agent's native memory files.**

What that commits to, independently of layout:

- **One resource kind, one storage root.** Not one store per agent, and not a
  per-agent view over a shared one. The framework's
  [per-agent scope](per-agent-resource-scope.md) decides which agent may reach a
  given collection; the store itself is undivided.
- **One tool surface, identical for every agent.** The `coffer__*` knowledge
  tools are agent-agnostic, so **adding a new agent adds no knowledge-layer code
  at all**. That property is the whole return on the decision, and the rejected
  alternatives cannot have it.
- **The caller does not classify.** With one kind and one set of tools, an agent
  never has to decide which store a fact belongs to before it can search for it.
- **Coffer never writes an agent's own memory files.** This is the load-bearing
  prohibition, and it is why retrieval from the shared store is deliberate
  rather than ambient.
  [Aggregate Agent Memory](aggregate-agent-memory-never-write-it.md) carries the
  same prohibition into the memory layer, where ownership runs the other way —
  the agents hold the canonical copy and Coffer derives from it read-only.

**What was tried instead, and why the prohibition exists.** This decision
originally projected the canonical store *outward* into each agent's native
location: a per-agent adapter with a `projection_mode` of
`SYMLINK | RENDER | NONE`, and each agent's own native memory switched off so
the canonical store stayed the only writer. All of it was removed in 2026-06-18
— writing and disabling another tool's configuration is intrusive and
illegible, and every supported agent owed a hand-maintained adapter tracking a
format that moves upstream. Two later attempts to recover its one real benefit,
ambient loading, were also removed: a session-start injection hook, which
shipped and was never installed on any machine, and the one-time inward import
of an agent's existing native memory, which shipped unused. So nothing pushes
knowledge into a session today, and an agent reaches the shared store only by
calling the tools itself.

## Consequences

**Positive**

- **One fact, every agent, no drift.** A fact is written once and every agent in
  scope reads the same file. The divergence problem is removed structurally — by
  there being one copy, not by keeping several in sync.
- **No per-agent knowledge code.** Onboarding a new agent costs nothing in this
  layer, in contrast to the per-agent adapter the removed mechanism required.
- **Clean layering.** Knowledge never authors an agent's config. The boundary
  the original mechanism maintained through an adapter is now maintained by
  simply not crossing it.

**Negative**

- **Retrieval is deliberate, not automatic.** An agent sees a fact only when it
  reaches for it. This is the full cost of not writing the agent's files, and it
  is accepted knowingly: the second force named in Context is unanswered, and
  both mechanisms that tried to answer it were removed for never having run.
- **Facts in an agent's own native store stay there.** They do not migrate on
  their own, and with the import removed there is no path to bring them across.
- **Coffer's tools are the only write path.** An agent that cannot speak MCP
  cannot contribute to the shared store.
- **What an agent wrote may later be rewritten.** The periodic tidy merges
  duplicates and rewrites notes unattended, on a timer. One shared store is what
  makes that worth doing — the duplicates it heals are the same fact written by
  several agents — but it means a note an agent wrote is not a fixed artefact.

## Alternatives Considered

**A silo per agent.** Rejected: it is the drift this ADR exists to remove.

**Native projection per agent.** Symlink where the format already matches, a
managed block where it does not, and disable the agent's own native memory so
copies cannot diverge. This is what was built first and then removed; the
Decision above says why, because that reasoning is now the prohibition.

**Render into each agent's own memory format, bidirectional.** Project the
canonical store *into* each agent's proprietary format and parse it *back* on
edit, so every agent edits natively and changes flow both ways. Rejected:
round-tripping a proprietary, evolving agent memory format losslessly is
industry-unsolved and inherently lossy.

**Fold knowledge into the agent-workspace config — let it write `CLAUDE.md`
directly.** Rejected on layering grounds: it collapses the config / knowledge
boundary. Knowledge stays agent-agnostic.

**Two faces over one substrate — a `memory` face and a `knowledge_base` face.**
This is how the store was actually built, and the facade was merged away in
2026-09-10. Rejected in retrospect: sharing a store across agents is the point,
and a second face over the same store only made callers guess which face a fact
belonged to.
