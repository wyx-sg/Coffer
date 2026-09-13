# Feature Specification: Memory

> 中文版: [spec.zh.md](./spec.zh.md)

**Created**: 2026-09-12
**Status**: Draft
**Folder name**: this spec lives at `specs/memory/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on.

**Input**: Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its rollouts into task groups and a profile. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows. Coffer **reads those native memories, without ever writing to them**, normalises them into one set of facts partitioned by project, organises that set, and hands each agent back what it does not know — a few hundred tokens at session start, the rest on request.

## The principle this layer answers to

**Coffer aggregates memory; it does not own it.** Every rule below follows from that. Coffer never writes an agent's native memory files, so no agent's own loop is disturbed and nothing has to be reconciled. Everything under `~/.coffer/memory/` is **derived** and may be deleted and rebuilt at any time, which is what makes it safe to organise aggressively. The single exception — the only non-derived state this layer holds — is the developer's own decisions about their memory, which are kept apart precisely so a rebuild cannot erase them.

## Memory is not knowledge

Spec [knowledge](../knowledge/spec.md) holds what the user or an agent **wrote down about the world**: a platform's API contract, a service's owner, an uploaded document. This layer holds what agents **learned while working**: the user's preferences, a project's decisions, a trap already hit. They are separate layers because they differ in every dimension that shapes a design.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | agents' native memories, read-only | the human uploads it, or writes it with an agent |
| Partitioned by | project (and `global`) | collection |
| Delivered by | **push** — a budgeted digest at session start | **pull** — the agent reaches for it |
| Can an entry be superseded | yes, and must be | no; it is updated |
| If the store is lost | rebuilt from the agents' own copies | gone |
| Organised by | rewriting a derived view, freely | rewriting the truth, conservatively, into `.history/` |

## What this does not repeat

Coffer has built two halves of a memory loop before and removed both. **Transcript distillation** (removed 2026-09-09) read session transcripts and wrote a journal; this layer does not read a transcript at all — Claude Code and Codex each already distil their own, far better than Coffer did, and this layer starts from their output. **Session-context injection** (removed 2026-09-10) was a working hook that had never once been installed on the maintainer's machine; delivery returns here with the failure addressed head-on: installation is an explicit act with a visible outcome, and the layer records whether injection actually happens (FR-055).

## User Scenarios & Testing

### User Story 1 — What one agent learns, the others know (Priority: P1)

In the morning Claude Code learns that this repository must be developed in a worktree. In the afternoon the developer opens Codex on the same repository, and it already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that fact at session start.

**Independent Test**: with both agents registered against fixture config directories, run a sync; confirm the fact extracted from Claude Code's memory appears in the context Coffer composes for Codex, and that Codex's own memory files are byte-identical to before.

### User Story 2 — Memory is filed by project, and by `global` (Priority: P1)

Facts about a repository belong to that repository; facts about the developer — how they like to be answered, what their machine's pip mirror does — belong everywhere. Coffer files each fact into the project it came from, or into `global` when it is about the person rather than a project.

**Independent Test**: aggregate a fixture holding one project-scoped fact and one preference; confirm the first lands in the project's partition and the second in `global`, and that a session opened in an unrelated directory receives the second and not the first.

### User Story 3 — The session opens with what matters, not with everything (Priority: P1)

A session starts with a few hundred tokens: who the developer is, what this project's memory holds, and how to ask for more. It does not start with two hundred facts. When the agent needs something it cannot name, it asks in its own words and gets the handful that bear on it.

**Independent Test**: compose the context for a partition holding more facts than the budget allows; confirm the payload stays within the stated bound and names how many facts were left out; then call recall and confirm the omitted fact is reachable.

### User Story 4 — Contradictions surface instead of accumulating (Priority: P2)

Two facts disagree — an older one recorded that a mechanism shipped, a newer one that it was removed. Coffer puts them side by side and marks the older superseded, rather than delivering both as if both were true.

**Independent Test**: aggregate two facts on one subject with opposite conclusions and different timestamps; confirm the pair is reported as a conflict and that the delivered digest carries the newer one.

### User Story 5 — The developer's judgement outlives the rebuild (Priority: P1)

The developer hides a fact that was never right, pins one that always matters, and settles a conflict by hand. Then the sources change and everything is recomputed — and their three decisions are still in force.

**Independent Test**: record an override of each kind, delete the entire memory tree, re-run aggregation, and confirm all three still apply to the regenerated facts.

### User Story 6 — Delivery is installed on purpose, and visibly (Priority: P1)

Session-start delivery requires touching an agent's own settings, so Coffer never does it silently. The developer installs it from Coffer, sees that it is installed, and — this being the thing that failed last time — sees when it last actually ran.

**Independent Test**: install into a fixture agent config, confirm the entry is marker-scoped and removable; confirm the surface reports installed state and the timestamp of the most recent injection, and reports "never fired" until one happens.

## Acceptance Scenarios

### Scenario: a Claude Code memory file becomes a normalised fact

### Scenario: a Codex task group becomes normalised facts partitioned by its cwd

### Scenario: the Codex profile becomes global facts

### Scenario: aggregation never modifies an agent's native memory files

### Scenario: an unchanged source file is skipped on the next sync

### Scenario: a fact keeps the agent, path and time it came from

### Scenario: a preference lands in global regardless of which project it came from

### Scenario: a project partition is named from its root, never from an opaque id

### Scenario: a partition is registered as a resource scoped to the agents it came from

### Scenario: the same fact learned by two agents is reported as one with two origins

### Scenario: two facts with opposite conclusions are reported as a conflict

### Scenario: organize regenerates the summary without an internal connection

### Scenario: deleting the memory tree and re-syncing reproduces the facts

### Scenario: a hidden fact stays hidden across a rebuild

### Scenario: a pinned fact stays pinned across a rebuild

### Scenario: a hand-settled conflict stays settled across a rebuild

### Scenario: the composed context stays within its token budget

### Scenario: the composed context says how many facts it left out

### Scenario: recall returns facts the digest omitted

### Scenario: recall falls back to literal matching with no internal connection

### Scenario: recall spans only the partitions the calling agent may see

### Scenario: a channel turn carries the memory context without a hook

### Scenario: hook installation is marker-scoped and removable

### Scenario: hook status reports never-fired until an injection happens

### Scenario: an agent whose native memory shape is unreadable degrades loudly

## Requirements

### Aggregation

- **FR-001**: Coffer MUST read the native memory of each **registered and enabled** agent, from a path derived from that agent's own `config_dir` (spec [agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.
- **FR-002**: Aggregation MUST be **read-only**. Coffer MUST NOT create, modify, move, delete or reformat any file in an agent's own memory, and MUST NOT disable or reconfigure an agent's native memory. This is [Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)'s prohibition, retained in full and now the load-bearing constraint of a different design.
- **FR-003**: Coffer MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output and adds no distillation of its own.
- **FR-004**: v1 MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the fact's name, description and type. **Codex**: its `MEMORY.md` task groups — each group's applicability, preferences, reusable knowledge and failures — and its distilled profile summary. Each reader MUST ignore the agent's own index or roll-up file, since Coffer regenerates that role itself.
- **FR-005**: A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing, the surface says so with the path and the reason, the other agent's aggregation still completes, and previously aggregated facts are left standing rather than deleted.
- **FR-006**: Aggregation MUST skip a source file whose content hash is unchanged since the last pass, and MUST record enough per source to make that decision without re-parsing.
- **FR-007**: Aggregation MUST run on a background worker on an interval and MUST be triggerable by hand. Unlike knowledge's tidy it MAY default to on, because it only reads the agents' files and only writes derived ones.

### Partitions

- **FR-010**: A **partition** is a top-level directory under `~/.coffer/memory/` and is one `memory` Resource. There MUST be exactly one partition per project plus one named `global`; no other partitioning axis exists.
- **FR-011**: A project partition MUST be named by a **readable slug** derived from its project root — never an opaque id. The absolute root MUST be recorded on the Resource and restated in the partition's own `README.md`, so the directory explains itself to a human browsing it. A name collision MUST be resolved by adding a distinguishing path segment, not by falling back to an id.
- **FR-012**: A fact MUST be filed into the partition of the project it was learned in, except that a fact **about the person rather than a project** — the user's own preferences and standing instructions — MUST be filed into `global` whichever project it came from. A source whose project root is the user's home directory MUST resolve to `global`.
- **FR-013**: Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.
- **FR-014**: A partition MUST support the Resource framework's per-agent scope. Its default scope on creation MUST be the set of agents it was aggregated from, so memory flows back to its sources without a setup step; the user MAY narrow or widen it afterwards. Scope MUST be enforced on every delivery and retrieval path.

### Facts

- **FR-020**: Each fact MUST be one Markdown file under its partition, carrying frontmatter with `title`, `description`, `type` (`user` | `feedback` | `project`), the origins it was seen in, `captured_at`, the source's own timestamp when it has one, and a status of `active` or `superseded`.
- **FR-021**: A fact's body MUST be the source's own words, not a paraphrase. Summarising happens in the derived digest (FR-031); the fact stays quotable back to its origin.
- **FR-022**: Every fact MUST carry an **origin key** that is stable across recomputation — derived from the contributing agent, the native file, and the fact's anchor within it — because it is what the developer's decisions are attached to (FR-040). Two agents contributing the same fact MUST produce one fact with two origins, not two facts.
- **FR-023**: The whole tree under `~/.coffer/memory/` MUST be derived: deleting it and re-running aggregation MUST reproduce it. It nonetheless MUST be included in export and backup (spec [vault-export-import](../vault-export-import/spec.md)), because its sources live outside the vault and would not survive the loss of the machine.

### Organise

- **FR-030**: After aggregation, an **organise** pass MUST run over each changed partition, driven by the internal connection: it merges duplicates across agents, marks a fact superseded when a later one contradicts it, flags a pair it cannot settle as a conflict, and writes the partition's digest.
- **FR-031**: Organise MAY rewrite the derived digest freely and MUST NOT archive prior revisions — knowledge's `.history/` exists because knowledge is the only copy, and memory is not. It MUST NOT edit a fact's body (FR-021) and MUST NOT delete a fact.
- **FR-032**: With no internal connection configured, organise MUST still produce a usable digest **mechanically** — facts grouped by type, newest first, one line each from their frontmatter — and simply contribute no merges, supersessions or conflict proposals. It MUST NOT be a no-op: an installation with no internal model still gets delivery.
- **FR-033**: A supersession or conflict that organise proposes MUST be recorded on the facts as the model's finding, distinguishable on every surface from one the developer settled (FR-041).

### The developer's decisions

- **FR-040**: The developer MUST be able to **hide** a fact, **pin** one, mark one **superseded by** another, and **settle** a conflict in favour of one side. These MUST be stored apart from the derived tree, keyed by origin key, in the one table this layer adds.
- **FR-041**: Overrides MUST be reapplied after every aggregation and organise pass, and MUST win over anything the model decided. Deleting the memory tree, or a partition being renamed, MUST NOT lose them.
- **FR-042**: A hidden fact MUST be absent from every delivery and every retrieval result while remaining visible — and reversible — on the management surface. A pinned fact MUST be preferred by the digest's budget (FR-051).

### Delivery

- **FR-050**: Delivery MUST have exactly three layers. **L0**, always: who the developer is, what this project's memory holds, and how to ask for more. **L1**, when it fits the budget: the partition's digest, one line per fact. **L2**, on request: `coffer__recall`.
- **FR-051**: The composed payload MUST be **bounded by an explicit token budget**, and when facts are left out it MUST say how many and how to reach them. Pinned facts, then `global` facts about the person, then the current project's most recent, MUST be preferred in that order.
- **FR-052**: `coffer__recall` MUST take a natural-language query, span only the partitions the calling agent's scope allows, and return the facts that bear on it with their origins. It MUST use the ranked retrieval of spec [knowledge](../knowledge/spec.md) FR-025..FR-029 — the same internal connection, the same disposable-sidecar rule — and MUST fall back to literal matching, never an error, when no internal connection is configured.
- **FR-053**: A **channel-driven turn** MUST receive L0 and L1 through the system-prompt append the turn platform already composes (spec [channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself.
- **FR-054**: For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI. Where the agent has a session-start event, delivery MUST use it. Where it has none — Codex, whose only hook events are `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` and `UserPromptSubmit` — delivery MUST use its earliest per-session event with a **once-per-session guard**, so the digest arrives once rather than on every prompt. Installation MUST be an **explicit act** on Coffer's surface, marker-scoped so it can be identified, removable without disturbing entries Coffer did not write, and idempotent. Coffer MUST NOT install it silently, and MUST NOT write into any file that is an agent's *memory* — a hook lives in the agent's settings, which is a different thing and is only ever written on the developer's instruction.
- **FR-055**: Coffer MUST report, per agent, whether delivery is installed and **when it last actually fired**, reporting never-fired until one does. This is the check the removed injection layer lacked: it shipped, was never installed, and nothing said so for two months.

### Surfaces

- **FR-060**: The MCP gateway MUST expose exactly one new built-in tool, `coffer__recall`. There MUST be no `remember` tool: this layer's facts are derived from agents' own memories, and an agent records something by recording it the way it already does.
- **FR-061**: A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and facts, show one fact with its origins and conflicts, run a sync, run an organise pass, compose the session context, apply and clear each override, and install/inspect/remove delivery for an agent.
- **FR-062**: The web UI MUST present partitions and their facts, surface conflicts as pairs to settle, expose the four overrides, show per-agent delivery state including last-fired, and read the audit log for this kind.
- **FR-063**: Every lifecycle act — aggregation, organise, each override, delivery installed or removed — MUST record an audit event with its actor. A recall MUST record the usual `mcp_invocations` row and nothing about its query or results.

### Constraints

- **FR-070**: This layer MUST add exactly **one** table, holding the developer's overrides. Facts, digests and partition metadata are files or existing Resource rows.
- **FR-071**: File content MUST leave the machine only through the internal connection the developer configured, for organise and for embedding, exactly as spec [knowledge](../knowledge/spec.md) allows — and not at all when none is configured.
- **FR-072**: Reading MUST be confined to the memory paths of registered agents' config directories. Every path built from a source's contents MUST pass a traversal guard.
- **FR-073**: This layer MUST NOT reintroduce transcript distillation, a journal lane, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.

## Success Criteria

- **SC-001**: A fact learned by one agent is present in the session context composed for a different agent, with no file in either agent's own memory having changed.
- **SC-002**: Deleting `~/.coffer/memory/` entirely and re-running a sync reproduces every fact, and every override the developer had recorded is still in force.
- **SC-003**: The session context stays inside its stated token budget on a partition with an order of magnitude more facts than the budget admits, and names what it omitted.
- **SC-004**: An installation with no internal connection configured still gets partitions, facts, a digest, delivery and recall — with merging, supersession and ranking absent rather than the feature absent.
- **SC-005**: The surface can answer, for each agent, whether delivery is installed and when it last fired.
- **SC-006**: A malformed or unrecognised native memory in one agent leaves the other agent's aggregation, and all previously aggregated facts, intact.

## Assumptions

- Each supported agent's native memory format is read at the shape it has today. A format change is expected to break the reader; FR-005 exists so that it breaks visibly and locally rather than silently emptying the store.
- Both supported agents distil their own memory well enough to be a good source. If one stops doing so, the answer is not for Coffer to start reading transcripts, but to reconsider that reader.
- The corpus stays in the hundreds of facts per partition, which is what makes an in-process ranking and a whole-digest organise pass affordable.
- A hook lives in an agent's settings file, not its memory; writing one on the developer's explicit instruction is a different act from projecting memory into an agent, which stays prohibited.
- Codex exposes no session-start event, so its guard keys on the agent process rather than on a session id it does not publish. That is a best-effort proxy: a guard that misfires costs a repeated digest, never a lost one, which is the right direction for the error to fall.
