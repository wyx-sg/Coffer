# Feature Specification: Workflow

**Spec**: `workflow`
**Status**: Draft

## The principle this layer answers to

Coffer already holds everything an agent needs to do a piece of work: the agents themselves, the skills that say how a job is done, the knowledge and memory that say what is already known, and the gateway that reaches the outside world. What Coffer has never held is **the shape of the work** — that a delivery goes from a requirement to a design to code to a test to a release, that each step owes a deliverable, and that some steps must not happen without the developer saying so.

This layer adds that shape and nothing else. It introduces no second way to run an agent: every task in a run is one ordinary Coffer conversation, driven by the turn platform the channels already use, and a run is the arrangement of those conversations rather than a conversation of its own. It introduces no second place to keep files: artifacts are plain files, the way knowledge is. It introduces no second notification path: an approval reaches the developer through a channel that already exists.

## A node is a conversation, and that is where everything happens

A stage holds one or more **nodes**, and each node is one conversation. The node opens with its bound skill already driving it, so the ordinary case is that it does its work without being told how; the developer opens the conversation when they want to steer it, and says so in ordinary words. Unplanned work is a task added to a stage and is a conversation like any other.

That has a consequence the rest of this document leans on: **everything the developer does, they do inside a conversation.** The run's own page is a map — where the delivery is, what it has produced, what it is reading — and carries no controls. Retry, skip, redirect, correct: all of it is said in the node's conversation, where the thing being decided is in front of them. The single exception is an approval's Approve / Reject, which is a decision about an exact payload and cannot honestly be made by typing "ok".

## What this layer is not

It is not a CI system — it never builds or tests on its own; a node asks an agent to, and the agent runs the repository's own commands. It is not a project tracker — Jira stays Jira, and a node writes to it through the gateway like any other external system. It is not a second agent runtime.

## The one position this layer reverses

Coffer does not gate individual tool calls today, and that is a considered position: the paired owner driving a conversation is the trust boundary, so an agent in a chat runs with the owner watching. A workflow run has no one watching — it advances in the background, possibly overnight. The trust boundary that holds for a chat does not hold here, so this layer introduces a gate on write-class tool calls made on behalf of a run, and only on behalf of a run. A conversation that is not a workflow node is untouched. See [Workflow Gates Tool Calls](../../docs/decisions/workflow-gates-tool-calls.md).

## User Scenarios *(mandatory)*

### User Story 1 - A delivery advances on its own (Priority: P1)

The developer points a template at a repository and a requirement, and the run advances through its stages without being nursed: each node opens its own conversation with an agent, does its work, leaves its deliverable behind, and hands the run to the next node.

**Why this priority**: This is the feature. Without it the layer is a board with no engine.

**Independent Test**: Create a run from a two-stage template, start it, and watch both nodes complete and the run reach `completed` without any command between `start` and the end.

**Covered by**: "a run advances from one node to the next without prompting", "a node's work happens in its own conversation", "a run reaches completed when its last node does"

---

### User Story 2 - The developer redirects a run in plain language (Priority: P1)

Halfway through, the requirement changes. The developer opens the task that is running, says so in its conversation — in ordinary words, not through a form — and every task that opens afterwards knows, because a task opens with what the earlier ones said.

**Why this priority**: A delivery that cannot be redirected mid-flight is a delivery the developer will abandon and do by hand.

**Independent Test**: Say something in one task's conversation, then start the next task and assert its opening context carries it.

**Covered by**: "a task is its own conversation, opened from the run", "a later task opens with what the earlier ones said", "the run's own page offers no controls"

---

### User Story 3 - Nothing reaches the outside world unapproved (Priority: P1)

A node wants to publish a design, file a ticket, push a branch, or deploy. Each of those stops at an approval the developer decides, with the exact payload in front of them. Until they decide, the write does not happen — not because the node was asked nicely, but because the gateway will not carry it.

**Why this priority**: An unattended run with unrestricted write access to Jira, GitLab and the deploy platform is the single way this layer can do real damage.

**Independent Test**: Run a node that calls a write-class tool with no approval in place, and assert the call is refused; approve, and assert the same call goes through once.

**Covered by**: "a write-class tool call without an approval is refused", "an approved call goes through exactly once", "an unknown tool is treated as write-class", "an approval decision is idempotent", "an expired approval does not authorise a write"

---

### User Story 4 - The shape of the work is the developer's to define (Priority: P1)

A three-stage flow for a small change, an eight-stage flow for a release train, stages named whatever the team calls them. The developer writes the template; Coffer attaches no meaning of its own to any stage.

**Why this priority**: A hard-coded delivery flow fits one team and no other, and would put one company's process into a general tool.

**Independent Test**: Register a template with three stages named by the user, create a run from it, and assert the run's stages are exactly those three in that order.

**Covered by**: "a template is registered as a resource", "a template with any number of stages runs as written", "an invalid template is refused with the offending path", "editing a template leaves a running run alone"

---

### User Story 5 - The developer authors the flow in the app (Priority: P1)

The shape of the work is the developer's, so they must be able to write it without leaving Coffer and without writing JSON: add a stage, name it, put nodes in it, pick the skill each node runs, say what it owes and whether it needs approval, and draw the edge that sends testing back to coding.

**Why this priority**: A flow that can only be authored by hand-editing a file is a flow that will be authored once and never adjusted, which defeats the point of the template being data.

**Independent Test**: Author a two-stage template through the UI, save it, create a run from it, and assert the run's stages are what was authored.

**Covered by**: "a template is authored in the app", "an invalid template is refused against the field that is wrong"

---

### User Story 6 - Unplanned work joins the run without leaving it (Priority: P2)

Something comes up that the template never anticipated. The developer adds a task to whichever stage it belongs to, writes the prompt themselves, and it runs with the same context and leaves its deliverable in the same place as every planned node.

**Why this priority**: Every real delivery has work no template predicted; if that work has to happen outside the run, the run's record stops being true.

**Independent Test**: Add an ad-hoc task to a stage of a running run and assert it opens with the same shared context and its artifacts are attributed to it like any node's.

**Covered by**: "an ad-hoc task joins a stage and carries the same context"

---

### User Story 7 - The run reads what the developer gives it (Priority: P1)

A delivery starts from things that already exist: a PRD, a ticket, a design doc, a file someone sent. The developer mounts them on the run — a knowledge collection, an uploaded file, a link — and every node opens knowing they are there. They can add one at any point, not only when the run is created.

**Why this priority**: A run that can only read what it produced itself starts every delivery from nothing.

**Independent Test**: Create a run — giving only a template and a title — then upload a file and add a link to it, start a node, and assert both appear in its opening context.

**Covered by**: "a run is created from a template and a title alone", "an uploaded file becomes an input the nodes can read", "an input can be added and removed while the run is going", "a mounted repository gives the run its own checkout"

---

### User Story 8 - A long delivery still fits (Priority: P2)

Some nodes run for hours and some deliveries run for weeks. Neither one conversation nor the run's accumulated history may grow until a node cannot open.

**Why this priority**: Unbounded context is not a degraded experience, it is a broken one: the node fails to start at all.

**Independent Test**: Build a run whose earlier tasks exceed the context budget, open the next node, and assert its context is within budget and says what it summarised.

**Covered by**: "earlier tasks are summarised when they exceed the budget", "a long conversation is compacted rather than truncated"

---

### User Story 9 - A run survives a restart and says what it lost (Priority: P2)

The daemon restarts. The run comes back exactly as it was, except the node that was mid-turn, which is reported as interrupted rather than quietly resumed or quietly dropped — and its conversation is still readable.

**Why this priority**: An engine that lies about what it lost is worse than one that loses nothing.

**Independent Test**: Kill the daemon mid-turn, restart, and assert the run's projection matches its events and the in-flight node is `failed` with an `interrupted` reason and an intact conversation.

**Covered by**: "a run rebuilds itself from its events", "an interrupted node is reported, not resumed"

---

### Edge Cases

- Two clients submit a command against the same run with the same observed version.
- A feedback edge points back into a stage that has already completed.
- A node declares an artifact as required and the agent never writes it.
- An approval is decided twice, or decided after it expired.
- The agent calls a write-class tool the vault has never seen.
- A run's working directory is deleted while the run is paused.
- A run is opened on a machine that is not the one advancing it.
- A feedback edge and a retry ceiling interact: testing keeps sending work back to coding.
- An uploaded input is larger than the context budget on its own.

## Requirements *(mandatory)*

### The template

- **FR-001**: The system MUST register a workflow template as a resource of kind `workflow`, identified `workflow:<name>`, taking the framework's lifecycle, audit, schema validation and sync.
- **FR-002**: A template MUST carry an ordered list of one or more stages, each with a key and a display name chosen by the user.
- **FR-003**: The system MUST attach no behaviour to any stage key — a stage's meaning is its position in the template and nothing else.
- **FR-004**: A stage MUST carry an ordered list of nodes; a node names its type, an optional skill to run, optional additional instructions, the artifacts it owes, its approval policy, its failure behaviour and optionally the agent it runs on.
- **FR-067**: A node's type MUST name who does the work and nothing else: an agent, or a person. The system MUST NOT carry a type that only describes what the work is ABOUT — a task's name and its instructions say that — and MUST NOT carry a type whose executor it cannot actually run.
- **FR-005**: A template MUST support feedback edges — an edge from a later stage back to an earlier one, carrying the reason that takes it.
- **FR-006**: The system MUST validate a template on write and refuse an invalid one naming the offending path, never storing a template that would stall a run.
- **FR-007**: A template's scope MUST be read inverted, as the agents this template may drive; a node naming an agent outside that scope MUST be refused at validation.
- **FR-008**: A template MUST travel with vault sync, so a flow defined on one machine is available on the developer's others.
- **FR-009**: The system MUST seed exactly one built-in template, which the developer may edit or delete like any other.
- **FR-010**: Creating a run MUST freeze a snapshot of its template; later edits to that template MUST NOT affect a run already created.

### The run

- **FR-011**: A run MUST be created from a template and a title, and MUST NOT be a resource — it is operational state, not a curated asset. Creating one MUST ask for nothing else: a working directory and inputs are not part of it.
- **FR-053**: The system MUST create and own a working directory per run, under that run's own directory, and every node's conversation MUST run in it. The developer MUST NOT be asked for one and MUST NOT be able to set one.
- **FR-012**: A run MUST record the machine that owns it; only that machine's daemon MUST advance it, and another machine MUST show it read-only.
- **FR-013**: A run MUST have exactly the statuses `draft`, `running`, `paused`, `completed`, `aborted` and `failed`. "Waiting for the developer" is a property of a node, never of a run.
- **FR-014**: A run's append-only event log MUST be its record of truth, and the run's current stage, node and status MUST be a projection rebuilt from those events on start.
- **FR-015**: Every mutating command MUST carry the caller's observed version, and a stale version MUST be refused with the run's current version and position rather than applied.
- **FR-016**: The system MUST support the run signals `start`, `pause`, `resume` and `abort`; an aborted run MUST refuse every later mutating command.
- **FR-017**: At most one node of a run MUST be running at any moment.

### Nodes

- **FR-019**: A node's work MUST be one conversation on the turn platform, with the run's working directory as the conversation's working directory.
- **FR-020**: A node MUST have exactly the statuses `pending`, `running`, `waiting_review`, `waiting_approval`, `completed`, `skipped` and `failed`.
- **FR-021**: The system MUST support the node actions `start`, `feedback`, `complete`, `retry`, `skip` and `restore`.
- **FR-022**: A retry MUST append a new attempt; an attempt's conversation, output and feedback MUST survive it.
- **FR-023**: A node that owes a required artifact and has not produced it MUST NOT complete; it MUST wait for the developer to supply it or waive it.
- **FR-024**: A node failure MUST be handled by the node's declared failure behaviour: stop the run, continue to the next node, or retry up to a stated number of times.
- **FR-025**: Taking a feedback edge MUST add a new task to the target stage carrying what was found, and MUST NOT reopen, retry or reset any node that already ran.
- **FR-026**: Every task MUST declare how many attempts it may open, and every route that sends work back MUST declare how many times it may fire; reaching either MUST fail the run with the reason rather than loop. The limit MUST belong to the task and the route rather than to the workflow as a whole — a draft that is cheap to redo and a deploy that must not be tried twice are not the same judgement — and a task that names no limit MUST be given a default rather than an unbounded one.
- **FR-027**: A node whose turn was interrupted by a daemon restart MUST be reported as failed with an `interrupted` reason, with its conversation preserved and readable.
- **FR-028**: The developer MUST be able to add an ad-hoc task to any stage of a run at any time, writing its instructions themselves; it MUST be recorded, contextualised and attributed exactly as a template node is.

### Shared context

- **FR-029**: Every node MUST open with the same shared context: its own brief, its bound skill's instructions, the transcripts of the run's earlier tasks, the artifact catalogue, and the run's mounted inputs.
- **FR-030**: A run MUST NOT have a conversation of its own. Every conversation in a run belongs to one task, the developer speaks to a task inside it, and what they say reaches the rest of the run by being part of the transcript the next task opens with.
- **FR-031**: The artifact catalogue MUST be generated from what is on disk, never hand-maintained, and MUST name the node and attempt that produced each artifact.
- **FR-032**: A run's mounted inputs MUST be able to include knowledge collections, uploaded files, notes the developer wrote, external references and local repositories, and MUST be listed to every node rather than inlined wholesale.
- **FR-057**: Mounting a repository input MUST give the run its own checkout of it inside the run's working directory. When the path is a git repository the system MUST create a git worktree on a branch of the run's own; otherwise it MUST link the directory in and say that it did. A run MUST NOT be pointed at the developer's working checkout in a way that lets it write there, because a run advances unattended and the developer's uncommitted work is not its to touch.
- **FR-058**: Unmounting a repository input MUST remove what the run was given and MUST leave the source repository, its branches and its working tree untouched.
- **FR-047**: The system MUST keep a node's opening context within a stated token budget, and MUST say in the context itself what it summarised rather than silently dropping it.
- **FR-048**: When the earlier tasks' transcripts exceed their share of that budget, the system MUST summarise the oldest of them rather than truncate them.
- **FR-049**: When one node's own conversation exceeds its share, the system MUST compact its oldest turns into a summary that stays in the conversation.

### Inputs

- **FR-050**: The developer MUST be able to add and remove a run's inputs at any point in its life, not only when it is created.
- **FR-051**: An uploaded input MUST be stored under the run's own directory and MUST be readable by the agent from the working directory it runs in.

### Approvals and the tool gate

- **FR-033**: A node action whose approval policy requires it MUST create an approval carrying the exact payload that will be executed, and MUST NOT execute before a decision.
- **FR-034**: The gateway MUST refuse a write-class upstream tool call made on behalf of a run that has no approved, unexpired approval for it.
- **FR-035**: The system MUST make a run's identity available to the gateway at the point a tool call is dispatched, so a call can be attributed to the run and node that caused it.
- **FR-036**: A tool the vault has no write-class judgement for MUST be treated as write-class, and the developer's answer MUST be remembered so the same tool is not asked about twice.
- **FR-037**: A held tool call MUST resume once approved, MUST fail with an explicit reason once its approval expires or is rejected, and MUST NOT be silently dropped.
- **FR-038**: An approval decision MUST be idempotent — a repeated decision MUST return the same terminal state and MUST NOT cause a second execution.
- **FR-039**: An approval MUST be shown on the conversation of the task that raised it — where the developer is already reading what led to it — and MUST also be delivered through a channel when one is bound.
- **FR-040**: The system MUST record an audit event for every template lifecycle change, run state change, approval decision and gated tool call.

### Artifacts

- **FR-041**: A node's artifacts MUST be files under the run's own directory, attributed to the node and attempt that wrote them.
- **FR-042**: A run's directory MUST NOT be indexed, chunked or embedded — the files are the only copy.
- **FR-043**: What a run is MADE OF MUST be promotable into a knowledge collection in one action, so a delivery's output becomes the next delivery's input. Its artifacts, its uploaded files and its notes MUST travel as files; the links, collections and repositories it read MUST travel as one written record of having been read, because those are not the run's bytes to copy. It MUST NOT wait for the run to produce anything: a delivery that has so far only been given a brief is one whose brief is worth keeping.

### Surfaces

- **FR-044**: The system MUST expose templates, runs, nodes, approvals and events over the REST API.
- **FR-045**: The web UI MUST list runs; show a run's stages and its tasks with their status; show what the run reads and what it has produced together in one list; open any task as its own conversation page; and let the developer decide that task's approvals from that page.
- **FR-046**: The CLI MUST create, list, inspect, signal and abort runs, manage a run's inputs, act on a node, and decide approvals.
- **FR-054**: The web UI MUST let the developer author a template: list templates, create one, and edit its stages and their order, the nodes in each stage and their order, each node's type, bound skill, instructions, declared artifacts, approval policy, failure behaviour, agent and attempt ceiling, and the routes that send work back between stages with each route's own ceiling. The workflow's name and description MUST be editable in place, on the workflow's own page, rather than only at creation.
- **FR-055**: A refusal from template validation MUST be shown against the field it names rather than as a whole-form error, since the refusal already carries the offending path (FR-006).
- **FR-056**: The template editor MUST write through the same resource endpoint every other client uses; it MUST NOT have a write path of its own.
- **FR-052**: The run's own page MUST offer no controls that advance or alter the run. Every such action belongs to the node's conversation page, where what is being decided is in front of the developer.
- **FR-059**: Templates and runs MUST be separate surfaces in the web UI: a template is a resource and MUST be reached where the other resource kinds are, and a run is operational state and MUST NOT be. Neither may be reachable only through the other.
- **FR-060**: The template editor MUST NOT ask the developer for a stage's or a task's key. A key is an identity the engine reads no meaning from (FR-003), so it MUST be derived from the name, made unique, and rewritten through the feedback edges that named it in the same edit.
- **FR-061**: The template editor MUST show a template as its SHAPE — every stage in the order it runs, with the routes that send work back drawn between them — beside the tasks of the one stage being edited, and MUST keep a stage's and a task's own fields behind opening that stage or task. A run MUST show its own stages and tasks the same way, because it is the same shape with state on it.
- **FR-062**: The template editor MUST write each edit as it is made and MUST NOT hold unsaved state. A stage's and a task's fields are saved from the dialog that holds them; adding, reordering and deleting save themselves.
- **FR-066**: A disabled workflow MUST start no new runs, and the refusal MUST come from the daemon rather than from one client's list — a rule that lives only in the web UI is not a rule. Runs already created from it MUST be unaffected: they froze their own snapshot (FR-011), so switching a workflow off retires it from the menu and does not reach into work already under way.
- **FR-065**: A mounted external reference MUST be reported with what it points at — Confluence, Jira, a Google doc — when that can be recognised from its address, and with nothing when it cannot. The node's context MUST carry it, so that "go and read this" resolves to one tool rather than a guess. It MUST be derived on read rather than stored, so a reference mounted before its provider was recognisable is recognised without a migration.
- **FR-069**: The developer MUST be able to write a note of their own into a run's context, in markdown, and to keep editing it for as long as the run lives. A note MUST be stored as a file under the run's own directory and listed to every task as the developer's own words; an image pasted into one MUST be stored with the run and MUST be displayable, which the text preview cannot answer for.
- **FR-064**: A file in a run's context MUST be readable from the app: an uploaded input and a produced artifact by their contents, a mounted collection by its own page, and an external reference by its address. Reading MUST be bounded — a path outside the run's own directory is refused, a long file is returned as its head and says so, and bytes that are not text are reported as such rather than rendered.
- **FR-068**: The developer MUST be able to say something to any task at any point in its life, in ordinary words, in one place. Before the task starts, what they say MUST be queued onto the attempt it opens with and reach its brief; while it waits for review, it MUST carry that attempt on; once it has finished, it MUST open the task's next attempt within the ceiling. A task whose turn is in flight or whose approval is pending MUST say so rather than accept it silently.
- **FR-063**: A task's page MUST offer no control that advances or alters the run. Retrying, redirecting and correcting are said in the task's conversation, where what is said also reaches every later task (FR-029). Deciding an approval is the one exception (FR-039), because a payload cannot honestly be approved by typing into a composer.

### Key Entities

- **Workflow Template**: a named, versioned, user-defined shape of work — stages, their nodes, and the edges between them. A resource.
- **Run**: one execution of a frozen template snapshot against a working directory on one machine.
- **Run Event**: an append-only record of something that happened to a run; the run's truth.
- **Node Attempt**: one try at one node, with its conversation, status, output and artifacts.
- **Approval**: a pending decision that stands between a prepared external write and its execution.
- **Artifact**: a file a node produced, attributed to the node and attempt that wrote it.

## Acceptance Scenarios

### Scenario: a template is registered as a resource

- **Given** a valid template definition
- **When** it is registered
- **Then** it exists as `workflow:<name>` with the framework's lifecycle and an audit entry (FR-001, FR-040)

### Scenario: a template with any number of stages runs as written

- **Given** a template whose three stages are named by the user
- **When** a run is created from it
- **Then** the run's stages are exactly those three, in that order, and no stage carries behaviour Coffer supplied (FR-002, FR-003)

### Scenario: an invalid template is refused with the offending path

- **Given** a template whose node names a skill that is not registered, or an agent outside the template's scope
- **When** it is registered
- **Then** the write is refused, naming the path of the offending field, and nothing is stored (FR-006, FR-007)

### Scenario: editing a template leaves a running run alone

- **Given** a run created from a template
- **When** the template is edited
- **Then** the run continues against the snapshot it froze at creation (FR-010)

### Scenario: a run advances from one node to the next without prompting

- **Given** a started run whose first node has completed
- **When** no further command is issued
- **Then** the next node starts on its own and the run's position moves with it (FR-017)

### Scenario: a node's work happens in its own conversation

- **Given** a node that is starting
- **When** its turn begins
- **Then** the work runs in a conversation whose working directory is the run's, and the node records that conversation (FR-019)

### Scenario: a run reaches completed when its last node does

- **Given** a run on its final node
- **When** that node completes
- **Then** the run is `completed` and refuses further mutating commands (FR-013)

### Scenario: a stale version is refused rather than applied

- **Given** two clients holding the same observed version
- **When** both submit a command
- **Then** the second is refused with the run's current version and position, and the run changed once (FR-015)

### Scenario: a run rebuilds itself from its events

- **Given** a run mid-flight
- **When** the daemon restarts
- **Then** the run's status, stage and node are rebuilt from its events and match what they were (FR-014)

### Scenario: an interrupted node is reported, not resumed

- **Given** a node whose turn was in flight when the daemon stopped
- **When** the daemon starts again
- **Then** the node is `failed` with an `interrupted` reason, its conversation is intact, and a retry opens a new attempt (FR-027, FR-022)

### Scenario: a required artifact that was never written blocks completion

- **Given** a node owing a required artifact
- **When** its turn ends without that artifact
- **Then** the node does not complete and waits for the developer (FR-023)

### Scenario: sending work back adds a task and resets nothing

- **Given** a completed coding node and a testing node that found a code issue
- **When** the feedback edge is taken
- **Then** a task describing the issue joins the coding stage, the run goes back to it, and every node that already ran keeps its result and its conversation (FR-025)

### Scenario: a loop between two stages stops at the attempt ceiling

- **Given** a feedback edge that has fired its own ceiling
- **When** it would send work back once more
- **Then** the run fails with the reason instead of looping (FR-026)

### Scenario: each task is given its own number of tries

- **Given** a workflow whose drafting task may be tried three times and whose deploy task may be tried once
- **When** each of them fails
- **Then** the drafting task opens a second attempt and the deploy task fails the run, because the limit belongs to the task and not to the workflow (FR-026)

### Scenario: a workflow is renamed and re-described in place

- **Given** a workflow with stages and tasks already authored
- **When** the developer edits its name and its description on its own page
- **Then** both change, its stages and tasks are untouched, and the page follows it to the new name (FR-054)

### Scenario: a task is its own conversation, opened from the run

- **Given** a run whose task has started
- **When** the developer opens that task
- **Then** they get the task's own conversation, and the run has no conversation of its own to open (FR-030)

### Scenario: a later task opens with what the earlier ones said

- **Given** a run with completed tasks, things said in their conversations, and artifacts
- **When** the next node starts
- **Then** its opening context carries the earlier tasks' transcripts, the artifact catalogue naming each artifact's node and attempt, and the mounted inputs (FR-029, FR-031, FR-032)

### Scenario: the run's own page offers no controls

- **Given** a run mid-flight
- **When** its page is read
- **Then** it describes where the run is, what it produced and what it reads, and offers nothing that advances or alters it (FR-052)

### Scenario: a template is found where the other resources are, and a run is not

- **Given** the web UI
- **When** the developer looks for the shape of work as opposed to a delivery of it
- **Then** the template is listed among the vault's resources and the run is not, and neither list is reachable only through the other (FR-059, FR-001)

### Scenario: the editor shows the whole flow beside the one stage being edited

- **Given** a template of three stages, each with tasks, and an edge sending work back
- **When** the editor is opened
- **Then** every stage is listed in order with the route back drawn between them, the tasks of one stage are shown and no other stage's are, and a task's fields appear only when that task is opened (FR-061)

### Scenario: a note the developer wrote is part of the run's context

- **Given** a running run
- **When** the developer writes a note into it and later changes their mind about what it says
- **Then** the note is a markdown file under the run's own directory, it is listed to every task as the developer's own words, and the rewrite keeps the name the tasks already know it by (FR-069, FR-032)

### Scenario: a task can be told something before it starts

- **Given** a task the run has not reached yet
- **When** the developer writes what it should do
- **Then** what they wrote is carried on the attempt the task opens with and is part of the brief it reads (FR-068, FR-029)

### Scenario: talking to a finished task reopens it

- **Given** a task that has completed
- **When** the developer says it is not right
- **Then** the task's next attempt opens carrying what they said, bounded by the same ceiling as every other loop (FR-068, FR-026)

### Scenario: a task is driven by talking to it, not by buttons

- **Given** a task's conversation page, whatever the engine says that task allows
- **When** it is read
- **Then** it offers no control that advances or alters the run, and what it offers instead is the composer (FR-063, FR-052)

### Scenario: the editor never asks for an identifier it can derive

- **Given** the template editor, on the map and in either dialog
- **When** the developer authors a stage and a task
- **Then** no key is asked for, and the keys that were stored are slugs of the names (FR-060)

### Scenario: the editor has no save button of its own

- **Given** the template editor
- **When** it is read
- **Then** there is nothing to save and nothing to discard, because each edit was written as it was made (FR-062)

### Scenario: a file in the run's context can be read from the app

- **Given** a run with an uploaded input and an artifact a task wrote
- **When** the developer opens either from the run's context
- **Then** its contents are shown, and a path outside the run's own directory is refused rather than read (FR-064)

### Scenario: a mounted link tells the task which tool opens it

- **Given** a run with a Confluence link and an ordinary web link mounted
- **When** a node opens
- **Then** the first is named as a Confluence page and the second is named as nothing but a link, so the task reaches for a tool only where one was identified (FR-065)

### Scenario: a disabled workflow starts no new runs

- **Given** a workflow that is switched off and a run already created from it
- **When** a new run is asked for from that workflow
- **Then** it is refused by the daemon, and the run already going is unaffected (FR-066)

### Scenario: a node's type says who does the work

- **Given** a template whose tasks are an agent's and a person's
- **When** the engine decides what to do with each
- **Then** the only question the type answers is whether a turn is dispatched or the run waits for a person (FR-067, FR-020)

### Scenario: earlier tasks are summarised when they exceed the budget

- **Given** a run whose earlier tasks' transcripts exceed their share of the context budget
- **When** the next node opens
- **Then** the oldest are replaced by summaries, the context says so, and the whole is within budget (FR-047, FR-048)

### Scenario: a long conversation is compacted rather than truncated

- **Given** a node whose own conversation has exceeded its share of the budget
- **When** its next turn runs
- **Then** its oldest turns are replaced by a summary that stays in the conversation, and nothing is silently dropped (FR-049)

### Scenario: a template is authored in the app

- **Given** the template editor
- **When** the developer adds two stages, puts a node in each, binds a skill, and saves
- **Then** the template is stored through the resource endpoint and a run created from it has exactly those stages and nodes (FR-054, FR-056)

### Scenario: an invalid template is refused against the field that is wrong

- **Given** the template editor with a node naming a skill that is not registered
- **When** the developer saves
- **Then** the refusal is shown against that node's skill field, and nothing is stored (FR-055, FR-006)

### Scenario: a run is created from a template and a title alone

- **Given** a registered template
- **When** a run is created with nothing but that template and a title
- **Then** the run exists with a working directory Coffer made for it and no inputs, and neither was asked for (FR-011, FR-053)

### Scenario: an uploaded file becomes an input the nodes can read

- **Given** a run and a file the developer uploads to it
- **When** a node opens
- **Then** the file is stored under the run's directory, listed in the node's context, and readable from the working directory (FR-051, FR-032)

### Scenario: a mounted repository gives the run its own checkout

- **Given** a run and a local git repository
- **When** the developer mounts it as a repository input
- **Then** the run's working directory holds a worktree of it on a branch of the run's own, the source repository's own working tree is untouched, and unmounting removes the worktree and nothing else (FR-057, FR-058)

### Scenario: an input can be added and removed while the run is going

- **Given** a run that is already running
- **When** the developer adds a link and removes a collection
- **Then** both take effect for every node that opens afterwards (FR-050)

### Scenario: an ad-hoc task joins a stage and carries the same context

- **Given** a running run
- **When** the developer adds a task to a stage with instructions of their own
- **Then** it runs with the same shared context and its artifacts are attributed to it as to any node (FR-028)

### Scenario: a write-class tool call without an approval is refused

- **Given** a node whose agent calls a write-class upstream tool with no approved approval
- **When** the gateway dispatches the call
- **Then** the call is refused with an explicit reason and the upstream system is untouched (FR-034, FR-035)

### Scenario: an approved call goes through exactly once

- **Given** a held write-class call and its approval
- **When** the developer approves
- **Then** the call resumes and reaches the upstream system once (FR-037)

### Scenario: an unknown tool is treated as write-class

- **Given** an upstream tool the vault has no judgement for
- **When** a node calls it
- **Then** it is held as write-class, and once the developer answers, the judgement is remembered for next time (FR-036)

### Scenario: an approval decision is idempotent

- **Given** an approval already approved
- **When** the same decision arrives again
- **Then** the terminal state is unchanged and nothing executes a second time (FR-038)

### Scenario: an expired approval does not authorise a write

- **Given** an approval past its expiry
- **When** the held call resumes
- **Then** the call fails with an explicit reason rather than executing (FR-037)

### Scenario: an approval reaches the developer where they are

- **Given** a run with a bound channel
- **When** an approval is created
- **Then** it is shown on the conversation of the task that raised it and is delivered through that channel (FR-039)

### Scenario: a run's artifacts become a knowledge collection

- **Given** a completed run with artifacts
- **When** the developer promotes them
- **Then** a knowledge collection holds those files and the run's directory is unchanged (FR-043, FR-042)

### Scenario: a delivery that has produced nothing yet is still worth keeping

- **Given** a running run with an uploaded file, a note and a link, and no artifact
- **When** the developer saves it into a knowledge collection
- **Then** the file and the note are copied there, the link is recorded as an address in a written reference, and the run's directory is unchanged (FR-043)

### Scenario: a run is read-only on a machine that does not own it

- **Given** a run owned by another machine
- **When** it is opened here
- **Then** it is visible and its mutating commands are refused (FR-012)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can take a requirement to a reviewed technical design, a branch of code, and a test report without issuing a command between stages other than review and approval decisions.
- **SC-002**: No upstream write executed on behalf of a run without an approval the developer decided.
- **SC-003**: A run's position after a daemon restart matches its position before, for every run that was not mid-turn.
- **SC-004**: A change of direction stated once in a task's conversation is visible to every task that runs afterwards, without being restated.
- **SC-005**: A delivery flow can be redefined — stages added, removed or reordered — without changing any code.
- **SC-006**: A node opens within its context budget however long the run has been going.

## Assumptions

- The developer is the single owner of this vault and the only approver.
- A run's work happens in one working directory; work in a second repository is an ad-hoc task pointed at it.
- The agents a node runs on are the registered ones; this layer adds no agent type.
- A node's external reach is whatever the gateway already exposes; this layer registers no upstream server of its own.

- Summarising a transcript uses the internal connection the rest of the vault already uses for its own model calls; with none configured, the oldest transcripts are listed rather than summarised, and the context says so.

## Out of Scope

- Parallel nodes within a run — one node at a time, so shared context and approvals stay answerable.
- Multi-person review or assignment; there is one owner and no reviewer role.
- Scheduling a run to start at a time; a run starts when the developer starts it.
- Driving the engine from an agent over MCP — an agent does a node's work, it does not decide the run's shape.
