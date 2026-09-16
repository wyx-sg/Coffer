# Feature Specification: Memory

**Status**: Accepted
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

Coffer has built two halves of a memory loop before and removed both. **Transcript distillation** (removed 2026-09-09) read session transcripts and wrote a journal; this layer does not read a transcript at all — Claude Code and Codex each already distil their own, far better than Coffer did, and this layer starts from their output. **Session-context injection** (removed 2026-09-10) was a working hook that had never once been installed on the maintainer's machine; delivery returns here with the failure addressed head-on: installation is an explicit act with a visible outcome, and every fire is recorded in the audit log, so "it is installed" and "it is running" are separately answerable (FR-055).

## User Scenarios & Testing

### User Story 1 — What one agent learns, the others know (Priority: P1)

In the morning Claude Code learns that this repository must be developed in a worktree. In the afternoon the developer opens Codex on the same repository, and it already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that fact at session start.

**Independent Test**: with both agents registered against fixture config directories, run a sync; confirm the fact extracted from Claude Code's memory appears in the context Coffer composes for Codex, and that Codex's own memory files are byte-identical to before.

### User Story 2 — Memory is filed by project, and by `global` (Priority: P1)

Facts about a repository belong to that repository; facts about the developer — how they like to be answered, what their machine's pip mirror does — belong everywhere. Coffer files each fact into the project it came from, or into `global` when it is about the person rather than a project.

**Independent Test**: aggregate a fixture holding one project-scoped fact and one preference; confirm the first lands in the project's partition and the second in `global`, and that a session opened in an unrelated directory receives the second and not the first.

### User Story 3 — The session opens with what matters, not with everything (Priority: P1)

A session starts with a few hundred tokens: who the developer is, what this project's memory holds, and how to ask for more. It does not start with two hundred facts. When the agent needs something the digest left out, it looks it up by a distinctive word or phrase and gets those facts back whole.

**Independent Test**: compose the context for a partition holding more facts than the budget allows; confirm the payload stays within the stated bound and names how many facts were left out; then call recall and confirm the omitted fact is reachable.

### User Story 4 — Contradictions surface instead of accumulating (Priority: P2)

Two facts disagree — an older one recorded that a mechanism shipped, a newer one that it was removed. Coffer puts them side by side and marks the older superseded, rather than delivering both as if both were true.

**Independent Test**: aggregate two facts on one subject with opposite conclusions and different timestamps; confirm the pair is reported as a conflict and that the delivered digest carries the newer one.

### User Story 5 — Delivery is installed on purpose, and visibly (Priority: P1)

Session-start delivery requires touching an agent's own settings, so Coffer never does it silently. The developer installs it from Coffer and sees, on that agent's own page, that it is installed. Whether it has actually fired — this being the thing that failed last time — is a separate question answered separately: every fire is an audit event, so the vault-wide audit surface can say when this agent's hook last ran, while the agent's page answers only installed or not (FR-055, FR-064).

**Independent Test**: install into a fixture agent config, confirm the entry is marker-scoped and removable, and confirm the per-agent status reports installation and carries no last-fired field; then serve one context with `record_fired` set and confirm one audit event names that agent.

## Acceptance Scenarios

### Scenario: a Claude Code memory file becomes a normalised fact

- **Given** a Claude Code per-project memory directory holding one fact file whose frontmatter carries `name`, `description` and `type`
- **When** the Claude Code reader lists its sources and reads that one
- **Then** exactly one fact comes back: its title is the `name`, its description the `description`, its type `feedback`, its body the prose with the frontmatter fence stripped out, its anchor the file's own stem, and its project root the project that memory directory belongs to
- **And** the agent's own roll-up file (`MEMORY.md`) is not among the sources at all, since Coffer regenerates that role itself

### Scenario: a Codex task group becomes normalised facts partitioned by its cwd

- **Given** Codex's `MEMORY.md` holding two task groups, one of which records the working directory it was learned in
- **When** the Codex reader reads that file
- **Then** one fact comes back per populated bullet section of each group — preferences typed `user`, reusable knowledge typed `project` — each carrying that group's recorded cwd as its project root, and each with an anchor prefixed by its group and section so one file of many facts yields many stable ones
- **And** the group's own rollout-reference subsections never surface as facts

### Scenario: the Codex profile becomes global facts

- **Given** Codex's distilled profile summary beside its `MEMORY.md`
- **When** the reader reads the summary
- **Then** the profile and the standing preferences in it come back as facts with an **empty** project root — which files them into `global` (FR-012) — and each typed `user`
- **And** Codex's own general-tips roll-up of what `MEMORY.md` already holds is not read as facts

### Scenario: aggregation never modifies an agent's native memory files

- **Given** fixture config directories for both supported agents, snapshotted byte-for-byte with their modification times
- **When** a full aggregation reads every source out of both
- **Then** facts are produced from both
- **And** every file under either config directory is byte-identical, with an unchanged modification time — Coffer created, moved, reformatted and deleted nothing (FR-002)

### Scenario: aggregation runs unattended, without anyone asking for it

- **Given** the aggregate worker configured with an interval, and nobody having asked for a pass
- **When** the daemon starts it
- **Then** a pass runs **immediately**, not after the first interval elapses — a daemon that has just started is when its picture of the agents is most stale
- **And** the audit actor on that pass is the worker's own, so the log can tell a scheduled pass from a requested one (FR-063)

### Scenario: an unchanged source file is skipped on the next sync

- **Given** a source already aggregated once, whose content hash has not changed since
- **When** a second pass runs
- **Then** the source is counted as skipped and is **not read at all** — a reader rigged to raise if consulted again is never consulted
- **And** no failure is reported and the facts that source produced are still on disk

### Scenario: a fact keeps the agent, path and time it came from

- **Given** both supported agents' real native memory in fixture config directories, each holding facts about the same project
- **When** aggregation runs
- **Then** that project's partition holds the facts from both, and their origins name both registered agents
- **And** every origin carries the absolute native path it was read out of and the time Coffer read it (FR-020)

### Scenario: a preference lands in global regardless of which project it came from

- **Given** a `user`-typed fact — a standing preference about the person — read out of one project's own memory directory
- **When** aggregation runs
- **Then** the only partition written is `global`, and the fact is in it
- **And** nothing lands in that project's partition (FR-012)

### Scenario: a project partition is named from its root, never from an opaque id

- **Given** a project-typed fact whose source records the absolute project root `/home/dev/coffer`
- **When** aggregation runs
- **Then** the partition is named `coffer` — the root's own directory name, readable to anyone browsing `~/.coffer/memory/` — and the fact is in it
- **And** a name collision is resolved by prefixing a parent path segment, never by falling back to an id (FR-011)

### Scenario: a partition is registered as a resource scoped to the agents it came from

- **Given** exactly one registered agent contributing one fact about a project
- **When** aggregation runs
- **Then** a `memory` Resource exists for that partition, its scope names exactly that one agent, and its config records the absolute project root
- **And** after the developer narrows the scope by hand, a later pass over a changed source leaves the scope alone (FR-014)

### Scenario: the same fact learned by two agents is reported as one with two origins

- **Given** both agents' native memory holding the same body of text about the same project, under different titles of their own
- **When** aggregation runs
- **Then** the partition holds **one** fact and one fact was written
- **And** its origins name both agents, so "which of my agents already knows this" is answerable (FR-022)

### Scenario: two facts with opposite conclusions are reported as a conflict

- **Given** two facts in one partition reaching opposite conclusions on one subject, and an internal connection whose answer flags the pair rather than choosing between them
- **When** the organise pass runs over that partition
- **Then** one conflict is reported and each fact names the other in its `conflicts_with`
- **And** neither body was edited and neither fact was deleted — the flag is the model's finding and stands until a later pass has grounds to withdraw it (FR-033). Where the model can order the pair instead, the older fact is marked superseded and carries the newer one's key

### Scenario: organize regenerates the summary without an internal connection

- **Given** a partition holding facts and **no** internal connection configured
- **When** the organise pass runs
- **Then** the partition's `summary.md` digest is written and names the facts, grouped mechanically from their frontmatter
- **And** the model is never called, no merge, supersession or conflict is proposed, and no fact is changed — an installation with no internal model still gets delivery (FR-032)

### Scenario: a second organise pass over the same partition is refused while the first is running

- **Given** a synced partition with an organise pass already in flight
- **When** a second pass over that same partition is requested
- **Then** it is **refused** with `UPKEEP_ALREADY_RUNNING` (409) rather than queued — the caller asked to start a pass, and no pass is going to start
- **And** the in-flight pass is readable on the shared upkeep-runs surface as `memory` on that partition, so a surface mounting mid-pass shows the pass instead of an idle button; once it finishes the runs list is empty again and the next request runs (FR-066)

### Scenario: deleting the memory tree and re-syncing reproduces the facts

- **Given** an aggregated partition whose directories are then deleted by hand, with the source-digest cache deliberately left behind
- **When** aggregation runs again
- **Then** the same facts come back, with the same titles in the same order
- **And** a digest match alone therefore never suppresses a rebuild: the whole tree is derived and disposable (FR-023, SC-002)

### Scenario: a partition's own directory is browsable as a file tree

- **Given** a synced partition
- **When** its file tree is requested, and then one file out of it
- **Then** the tree's root carries the partition directory's absolute path and holds a `README.md` naming the project root plus a `facts/` directory listing one Markdown file per fact; reading `facts/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **And** the family is read-only (a write is refused with 405) and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400), because the tree is derived and an edit would survive only until the next pass (FR-062, FR-072)

### Scenario: a partition does not travel to the sync remote

- **Given** a vault with a synced remote, holding a `memory` partition row and an ordinary resource of another kind
- **When** the vault is exported
- **Then** the other kind's document is written and the partition's is not — neither the derived tree nor the Resource row leaves this machine
- **And** a partition document an older build had already published is removed by the export, and one arriving in the working tree creates no row here, so the ghost cannot enter from either direction (FR-023)

### Scenario: the composed context stays within its token budget

- **Given** a partition holding an order of magnitude more facts than the budget admits
- **When** the session context is composed against an explicit token budget
- **Then** the payload's estimated token count is at or under that budget, and fewer facts are included than the partition holds
- **And** the budget is spent on `global` facts about the person first and then the project's most recent, so a trim drops the oldest rather than an arbitrary set (FR-051, SC-003)

### Scenario: the composed context says how many facts it left out

- **Given** a partition whose facts do not all fit the budget
- **When** the session context is composed
- **Then** the omitted count is greater than zero and that number appears in the text itself
- **And** the text names `coffer__recall` as the way to reach what was left out, and asks for a distinctive word or phrase rather than a question — the same thing the tool's own description says, so the first line of a session cannot contradict the tool it points at (FR-051, FR-060)

### Scenario: recall returns facts the digest omitted

- **Given** a partition of several dozen facts, one of them carrying a distinctive codeword, and a composed context too small to include it
- **When** `coffer__recall` is called with that codeword
- **Then** the omitted fact comes back **whole**, body and all, with its origins (FR-050 L2, FR-052)

### Scenario: recall matches a phrase in a fact's body

- **Given** a fact whose **body** — not its title and not its description — contains the phrase "unreachable internal mirror"
- **When** `coffer__recall` is called with that phrase
- **Then** the fact is returned
- **And** matching was a case-insensitive substring scan over the facts already in hand, with no score, no mode and no internal connection involved (FR-052)

### Scenario: recall spans only the partitions the calling agent may see

- **Given** two project partitions each holding a fact with the same codeword, scoped to two different agents
- **When** one of those agents recalls that codeword
- **Then** only its own partition's fact comes back
- **And** the other partition's fact is absent from the answer — scope is enforced on every retrieval path, not only on delivery (FR-014, FR-052)

### Scenario: a channel turn carries the memory context without a hook

- **Given** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **When** a turn is taken
- **Then** the digest arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **And** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (FR-053)

### Scenario: hook installation is marker-scoped and removable

- **Given** an agent whose settings file already carries a foreign hook on the same lifecycle event, other events' hooks, and unrelated top-level keys
- **When** delivery is installed, installed a second time, and then removed
- **Then** install adds exactly **one** entry carrying Coffer's marker, a second install leaves one entry, and every foreign hook, every other event and every unrelated key is untouched
- **And** remove takes out only the marked entry — dropping the event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (FR-054)

### Scenario: every hook fire is recorded in the audit log

- **Given** an agent for which delivery has been installed
- **When** the installed hook fires and the served context is recorded as a delivery
- **Then** exactly one audit event is written naming that agent as both the resource and the actor — nobody clicked anything, the agent whose session started is the actor
- **And** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own: "installed" and "has ever run" stay two separate facts read in two separate places (FR-055, FR-064)

### Scenario: an agent whose native memory shape is unreadable degrades loudly

- **Given** one agent holding a memory file whose frontmatter is missing, unterminated, not a mapping, or missing its name field, and a second agent whose memory is fine
- **When** aggregation runs
- **Then** the reader raises for the offending file with that file's own path, and the pass reports one failure naming the agent, the path and the reason
- **And** the other agent's facts are aggregated as normal, and facts from an earlier pass are left standing rather than deleted (FR-005, SC-006)

## Requirements

### Aggregation

- **FR-001**: Coffer MUST read the native memory of each **registered and enabled** agent, from a path derived from that agent's own `config_dir` (spec [agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.
- **FR-002**: Aggregation MUST be **read-only**. Coffer MUST NOT create, modify, move, delete or reformat any file in an agent's own memory, and MUST NOT disable or reconfigure an agent's native memory. This is [Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)'s prohibition, retained in full and now the load-bearing constraint of a different design.
- **FR-003**: Coffer MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output and adds no distillation of its own.
- **FR-004**: v1 MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the fact's name, description and type. **Codex**: its `MEMORY.md` task groups — each group's applicability, preferences, reusable knowledge and failures — and its distilled profile summary. Each reader MUST ignore the agent's own index or roll-up file, since Coffer regenerates that role itself.
- **FR-005**: A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing, the surface says so with the path and the reason, the other agent's aggregation still completes, and previously aggregated facts are left standing rather than deleted.
- **FR-006**: Aggregation MUST skip a source file whose content hash is unchanged since the last pass, and MUST record enough per source to make that decision without re-parsing.
- **FR-007**: Aggregation MUST run on a background worker on an interval and MUST be triggerable by hand. Unlike knowledge's tidy it MAY default to on, because it only reads the agents' files and only writes derived ones. Its switch and its interval MUST both be settable by the operator and MUST be read per pass rather than at boot, so a change takes effect without a daemon restart (spec [provider-switching](../provider-switching/spec.md) E3a).

### Partitions

- **FR-010**: A **partition** is a top-level directory under `~/.coffer/memory/` and is one `memory` Resource. There MUST be exactly one partition per project plus one named `global`; no other partitioning axis exists.
- **FR-011**: A project partition MUST be named by a **readable slug** derived from its project root — never an opaque id. The absolute root MUST be recorded on the Resource and restated in the partition's own `README.md`, so the directory explains itself to a human browsing it. A name collision MUST be resolved by adding a distinguishing path segment, not by falling back to an id.
- **FR-012**: A fact MUST be filed into the partition of the project it was learned in, except that a fact **about the person rather than a project** — the user's own preferences and standing instructions — MUST be filed into `global` whichever project it came from. A source whose project root is the user's home directory MUST resolve to `global`.
- **FR-013**: Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.
- **FR-014**: A partition MUST support the Resource framework's per-agent scope. Its default scope on creation MUST be the set of agents it was aggregated from, so memory flows back to its sources without a setup step; the user MAY narrow or widen it afterwards. Scope MUST be enforced on every delivery and retrieval path.

### Facts

- **FR-020**: Each fact MUST be one Markdown file under its partition, carrying frontmatter with `title`, `description`, `type` (`user` | `feedback` | `project`), the origins it was seen in, `captured_at`, the source's own timestamp when it has one, and a status of `active` or `superseded`.
- **FR-021**: A fact's body MUST be the source's own words, not a paraphrase. Summarising happens in the derived digest (FR-031); the fact stays quotable back to its origin.
- **FR-022**: Every fact MUST carry an **origin key** that is stable across recomputation — derived from the contributing agent, the native file, and the fact's anchor within it — because it is what two agents' contributions are matched on across recomputation. Two agents contributing the same fact MUST produce one fact with two origins, not two facts.
- **FR-023**: The whole tree under `~/.coffer/memory/` MUST be derived: deleting it and re-running aggregation MUST reproduce it. It MUST NOT converge with the sync remote (spec [vault-sync](../vault-sync/spec.md)): it is aggregated from the agents installed on *this* machine, so sending it to another would send facts that machine's own next pass would recompute away, and a machine that has never installed an agent would have that agent's partition appear and then vanish. **A partition's Resource row is covered by that prohibition too, not only the files.** The row is as derived as the tree is, and it is the half that produces the failure the sentence above describes: the tree stays home either way, so a row that travelled alone would land on the second machine as a partition naming a project root it may not have, with no facts behind it. The `memory` kind therefore declares `converges=False`, which is the one mechanism the sync layer reads — the exporter withholds such rows and the applier refuses such a document, so a machine still running an older build cannot deliver one either. Losing the machine loses the derived tree, and that is accepted: the sources it is derived from are the agents' own files, which the machine that has them can always recompute from.

### Organise

- **FR-030**: After aggregation, an **organise** pass MUST run over each changed partition, driven by the internal connection: it merges duplicates across agents, marks a fact superseded when a later one contradicts it, flags a pair it cannot settle as a conflict, and writes the partition's digest.
- **FR-031**: Organise MAY rewrite the derived digest freely and MUST NOT archive prior revisions — knowledge's `.history/` exists because knowledge is the only copy, and memory is not. It MUST NOT edit a fact's body (FR-021) and MUST NOT delete a fact. The `summary.md` it writes is read by the **developer**, browsing the partition as a folder (FR-062); delivery does not read the file, because it composes L1 against a budget and a partition may legitimately have no digest yet. Sharing the renderer rather than the file is what keeps the two honest (FR-050).
- **FR-032**: With no internal connection configured, organise MUST still produce a usable digest **mechanically** — facts grouped by type, newest first, one line each from their frontmatter — and simply contribute no merges, supersessions or conflict proposals. It MUST NOT be a no-op: an installation with no internal model still gets delivery.
- **FR-033**: A supersession or conflict that organise proposes MUST be recorded on the facts themselves, as the model's finding. Nothing settles it by hand: a conflict is shown because two facts disagree, and the next pass over changed sources is what resolves it.

### Delivery

- **FR-050**: Delivery MUST have exactly three layers. **L0**, always: who the developer is, what this project's memory holds, and how to ask for more. **L1**, when it fits the budget: the partition's digest, one line per fact. **L2**, on request: `coffer__recall`. "The partition's digest" MUST be meant literally: a delivered fact line and a line of `summary.md` are rendered by **one** function, and the two surfaces sort by one definition of "newest". They were two, and drifted — the file said `- **title** — description` while delivery said `- title: description`, and a fact timestamped only at its source sorted correctly in the file and last in the delivery.
- **FR-051**: The composed payload MUST be **bounded by an explicit token budget**, and when facts are left out it MUST say how many and how to reach them. How to reach them MUST agree with what recall can answer: the line asks for a **distinctive word or phrase**, never for a question, because matching is a literal substring scan (FR-052) and this line is the first thing an agent reads every session. `global` facts about the person, then the current project's most recent, MUST be preferred in that order.
- **FR-052**: `coffer__recall` MUST take a word or phrase, span only the partitions the calling agent's scope allows, and return the matching facts **whole**, with their origins. Matching MUST be memory's own **case-insensitive substring scan** over the facts already in hand — a fact's body first, and failing that its title and description — with no score, no mode and no reason in the answer. It MUST need no internal connection at all: recall used to borrow spec [knowledge](../knowledge/spec.md)'s ranked retrieval, and that engine was deliberately removed along with every other use of embeddings in Coffer, so there is nothing left for recall to borrow and nothing for it to degrade from. The scan stays memory's own rather than reaching for knowledge's ripgrep, because at the corpus size this layer assumes the facts are already loaded.
- **FR-053**: A **channel-driven turn** MUST receive L0 and L1 through the system-prompt append the turn platform already composes (spec [channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself.
- **FR-054**: For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI. Where the agent has a session-start event, delivery MUST use it. Where it has none — Codex, whose only hook events are `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` and `UserPromptSubmit` — delivery MUST use its earliest per-session event with a **once-per-session guard**, so the digest arrives once rather than on every prompt. Installation MUST be an **explicit act** on Coffer's surface, marker-scoped so it can be identified, removable without disturbing entries Coffer did not write, and idempotent. Coffer MUST NOT install it silently, and MUST NOT write into any file that is an agent's *memory* — a hook lives in the agent's settings, which is a different thing and is only ever written on the developer's instruction.
- **FR-055**: Coffer MUST record **an audit event for every delivery fire**, so that whether injection is actually happening is answerable after the fact. This is the check the removed injection layer lacked: it shipped, was never installed, and nothing said so for two months. A fire is an event, not a property of the agent: the per-agent delivery status MUST report installation only, and MUST NOT carry a last-fired timestamp or warn about the absence of one — a hook installed a minute ago has legitimately never fired, and a surface that flags that is crying wolf on its own normal state.

### Surfaces

- **FR-060**: The MCP gateway MUST expose exactly one new built-in tool, `coffer__recall`, and its description MUST tell the caller that matching is literal, so an agent gives it a distinctive word or phrase rather than a whole question. There MUST be no `remember` tool: this layer's facts are derived from agents' own memories, and an agent records something by recording it the way it already does.
- **FR-061**: A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and facts, show one fact with its origins and conflicts, browse a partition's own directory and read one file from it, run a sync, run an organise pass, compose the session context, and install/inspect/remove delivery for an agent.
- **FR-062**: The web UI MUST present partitions **as a table**, in the same shape whether or not any exist — an installation with no partitions yet MUST get that table's own empty row and a reachable sync, not a different page. One partition MUST be presented as a **file tree over its own directory** with a read-only preview beside it — the same two panes a skill's Files tab is — and MUST offer open-in-editor and reveal-in-file-manager on the previewed file. It MUST NOT carry per-fact actions: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one.
- **FR-064**: Per-agent delivery state MUST be presented on **that agent's own detail page**, not on the partitions surface. Delivery writes one agent's settings file, so it is per-agent state; a surface that is already scoped to an agent MUST NOT make the reader pick one again. That surface answers one question — installed or not; firing is read as events on the audit surface (FR-055, FR-065).
- **FR-065**: This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, which every kind shares; a kind-scoped second copy is a duplicate surface, and every event type this layer records MUST therefore be legible there rather than shown as a raw event code.
- **FR-063**: Every lifecycle act — aggregation, organise, delivery installed, removed or fired — MUST record an audit event with its actor. A recall MUST record the usual `mcp_invocations` row and nothing about its query or results.
- **FR-066**: Only **one organise pass per partition** may run at a time, whoever started it. The pass runs for minutes and rewrites the partition's whole directory, so a second pass over the same partition is not a faster organise but two writers over one directory. A manual trigger that arrives while a pass is in flight MUST be **refused** rather than queued (`UPKEEP_ALREADY_RUNNING`, 409) — the caller asked to start a pass, and no pass is going to start — and the interval worker MUST **skip** a partition that is already being organised rather than wait behind it, since its next sweep comes round again anyway. Which partitions are being rewritten right now MUST be readable, so a surface that opens mid-pass shows the pass instead of an idle button that invites the second click. The record is per-daemon and does not outlive it: a pass lives in the process that was asked for it, so a restart ends it and the reading comes back empty, which is the truth rather than a lost record.

### Constraints

- **FR-070**: This layer MUST add **no table of its own**. Facts, digests and partition metadata are files or existing Resource rows, and nothing else about a partition is worth keeping anywhere but in the partition.
- **FR-071**: File content MUST leave the machine only through the internal connection the developer configured, and only for the organise pass (FR-030) — exactly as spec [knowledge](../knowledge/spec.md) allows, and not at all when none is configured. Recall MUST send nothing anywhere: it reads no further than the facts on disk.
- **FR-072**: Reading MUST be confined to the memory paths of registered agents' config directories. Every path built from a source's contents MUST pass a traversal guard.
- **FR-073**: This layer MUST NOT reintroduce transcript distillation, a journal lane, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.

## Success Criteria

- **SC-001**: A fact learned by one agent is present in the session context composed for a different agent, with no file in either agent's own memory having changed.
- **SC-002**: Deleting `~/.coffer/memory/` entirely and re-running a sync reproduces every fact.
- **SC-003**: The session context stays inside its stated token budget on a partition with an order of magnitude more facts than the budget admits, and names what it omitted.
- **SC-004**: An installation with no internal connection configured still gets partitions, facts, a digest, delivery and recall — with merging and supersession absent rather than the feature absent. Recall is unaffected either way: it never needed a connection.
- **SC-005**: The surface can answer, for each agent, whether delivery is installed; and the audit surface can answer when that agent's hook last fired.
- **SC-006**: A malformed or unrecognised native memory in one agent leaves the other agent's aggregation, and all previously aggregated facts, intact.

## Assumptions

- Each supported agent's native memory format is read at the shape it has today. A format change is expected to break the reader; FR-005 exists so that it breaks visibly and locally rather than silently emptying the store.
- Both supported agents distil their own memory well enough to be a good source. If one stops doing so, the answer is not for Coffer to start reading transcripts, but to reconsider that reader.
- The corpus stays in the hundreds of facts per partition, which is what makes a scan over every fact in hand and a whole-digest organise pass affordable.
- A hook lives in an agent's settings file, not its memory; writing one on the developer's explicit instruction is a different act from projecting memory into an agent, which stays prohibited.
- Codex exposes no session-start event, so its guard keys on the agent process rather than on a session id it does not publish. That is a best-effort proxy: a guard that misfires costs a repeated digest, never a lost one, which is the right direction for the error to fall.
