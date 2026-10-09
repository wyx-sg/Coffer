# Tidying Knowledge Is the Agent's Job

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [Internal Engine Settings](internal-engine-settings.md), research note [knowledge curation](../research/knowledge-curation.md), spec knowledge "Teach writing and tidying in the guide", spec knowledge "Hand a tidy to the agent", spec knowledge "Promote submitted material at once"

## Context

Knowledge rots unless something tidies it. Documents repeat each other and
contradict each other, and a fact an agent wrote down lands beside the document
that already covers its subject. Tidying is judgement: where a fact belongs,
which two documents are about the same subject, which statement is stale.

Coffer used to make that judgement with its own model. A curation pass folded
new knowledge into a collection's documents, and a two-stage distil pass merged
the agents' memory entries into notes. Both ran on a timer through a separate
model connection the person had to configure. Three facts came out of running
that way:

- **Without a connection nothing was tidied.** Both passes degraded to a
  mechanical path when no connection was set, which is a first-run state. On the
  maintainer's machine 58 items had waited in the knowledge inbox since
  2026-09-28 with nothing curating them.
- **The model was the weaker one.** The person's own coding agent has file
  tools, a stronger model and a person watching it. Coffer's pass had a small
  fenced toolset and a cheaper model, and nobody saw it run.
- **Unattended rewriting of synced content needs its own safety machinery.**
  Two machines curating the same material produce the same knowledge twice at
  different paths, which git merges cleanly. Preventing that took an owner
  machine, a lock shared with the sync round, a per-pass write cap and an undo.

Memory is outside this decision. Coffer keeps no memory of its own to tidy: it
writes copies of what the person's agents learned into each agent's own
memory, and each agent curates those with its own built-in curation
([Sync Memory Into Each Agent's Own Memory](sync-memory-into-each-agents-own-memory.md)).

The agents already load the `coffer-guide` skill
([Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md)),
so there is a delivery channel for instructions that costs nothing extra.

## Options Considered

### Option A — The agent tidies on request; the person presses Tidy (chosen)

The `coffer-guide` skill teaches the judgement: how to write a fact straight
into the right document (six rules: find its home, lose nothing, organise by
subject, the newer statement wins unless the older one is shown right, never
name another knowledge file, give every document frontmatter) and how to tidy
a collection (merge, split, correct). A **Tidy** button on each collection,
and **Tidy all** on the Knowledge page, starts the default hand-off agent in
the person's preferred terminal with a prompt Coffer renders as its first
message, naming the path and the count. With no managed agent the button
offers Copy prompt only.

Coffer keeps only the mechanical work: knowledge submitted through an upload
or a channel becomes a document at once, and a file an agent drops into
`.inbox/` is adopted by the next sweep.

- **Pros.** The strongest model on the machine does the judgement, with file
  tools, while the person watches. Nothing needs a separate model connection.
  Coffer makes no model call over knowledge, so there is no unattended
  rewriter of synced content and no owner machine to name. The cost sits in
  the person's own agent session, started by the person.
- **Cons.** Documents duplicate until someone presses Tidy. An agent can tidy
  badly. That is bounded by the vault's git history: a tidy that went wrong is
  repaired by handing the restore of an earlier version to an agent from the
  document's **History…** dialog.
- **Why it wins.** The judgement belongs to the actor with the best model and
  the person's attention, and pressing a button is the consent that makes a
  prompt that edits Coffer's own files safe to send without asking again.

### Option B — Keep Coffer's own model passes

Curation and a model-driven distil run on timers through an internal default
connection.

- **Pros.** Tidying happens without anyone asking; the collection reorganises
  itself.
- **Cons.** A separate connection to configure, and a silent fallback when it is
  missing. A weaker model than the agent the person already pays for. An
  unattended rewriter of the only copy, with the bounds, owner machine and undo
  that implies. A LangChain and LangGraph dependency for one subsystem.
- **Why it lost.** It needed more machinery than the work deserved and, on the
  one real vault that used it, did not run.

### Option C — Scheduled agent runs

Start a managed agent on a timer to tidy.

- **Pros.** Unattended, with the stronger model.
- **Cons.** It spends the person's agent quota without their knowledge, leaves
  agent sessions nobody started, and has to be kept from looping through
  whatever fires inside every session it starts, such as the person's own
  agent hooks.
- **Why it lost.** Nothing the person did started it. A button keeps the person
  in control of when quota is spent and what appears in their session list.

### Option D — Tidy only as a prompt the person pastes

Offer the prompt and leave the sending to the person.

- **Pros.** No new automatic send.
- **Cons.** An extra step on every tidy, for a prompt that only edits Coffer's
  own recoverable files.
- **Why it lost.** It is the fallback when no managed agent exists, not the
  default.

### Option E — A tool the agent calls to tidy

Expose a `coffer__tidy` gateway tool that runs a model pass on the agent's
behalf.

- **Pros.** The agent can trigger it mid-task.
- **Cons.** The caller is the stronger reasoner, so delegating to a weaker model
  lowers quality, and a second model hop adds latency and cost. An earlier
  `coffer__ask` tool built on the same shape was called four times in thirty
  days and removed.
- **Why it lost.** The agent can already do the work itself with the guide.

## Decision

Tidying knowledge is the agent's job. The `coffer-guide` skill holds the
judgement; the person starts it with Tidy; nothing tidies unattended; and
Coffer runs no model of its own over knowledge. Tidy first integrates the
sources no page cites yet, and a report-only **Check with agent** hand-off sits
beside it; Coffer computes the mechanical findings (dead links, orphan pages,
waiting sources) itself, without judgement
([Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md)).
Rules a future change must respect:

- Coffer's mechanical passes (the knowledge sweep, the memory sync) merge or
  rewrite no content by meaning. Anything that needs to decide where a fact
  belongs or which statements agree is written into the guide, not into a pass.
- A tidy runs only when the person asks for it.
- The prompt is rendered by the backend like every hand-off, and the web UI
  only sends it.

## Consequences

- No Coffer-run model call remains except speech-to-text, which keeps its own
  connection and model ([Internal Engine Settings](internal-engine-settings.md)).
- No unattended pass rewrites synced content by meaning, so no owner machine is
  needed for one, and the knowledge sweep writes through the vault writer under
  the same lock as every other write.
- A person sees duplicates and the button instead of a pass that quietly did or
  did not run.
- Enforced by spec knowledge "Hand a tidy to the agent"; the guide text is
  `backend/coffer/application/knowledge/skill_assets/coffer-guide.md`.
