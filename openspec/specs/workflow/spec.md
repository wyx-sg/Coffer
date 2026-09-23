# Workflow

## Purpose
Coffer already holds everything an agent needs to do a piece of work: the agents themselves, the skills that say how a job is done, the knowledge and memory that say what is already known, and the gateway that reaches the outside world. What Coffer has never held is **the shape of the work** — that a delivery goes from a requirement to a design to code to a test to a release, that each step owes a deliverable, and that some steps must not happen without the developer saying so. A workflow is that shape, written by the developer as a template of stages and the tasks inside them; a run is one delivery through it, advancing on its own in the background.

This layer adds that shape and nothing else. It introduces no second way to run an agent: every task in a run is one ordinary Coffer conversation, driven by the turn platform the channels already use ([chat](../chat/spec.md)), and a run is the arrangement of those conversations rather than a conversation of its own. It introduces no second place to keep files: artifacts are plain files, the way knowledge is. It introduces no second notification path: an approval reaches the developer through a channel that already exists.

**A node is a conversation, and that is where everything happens.** A stage holds one or more nodes, and each node is one conversation. The node opens with its bound skill already driving it, so the ordinary case is that it does its work without being told how; the developer opens the conversation when they want to steer it, and says so in ordinary words. Unplanned work is a task added to a stage and is a conversation like any other. Everything the developer does, they do inside a conversation: the run's own page is a map — where the delivery is, what it has produced, what it is reading — and carries no controls. Retry, skip, redirect, correct: all of it is said in the node's conversation, where the thing being decided is in front of them. The single exception is an approval's Approve / Reject, which is a decision about an exact payload and cannot honestly be made by typing "ok".

**A task's deliverable is what the next task reads.** Tasks do not hand each other their conversations. Each task owes at least one artifact — a file written at a path the task was told — and that artifact is the whole of what it says to the tasks that follow. A task opens with an INDEX of the run so far: every task that has run, what became of it, and the paths of what it produced. It opens what it needs from those paths and leaves the rest closed. That is the rule the whole opening context is built from: **name it, do not paste it.** Carrying the earlier tasks' transcripts forward instead was tried and does not survive a real delivery — the opening message then grows with every task that preceded it, and the fortieth task cannot start. An index costs one line per task however long the run gets, and a task that wants the detail is one `read` away from it. So a change of direction stated once in a task's conversation reaches every later task by way of the deliverable that task writes, and a task that owes nothing tells the next task nothing — which is why every task owes a deliverable.

**The one position this layer reverses.** Coffer does not gate individual tool calls today, and that is a considered position: the paired owner driving a conversation is the trust boundary, so an agent in a chat runs with the owner watching. A workflow run has no one watching — it advances in the background, possibly overnight. The trust boundary that holds for a chat does not hold here, so this layer introduces a gate on write-class tool calls made on behalf of a run, and only on behalf of a run. A conversation that is not a workflow node is untouched. An unattended run with unrestricted write access to Jira, GitLab and the deploy platform is the single way this layer can do real damage. See [A Workflow Run's Writes Are Gated at the Gateway](../../../docs/decisions/workflow-gates-tool-calls.md).

What the layer promises as outcomes: a developer can take a requirement to a reviewed technical design, a branch of code, and a test report without issuing a command between stages other than review and approval decisions; no upstream write executes on behalf of a run without an approval the developer decided; a run's position after a daemon restart matches its position before, for every run that was not mid-turn; a delivery flow can be redefined — stages added, removed or reordered — without changing any code; and a task's opening context grows by one line per task that preceded it, so the last task of a forty-task delivery opens on roughly what the first one did.

What it assumes: the developer is the single owner of this vault and the only approver. A run's work happens in one working directory; work in a second repository is an ad-hoc task pointed at it. The agents a node runs on are the registered ones; this layer adds no agent type. A node's external reach is whatever the gateway already exposes; this layer registers no upstream server of its own. Compacting one task's own conversation uses the internal connection the rest of the vault already uses for its own model calls; with none configured, nothing is removed and the conversation is told why ("Compact a long node conversation into a summary"). Nothing else in a task's opening context needs a model, because none of it is summarised — it is named.

What it is not, and its known boundaries. It is not a CI system — it never builds or tests on its own; a node asks an agent to, and the agent runs the repository's own commands. It is not a project tracker — Jira stays Jira, and a node writes to it through the gateway like any other external system. It is not a second agent runtime. It runs one task at a time, so the index a task opens with and the approvals it raises stay answerable; it has no multi-person review or assignment, since there is one owner and no reviewer role; a run starts when the developer starts it, never on a schedule; and an agent does a node's work but does not drive the engine over MCP or decide the run's shape. The gate is not a sandbox: it covers what Coffer brokers, so a node's agent with a shell can still reach the network directly.

## Requirements

### Requirement: Register a template as a workflow resource
The system MUST register a workflow template as a resource of kind `workflow`, identified by the framework's immutable `uid` ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)), taking the framework's lifecycle, audit, schema validation, rename and sync. Creating a run MUST name the template by that uid; what a run records of it afterwards is its LABEL, frozen at creation and provenance only ("Freeze the template when a run is created").

#### Scenario: a template is registered as a resource
- **GIVEN** a valid template definition
- **WHEN** it is registered
- **THEN** it exists as a `workflow` resource with its own identity, the framework's lifecycle and an audit entry

### Requirement: Order a template's stages as the developer names them
A template MUST carry an ordered list of one or more stages, each with a key and a display name chosen by the user.

#### Scenario: a template with any number of stages runs as written
- **GIVEN** a template whose three stages are named by the user
- **WHEN** a run is created from it
- **THEN** the run's stages are exactly those three, in that order, and no stage carries behaviour Coffer supplied

### Requirement: Attach no behaviour to a stage key
The system MUST attach no behaviour to any stage key — a stage's meaning is its position in the template and nothing else.

#### Scenario: a stage's key changes nothing about how it runs
- **GIVEN** two templates identical except for the keys their stages carry
- **WHEN** a run is created from each and advanced through its tasks
- **THEN** both runs take the same tasks in the same order and end the same way
- **AND** neither run's progress depends on what its stage keys were

### Requirement: Carry each stage's nodes in order with what runs them
A stage MUST carry an ordered list of nodes; a node names its type, an optional skill to run, optional additional instructions, the artifacts it owes, its approval policy, its failure behaviour and optionally the agent it runs on.

#### Scenario: a task carries everything the engine needs to run it
- **GIVEN** a stage holding two tasks in the order the developer put them
- **WHEN** the template is read back
- **THEN** each task carries its type, its bound skill, its own instructions, the artifacts it owes, its approval policy, its failure behaviour and the agent it runs on, and the stage's tasks are in the order they were written

### Requirement: Type a node by who does the work
A node's type MUST name who does the work and nothing else: an agent, or a person. The system MUST NOT carry a type that only describes what the work is ABOUT — a task's name and its instructions say that — and MUST NOT carry a type whose executor it cannot actually run.

#### Scenario: a node's type says who does the work
- **GIVEN** a template whose tasks are an agent's and a person's
- **WHEN** the engine decides what to do with each
- **THEN** the only question the type answers is whether a turn is dispatched or the run waits for a person

### Requirement: Refuse an invalid template naming the offending path
The system MUST validate a template on write and refuse an invalid one naming the offending path, never storing a template that would stall a run.

#### Scenario: an invalid template is refused with the offending path
- **GIVEN** a template whose node names a skill that is not registered, or an agent outside the template's scope
- **WHEN** it is registered
- **THEN** the write is refused, naming the path of the offending field, and nothing is stored

### Requirement: Read a template's scope as the agents it may drive
A template's scope MUST be read inverted, as the agents this template may drive; a node naming an agent outside that scope MUST be refused at validation.

#### Scenario: a node may name only an agent the template may drive
- **GIVEN** a template scoped to one agent
- **WHEN** one of its nodes names that agent, and in a second version a node names an agent outside the scope
- **THEN** the first is accepted
- **AND** the second is refused at validation, naming that node's agent field, and nothing is stored

### Requirement: Sync templates with the vault
A template MUST travel with vault sync, so a flow defined on one machine is available on the developer's others.

#### Scenario: a workflow defined on one machine is there on the other
- **GIVEN** a workflow registered on one machine and a vault that syncs
- **WHEN** the developer's other machine converges
- **THEN** the workflow is there to run from, taking the same path every other resource kind takes

### Requirement: Seed one built-in template
The system MUST seed exactly one built-in template, which the developer may edit or delete like any other.

#### Scenario: a vault that has never been touched already has a workflow
- **GIVEN** a vault with no workflow of the developer's own
- **WHEN** they look for one to run
- **THEN** exactly one built-in workflow is there, it names no skill and assumes nothing about what this vault has registered, and it can be edited, disabled or deleted like any other

### Requirement: Freeze the template when a run is created
Creating a run MUST freeze a snapshot of its template; later edits to that template MUST NOT affect a run already created.

#### Scenario: editing a template leaves a running run alone
- **GIVEN** a run created from a template
- **WHEN** the template is edited
- **THEN** the run continues against the snapshot it froze at creation

### Requirement: Create a run from a template and a title alone
A run MUST be created from a template and a title, and MUST NOT be a resource — it is operational state, not a curated asset. Creating one MUST ask for nothing else: a working directory and inputs are not part of it.

#### Scenario: a run is created from a template and a title alone
- **GIVEN** a registered template
- **WHEN** a run is created with nothing but that template and a title
- **THEN** the run exists with a working directory Coffer made for it and no inputs, and neither was asked for

### Requirement: Give each run a working directory of its own
The system MUST create and own a working directory per run, under that run's own directory, and every node's conversation MUST run in it. The developer MUST NOT be asked for one and MUST NOT be able to set one.

#### Scenario: a run's working directory is Coffer's to choose
- **GIVEN** a request to create a run that also names a working directory of its own
- **WHEN** it reaches the daemon
- **THEN** no run is given the directory the request named
- **AND** a run created from a template and a title works in a directory under that run's own directory

### Requirement: Advance a run only on the machine that owns it
A run MUST record the machine that owns it; only that machine's daemon MUST advance it, and another machine MUST show it read-only.

#### Scenario: a run is read-only on a machine that does not own it
- **GIVEN** a run owned by another machine
- **WHEN** it is opened here
- **THEN** it is visible and its mutating commands are refused

### Requirement: Keep a run to six statuses
A run MUST have exactly the statuses `draft`, `running`, `paused`, `completed`, `aborted` and `failed`. "Waiting for the developer" is a property of a node, never of a run.

#### Scenario: a run reaches completed when its last node does
- **GIVEN** a run on its final node
- **WHEN** that node completes
- **THEN** the run is `completed` and refuses further mutating commands

### Requirement: Rebuild a run from its event log
A run's append-only event log MUST be its record of truth, and the run's current stage, node and status MUST be a projection rebuilt from those events on start.

#### Scenario: a run rebuilds itself from its events
- **GIVEN** a run mid-flight
- **WHEN** the daemon restarts
- **THEN** the run's status, stage and node are rebuilt from its events and match what they were

### Requirement: Refuse a command carrying a stale version
Every mutating command MUST carry the caller's observed version, and a stale version MUST be refused with the run's current version and position rather than applied.

#### Scenario: a stale version is refused rather than applied
- **GIVEN** two clients holding the same observed version
- **WHEN** both submit a command
- **THEN** the second is refused with the run's current version and position, and the run changed once

### Requirement: Accept the run signals start, pause, resume and abort
The system MUST support the run signals `start`, `pause`, `resume` and `abort`; an aborted run MUST refuse every later mutating command.

#### Scenario: an aborted run refuses everything afterwards
- **GIVEN** a running run
- **WHEN** it is paused, resumed and then aborted
- **THEN** each signal is accepted in turn, and after the abort every mutating command is refused rather than applied

### Requirement: Run at most one node at a time
At most one node of a run MUST be running at any moment.

#### Scenario: a run advances from one node to the next without prompting
- **GIVEN** a started run whose first node has completed
- **WHEN** no further command is issued
- **THEN** the next node starts on its own and the run's position moves with it

### Requirement: Run a node's work as one conversation
A node's work MUST be one conversation on the turn platform, with the run's working directory as the conversation's working directory.

#### Scenario: a node's work happens in its own conversation
- **GIVEN** a node that is starting
- **WHEN** its turn begins
- **THEN** the work runs in a conversation whose working directory is the run's, and the node records that conversation

### Requirement: Keep a node to seven statuses
A node MUST have exactly the statuses `pending`, `running`, `waiting_review`, `waiting_approval`, `completed`, `skipped` and `failed`.

#### Scenario: a node is only ever in one of seven statuses
- **GIVEN** the statuses a node can be in, as the engine holds them and as the API reports them
- **WHEN** they are listed
- **THEN** they are exactly `pending`, `running`, `waiting_review`, `waiting_approval`, `completed`, `skipped` and `failed`

### Requirement: Accept the node actions start, feedback, complete, retry, skip and restore
The system MUST support the node actions `start`, `feedback`, `complete`, `retry`, `skip` and `restore`.

#### Scenario: a node takes exactly six actions
- **GIVEN** a node of a run
- **WHEN** an action is submitted to it
- **THEN** `start`, `feedback`, `complete`, `retry`, `skip` and `restore` are the actions it knows
- **AND** an action outside those six is refused rather than applied

### Requirement: Keep every attempt when a node is retried
A retry MUST append a new attempt; an attempt's conversation, output and feedback MUST survive it.

#### Scenario: a retry keeps the attempt before it
- **GIVEN** a node whose first attempt ended with a conversation, an output and feedback from the developer
- **WHEN** it is retried
- **THEN** a second attempt is appended
- **AND** the first attempt's conversation, output and feedback are still there to read

### Requirement: Hold completion until a required artifact exists
A node that owes a required artifact and has not produced it MUST NOT complete; it MUST wait for the developer to supply it or waive it.

#### Scenario: a required artifact that was never written blocks completion
- **GIVEN** a node owing a required artifact
- **WHEN** its turn ends without that artifact
- **THEN** the node does not complete and waits for the developer

### Requirement: Handle a node failure as the node declares
A node failure MUST be handled by the node's declared failure behaviour: stop the run, continue to the next node, or retry up to a stated number of times.

#### Scenario: a failed task does what its workflow said to do about failure
- **GIVEN** three workflows whose task declares `stop`, `continue` and `retry` twice
- **WHEN** that task fails in each
- **THEN** the first run stops on it, the second carries on to the next task, and the third opens two more attempts before it stops — the behaviour the task declared, not one the engine chose

### Requirement: Send work back by the developer's hand, never a template route
Sending work back MUST be the developer's own action and MUST NOT be a route the template draws. A finding in a later task is acted on by retrying the task that was wrong or by adding a task that fixes it ("Accept the node actions start, feedback, complete, retry, skip and restore" and "Add an ad-hoc task to any stage"); either way the tasks that already ran keep their result, their conversation and their artifacts. The template MUST NOT carry an edge between stages, because the judgement it would encode — whether this finding means redo the code or redo the design — is one only the person or the agent holding the finding can make, and a route fixed when the template was written makes it in advance and wrongly.

#### Scenario: sending work back is the developer's hand, not the template's route
- **GIVEN** a completed coding task and a testing task that found a code issue
- **WHEN** the developer acts on the finding
- **THEN** the template offers no route to take, and what they do instead — retry the coding task, or add a task that fixes it — leaves every task that already ran holding its result, its conversation and its artifacts

### Requirement: Bound each task's attempts by its own ceiling
Every task MUST declare how many attempts it may open, and reaching that limit MUST fail the run with the reason rather than open another. The limit MUST belong to the task rather than to the workflow as a whole — a draft that is cheap to redo and a deploy that must not be tried twice are not the same judgement — and a task that names no limit MUST be given a default rather than an unbounded one.

#### Scenario: each task is given its own number of tries
- **GIVEN** a workflow whose drafting task may be tried three times and whose deploy task may be tried once
- **WHEN** each of them fails
- **THEN** the drafting task opens a second attempt and the deploy task fails the run, because the limit belongs to the task and not to the workflow

### Requirement: Report a node interrupted by a restart as failed
A node whose turn was interrupted by a daemon restart MUST be reported as failed with an `interrupted` reason, with its conversation preserved and readable.

#### Scenario: an interrupted node is reported, not resumed
- **GIVEN** a node whose turn was in flight when the daemon stopped
- **WHEN** the daemon starts again
- **THEN** the node is `failed` with an `interrupted` reason, its conversation is intact, and a retry opens a new attempt

### Requirement: Add an ad-hoc task to any stage
The developer MUST be able to add an ad-hoc task to any stage of a run at any time, writing its instructions themselves; it MUST be recorded, contextualised and attributed exactly as a template node is.

#### Scenario: an ad-hoc task joins a stage and carries the same context
- **GIVEN** a running run
- **WHEN** the developer adds a task to a stage with instructions of their own
- **THEN** it runs with the same shared context and its artifacts are attributed to it as to any node

### Requirement: Open every task with the same four parts
Every task MUST open with the same four parts: its own brief including the exact path of each deliverable it owes, its bound skill's instructions, an index of the run's earlier tasks, and the run's mounted inputs. The skill's instructions are the only part carried as CONTENT, and even they are bounded ("Keep a task's opening context within budget") — everything else MUST be named with the path or address that opens it, because a collection, an artifact or a repository can each be larger than the whole message. A task's opening context MUST NOT carry another task's conversation.

#### Scenario: a later task opens with an index of what the run produced
- **GIVEN** a run with completed tasks, long conversations in them, and the artifacts they wrote
- **WHEN** the next task starts
- **THEN** its opening context lists each earlier task with what became of it and the path of each artifact it produced, lists the mounted inputs by name and address, and carries no earlier task's conversation

### Requirement: Give a run no conversation of its own
A run MUST NOT have a conversation of its own. Every conversation in a run belongs to one task, the developer speaks to a task inside it, and what they say reaches the rest of the run by way of the deliverable that task writes, which is what every later task reads.

#### Scenario: a task is its own conversation, opened from the run
- **GIVEN** a run whose task has started
- **WHEN** the developer opens that task
- **THEN** they get the task's own conversation, and the run has no conversation of its own to open

### Requirement: Generate the index of earlier tasks
The index of earlier tasks MUST be generated rather than hand-maintained: the artifacts from what is on disk, each named with the task and attempt that produced it, and the tasks from the run's own record. A task the run has already opened and that produced nothing — because it failed, or was skipped — MUST still appear, with what became of it, because a task missing from the index reads as a task that never existed and the next one works from a hole it cannot see. The index MUST carry the LATEST attempt of each task and not the ones before it: a run reopens a task because what it produced was not right, so listing both would offer the next task a discarded deliverable beside the real one with nothing to tell them apart.

#### Scenario: a task that produced nothing is still in the index
- **GIVEN** a run whose second task failed and whose third was skipped
- **WHEN** the fourth task opens
- **THEN** both appear in its index with what became of them, so the absence of their deliverables is something it was told rather than something it has to infer

### Requirement: List a run's mounted inputs to every node
A run's mounted inputs MUST be able to include knowledge collections, uploaded files, notes the developer wrote, external references and local repositories, and MUST be listed to every node rather than inlined wholesale.

#### Scenario: every kind of input is listed and none is pasted
- **GIVEN** a run with a knowledge collection, an uploaded file, a note, an external reference and a local repository mounted
- **WHEN** a node opens
- **THEN** each of the five is listed in its opening context by the path or address that opens it
- **AND** none of their contents is inlined into that context

### Requirement: Give a mounted repository its own checkout
Mounting a repository input MUST give the run its own checkout of it inside the run's working directory. When the path is a git repository the system MUST create a git worktree on a branch of the run's own; otherwise it MUST link the directory in and say that it did. A run MUST NOT be pointed at the developer's working checkout in a way that lets it write there, because a run advances unattended and the developer's uncommitted work is not its to touch.

#### Scenario: a mounted repository gives the run its own checkout
- **GIVEN** a run and a local git repository
- **WHEN** the developer mounts it as a repository input
- **THEN** the run's working directory holds a worktree of it on a branch of the run's own, the source repository's own working tree is untouched, and unmounting removes the worktree and nothing else

### Requirement: Leave the source repository untouched on unmount
Unmounting a repository input MUST remove what the run was given and MUST leave the source repository, its branches and its working tree untouched.

#### Scenario: unmounting a repository leaves the source as it was
- **GIVEN** a local git repository with uncommitted work, mounted on a run
- **WHEN** the developer unmounts it
- **THEN** the run's checkout of it is gone
- **AND** the source repository's working tree, its uncommitted work and the developer's own branches are as they were, and its branch list is the one it had before the repository was mounted

### Requirement: Keep a task's opening context within budget
The system MUST keep a task's opening context within a stated token budget, and MUST say in the context itself what it shortened rather than silently dropping it. The budget is a backstop rather than the mechanism: an index of names is what keeps the context small, and a run long enough to overrun even that MUST be told which of its older tasks were elided and where the whole index can be read.

#### Scenario: an index too long for the budget says what it left out
- **GIVEN** a run of so many tasks that even their index exceeds the context budget
- **WHEN** the next task opens
- **THEN** the oldest entries are elided, the context says which and where the whole index can be read, and what remains is within budget

### Requirement: Compact a long node conversation into a summary
When one node's own conversation exceeds its share, the system MUST compact its oldest turns into a summary that stays in the conversation.

#### Scenario: a long conversation is compacted rather than truncated
- **GIVEN** a node whose own conversation has exceeded its share of the budget
- **WHEN** its next turn runs
- **THEN** its oldest turns are replaced by a summary that stays in the conversation, and nothing is silently dropped

### Requirement: Add and remove inputs at any point in a run
The developer MUST be able to add and remove a run's inputs at any point in its life, not only when it is created.

#### Scenario: an input can be added and removed while the run is going
- **GIVEN** a run that is already running
- **WHEN** the developer adds a link and removes a collection
- **THEN** both take effect for every node that opens afterwards

### Requirement: Store an uploaded input under the run's directory
An uploaded input MUST be stored under the run's own directory and MUST be readable by the agent from the working directory it runs in.

#### Scenario: an uploaded file becomes an input the nodes can read
- **GIVEN** a run and a file the developer uploads to it
- **WHEN** a node opens
- **THEN** the file is stored under the run's directory, listed in the node's context, and readable from the working directory

### Requirement: Hold a task whose policy requires approval when its turn ends
A task whose approval policy requires it MUST stop for the developer when its turn ends and MUST NOT let the run move past it until they say so. This is a decision about WORK, not about a payload: a task's work is a conversation, and a conversation has no single exact payload to hold up in front of someone before it runs. The decision that IS about an exact payload is the one the gateway makes on a write-class tool call ("Refuse an unapproved write-class tool call made for a run"), which is where a payload exists and where holding it actually stops the outside world being touched. The system MUST NOT carry a second approval mechanism at the task level claiming to do the gateway's job at a level that cannot do it.

#### Scenario: a task whose workflow demands approval holds the run until the developer decides
- **GIVEN** a task whose approval policy is `always` and a task after it
- **WHEN** its turn ends
- **THEN** it waits for the developer rather than completing, the task after it does not start, and no approval of its own is raised — what its writes needed was decided at the gateway while it ran

### Requirement: Refuse an unapproved write-class tool call made for a run
The gateway MUST refuse a write-class upstream tool call made on behalf of a run that has no approved, unexpired approval for it.

#### Scenario: a write-class tool call without an approval is refused
- **GIVEN** a node whose agent calls a write-class upstream tool with no approved approval
- **WHEN** the gateway dispatches the call
- **THEN** the call is refused with an explicit reason and the upstream system is untouched

### Requirement: Give the gateway the run's identity at dispatch
The system MUST make a run's identity available to the gateway at the point a tool call is dispatched, so a call can be attributed to the run and node that caused it.

#### Scenario: a tool call is attributed to the run and task that made it
- **GIVEN** a task whose turn is in flight, and the agent's shim launched for that turn
- **WHEN** the agent calls an upstream tool through the gateway
- **THEN** the gateway knows, as it dispatches the call, the run and the attempt the call was made for
- **AND** a call from a shim launched outside any run carries no run identity

### Requirement: Treat an unjudged tool as write-class and remember the answer
A tool the vault has no write-class judgement for MUST be treated as write-class, and the developer's answer MUST be remembered so the same tool is not asked about twice.

#### Scenario: an unknown tool is treated as write-class
- **GIVEN** an upstream tool the vault has no judgement for
- **WHEN** a node calls it
- **THEN** it is held as write-class, and once the developer answers, the judgement is remembered for next time

### Requirement: Resume or fail a held tool call, never drop it
A held tool call MUST resume once approved, MUST fail with an explicit reason once its approval expires or is rejected, and MUST NOT be silently dropped.

#### Scenario: an approved call goes through exactly once
- **GIVEN** a held write-class call and its approval
- **WHEN** the developer approves
- **THEN** the call resumes and reaches the upstream system once

#### Scenario: an expired approval does not authorise a write
- **GIVEN** an approval past its expiry
- **WHEN** the held call resumes
- **THEN** the call fails with an explicit reason rather than executing

### Requirement: Make an approval decision idempotent
An approval decision MUST be idempotent — a repeated decision MUST return the same terminal state and MUST NOT cause a second execution.

#### Scenario: an approval decision is idempotent
- **GIVEN** an approval already approved
- **WHEN** the same decision arrives again
- **THEN** the terminal state is unchanged and nothing executes a second time

### Requirement: Show an approval on its task's conversation and through a bound channel
An approval MUST be shown on the conversation of the task that raised it — where the developer is already reading what led to it — and MUST also be delivered through a channel when one is bound.

#### Scenario: an approval reaches the developer where they are
- **GIVEN** a run with a bound channel
- **WHEN** an approval is created
- **THEN** it is shown on the conversation of the task that raised it and is delivered through that channel

### Requirement: Audit template, run, approval and gate events
The system MUST record an audit event for every template lifecycle change, the start and the end of every run, every approval decision and every gated tool call. A run's pauses and resumes are not audited: its own event log already records them ("Rebuild a run from its event log"), and the audit trail answers the coarser question of what this vault did on its own.

#### Scenario: every change to a workflow leaves an audit entry
- **GIVEN** a template, a run of it, an approval and a write-class tool call made for that run
- **WHEN** the template is registered, the run starts and finishes, the approval is decided and the tool call is held
- **THEN** each of those leaves its own entry in the audit log

### Requirement: Give every task at least one deliverable
Every task MUST owe at least one artifact, and a task whose template declared none MUST be given a required `report.md`. A deliverable is the only thing a task says to the tasks after it ("Open every task with the same four parts"), so a task that owes nothing is a task whose work leaves the run when its conversation closes. The default MUST be applied where the template is read rather than written into the developer's template, so a task they later give a deliverable of its own is not left owing two.

#### Scenario: a task the developer gave no deliverable still owes one
- **GIVEN** a workflow whose task declares no artifacts
- **WHEN** a run reaches that task
- **THEN** it opens owing a required `report.md` at an exact path, it does not complete until that file is there, and the developer's stored template is unchanged

### Requirement: Store artifacts as files attributed to their node and attempt
A node's artifacts MUST be files under the run's own directory, attributed to the node and attempt that wrote them.

#### Scenario: an artifact is a file, attributed to what wrote it
- **GIVEN** a task on its second attempt that writes the deliverable it owes
- **WHEN** the run's artifacts are read
- **THEN** the file is under the run's own directory and is named with that task and that attempt, so the first attempt's copy is still distinguishable from it

### Requirement: Never index a run's directory
A run's directory MUST NOT be indexed, chunked or embedded — the files are the only copy.

#### Scenario: a run's files are the only copy of themselves
- **GIVEN** a run whose tasks wrote artifacts and whose developer uploaded a file
- **WHEN** the run's directory is read after the work
- **THEN** it holds those files as they were written and nothing derived from them beyond its generated catalogue — no search index, no chunks, no embeddings
- **AND** the knowledge root has gained nothing from them

### Requirement: Promote what a run is made of into a knowledge collection
What a run is MADE OF MUST be promotable into a knowledge collection in one action, so a delivery's output becomes the next delivery's input. Its artifacts, its uploaded files and its notes MUST travel as files; the links, collections and repositories it read MUST travel as one written record of having been read, because those are not the run's bytes to copy. It MUST NOT wait for the run to produce anything: a delivery that has so far only been given a brief is one whose brief is worth keeping.

#### Scenario: a run's artifacts become a knowledge collection
- **GIVEN** a completed run with artifacts
- **WHEN** the developer promotes them
- **THEN** a knowledge collection holds those files and the run's directory is unchanged

#### Scenario: a delivery that has produced nothing yet is still worth keeping
- **GIVEN** a running run with an uploaded file, a note and a link, and no artifact
- **WHEN** the developer saves it into a knowledge collection
- **THEN** the file and the note are copied there, the link is recorded as an address in a written reference, and the run's directory is unchanged

### Requirement: Expose the engine over REST
The system MUST expose templates, runs, nodes, approvals and events over the REST API.

#### Scenario: everything the engine holds is on the API
- **GIVEN** a run with tasks, an approval and an event log
- **WHEN** the API is read
- **THEN** the workflows, the runs, their tasks, their approvals and their events are all reachable over REST, and no surface reads the engine another way

### Requirement: Show runs, their tasks and their context in the web UI
The web UI MUST list runs; show a run's stages and its tasks with their status; show what the run reads and what it has produced together in one list; open any task as its own conversation page; and let the developer decide that task's approvals from that page.

#### Scenario: the web UI shows a delivery without opening its files by hand
- **GIVEN** a run mid-flight
- **WHEN** the developer opens the runs list and then that run
- **THEN** the list shows the run, the run shows its stages and its tasks with their status, what it reads and what it has produced are one list, any task opens as its own conversation page, and its approvals are decided from that page

### Requirement: Drive runs from the CLI
The CLI MUST create, list, inspect, signal and abort runs, manage a run's inputs, act on a node, and decide approvals.

#### Scenario: the same delivery can be driven from the command line
- **GIVEN** a registered workflow
- **WHEN** the developer works only from the CLI
- **THEN** they can create, list, inspect, signal and abort a run, add and remove its inputs, act on a task, and decide an approval

### Requirement: Author templates in the web UI
The web UI MUST let the developer author a template: list templates, create one, and edit its stages and their order, the nodes in each stage and their order, each node's type, bound skill, instructions, declared artifacts, approval policy, failure behaviour, agent and attempt ceiling. The workflow's name and description MUST be editable in place, on the workflow's own page, rather than only at creation.

#### Scenario: a workflow is renamed and re-described in place
- **GIVEN** a workflow with stages and tasks already authored
- **WHEN** the developer edits its name and its description on its own page
- **THEN** both change, its stages and tasks are untouched, and the page does not move — it was never addressed by the name

### Requirement: Show a validation refusal against its field
A refusal from template validation MUST be shown against the field it names rather than as a whole-form error, since the refusal already carries the offending path ("Refuse an invalid template naming the offending path").

#### Scenario: an invalid template is refused against the field that is wrong
- **GIVEN** the template editor with a node naming a skill that is not registered
- **WHEN** the developer saves
- **THEN** the refusal is shown against that node's skill field, and nothing is stored

### Requirement: Write templates through the resource endpoint only
The template editor MUST write through the same resource endpoint every other client uses; it MUST NOT have a write path of its own.

#### Scenario: a template is authored in the app
- **GIVEN** the template editor
- **WHEN** the developer adds two stages, puts a node in each, binds a skill, and saves
- **THEN** the template is stored through the resource endpoint and a run created from it has exactly those stages and nodes

### Requirement: Offer no run controls on the run's page
The run's own page MUST offer no controls that advance or alter the run. Every such action belongs to the node's conversation page, where what is being decided is in front of the developer.

#### Scenario: the run's own page offers no controls
- **GIVEN** a run mid-flight
- **WHEN** its page is read
- **THEN** it describes where the run is, what it produced and what it reads, and offers nothing that advances or alters it

### Requirement: Keep templates and runs as separate surfaces
Templates and runs MUST be separate surfaces in the web UI: a template is a resource and MUST be reached where the other resource kinds are, and a run is operational state and MUST NOT be. Neither may be reachable only through the other.

#### Scenario: a template is found where the other resources are, and a run is not
- **GIVEN** the web UI
- **WHEN** the developer looks for the shape of work as opposed to a delivery of it
- **THEN** the template is listed among the vault's resources and the run is not, and neither list is reachable only through the other

### Requirement: Derive stage and task keys from their names
The template editor MUST NOT ask the developer for a stage's or a task's key. A key is an identity the engine reads no meaning from ("Attach no behaviour to a stage key"), so it MUST be derived from the name and made unique.

#### Scenario: the editor never asks for an identifier it can derive
- **GIVEN** the template editor, on the map and in either dialog
- **WHEN** the developer authors a stage and a task
- **THEN** no key is asked for, and the keys that were stored are slugs of the names

### Requirement: Show a template as its shape beside the stage being edited
The template editor MUST show a template as its SHAPE — every stage in the order it runs — beside the tasks of the one stage being edited, and MUST keep a stage's and a task's own fields behind opening that stage or task. A run MUST show its own stages and tasks the same way, because it is the same shape with state on it.

#### Scenario: the editor shows the whole flow beside the one stage being edited
- **GIVEN** a template of three stages, each with tasks
- **WHEN** the editor is opened
- **THEN** every stage is listed in the order it runs, the tasks of one stage are shown and no other stage's are, and a task's fields appear only when that task is opened

### Requirement: Save each template edit as it is made
The template editor MUST write each edit as it is made and MUST NOT hold unsaved state. A stage's and a task's fields are saved from the dialog that holds them; adding, reordering and deleting save themselves.

#### Scenario: the editor has no save button of its own
- **GIVEN** the template editor
- **WHEN** it is read
- **THEN** there is nothing to save and nothing to discard, because each edit was written as it was made

### Requirement: Refuse new runs from a disabled workflow at the daemon
A disabled workflow MUST start no new runs, and the refusal MUST come from the daemon rather than from one client's list — a rule that lives only in the web UI is not a rule. Runs already created from it MUST be unaffected: they froze their own snapshot ("Freeze the template when a run is created"), so switching a workflow off retires it from the menu and does not reach into work already under way.

#### Scenario: a disabled workflow starts no new runs
- **GIVEN** a workflow that is switched off and a run already created from it
- **WHEN** a new run is asked for from that workflow
- **THEN** it is refused by the daemon, and the run already going is unaffected

### Requirement: Name what a mounted external reference points at
A mounted external reference MUST be reported with what it points at — Confluence, Jira, a Google doc — when that can be recognised from its address, and with nothing when it cannot. The node's context MUST carry it, so that "go and read this" resolves to one tool rather than a guess. It MUST be derived on read rather than stored, so a reference mounted before its provider was recognisable is recognised without a migration.

#### Scenario: a mounted link tells the task which tool opens it
- **GIVEN** a run with a Confluence link and an ordinary web link mounted
- **WHEN** a node opens
- **THEN** the first is named as a Confluence page and the second is named as nothing but a link, so the task reaches for a tool only where one was identified

### Requirement: Keep the developer's own notes in a run's context
The developer MUST be able to write a note of their own into a run's context, in markdown, and to keep editing it for as long as the run lives. A note MUST be stored as a file under the run's own directory and listed to every task as the developer's own words; an image pasted into one MUST be stored with the run and MUST be displayable, which the text preview cannot answer for.

#### Scenario: a note the developer wrote is part of the run's context
- **GIVEN** a running run
- **WHEN** the developer writes a note into it and later changes their mind about what it says
- **THEN** the note is a markdown file under the run's own directory, it is listed to every task as the developer's own words, and the rewrite keeps the name the tasks already know it by

### Requirement: Edit a run's title and description as labels
A run's title and description MUST be editable for as long as the run exists, on the run's own page and through the command line. They are LABELS: the title is typed before the first task has opened, when the developer knows least about the work, and a label that cannot be corrected makes a list of forty runs unreadable. Editing one MUST NOT append an event, MUST NOT carry the run's version and MUST NOT touch the run's status, stage or position — those are folded from the log and only the engine writes them ("Rebuild a run from its event log"). A blank title MUST be refused, and a run this machine does not advance MUST refuse the edit like every other change to it ("Advance a run only on the machine that owns it").

#### Scenario: a run is renamed after the work has shown what it is
- **GIVEN** a run created with a hurried title and no description
- **WHEN** the developer rewrites both on the run's own page
- **THEN** the run carries the new words, its status, stage and position are exactly as they were, its version has not moved, and its event log has gained nothing

### Requirement: Choose a task's agent, model and effort before it starts
The developer MUST be able to choose which agent runs a task, on which model and at which reasoning effort, BEFORE that task starts — the moment the choice is worth making, and the one moment no conversation exists to make it in. The choice MUST be recorded against the attempt rather than the task, so a retry given a stronger model leaves the earlier attempt's record saying what it actually ran on. An unset choice MUST defer to the task's own, and an unset task MUST defer to the agent's own configuration; clearing a choice MUST be possible and MUST mean deferring, not blanking. Once a task's turn is in flight the conversation MUST own these settings and the choice MUST be refused here, so that one setting has one writer.

#### Scenario: a task is given a bigger model before it runs
- **GIVEN** a task the run has not reached, whose workflow names no model
- **WHEN** the developer picks an agent and a model for it and the run reaches it
- **THEN** the task's conversation opens on that agent and that model, the choice is recorded against that attempt, and a retry may be given a different one without rewriting what the first attempt ran on

### Requirement: Read a run's files from the app, bounded
A file in a run's context MUST be readable from the app: an uploaded input and a produced artifact by their contents, a mounted collection by its own page, and an external reference by its address. Reading MUST be bounded — a path outside the run's own directory is refused, a long file is returned as its head and says so, and bytes that are not text are reported as such rather than rendered.

#### Scenario: a file in the run's context can be read from the app
- **GIVEN** a run with an uploaded input and an artifact a task wrote
- **WHEN** the developer opens either from the run's context
- **THEN** its contents are shown, and a path outside the run's own directory is refused rather than read

### Requirement: Let the developer speak to a task at any point, in one place
The developer MUST be able to say something to any task at any point in its life, in ordinary words, in one place. Before the task starts, what they say MUST be queued onto the attempt it opens with and reach its brief; while it waits for review, it MUST carry that attempt on; once it has finished, it MUST open the task's next attempt within the ceiling. A task whose turn is in flight or whose approval is pending MUST say so rather than accept it silently.

#### Scenario: a task can be told something before it starts
- **GIVEN** a task the run has not reached yet
- **WHEN** the developer writes what it should do
- **THEN** what they wrote is carried on the attempt the task opens with and is part of the brief it reads

#### Scenario: talking to a finished task reopens it
- **GIVEN** a task that has completed
- **WHEN** the developer says it is not right
- **THEN** the task's next attempt opens carrying what they said, bounded by the same ceiling as every other loop

### Requirement: Offer no run controls on a task's page
A task's page MUST offer no control that advances or alters the run. Retrying, redirecting and correcting are said in the task's conversation, where what is said also reaches every later task ("Open every task with the same four parts"). Deciding an approval is the one exception ("Show an approval on its task's conversation and through a bound channel"), because a payload cannot honestly be approved by typing into a composer.

#### Scenario: a task is driven by talking to it, not by buttons
- **GIVEN** a task's conversation page, whatever the engine says that task allows
- **WHEN** it is read
- **THEN** it offers no control that advances or alters the run, and what it offers instead is the composer
