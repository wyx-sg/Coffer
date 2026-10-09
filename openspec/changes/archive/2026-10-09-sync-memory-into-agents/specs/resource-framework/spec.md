## MODIFIED Requirements

### Requirement: Address every resource by an immutable uid through one kind-agnostic surface
The system MUST model every managed thing as a *resource* identified by an immutable,
opaque **`uid`** ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)),
and MUST expose one kind-agnostic REST surface, `/api/v1/resources*`, to list, read, update,
enable, disable and delete any of them without the caller knowing the kind. Every route and
every stored reference from one resource to another MUST address the uid. A uid MUST be minted
once and never reused, and MUST be the same value on every machine that holds the resource, so
that two machines can tell "the same thing" from "a different thing with the same name" without
asking each other.

The lifecycle controls of the web UI are exactly these routes: list, read, update — the
description, `title` on a kind that carries one ("Carry an optional editable title on the kinds that
have one"), and the kind's own fields — enable, disable and delete, plus the reach pair ("Carry a
per-agent reach on every resource"). Creating is not one of them: a kind registers through its own
seam (see "Keep creation a per-kind seam"). A request a kind does not support MUST be refused rather
than ignored (see "Keep creation a per-kind seam" and "Carry a per-agent reach on every resource").

A kind MAY declare that its resources cannot be disabled — `knowledge` and `agent` do.
Every resource of such a kind MUST read as enabled, whatever its stored reach holds (a resource disabled before its kind became non-toggleable reads enabled from then on), and enabling or disabling one through the
kind-agnostic surface MUST be refused with `RESOURCE_NOT_TOGGLEABLE` (409), changing
nothing. The resource read carries the kind's answer as `toggleable`, so a surface can
leave the switch out rather than offer one that is refused.

A kind exists only because the composition root registered it; a request naming an
unregistered kind MUST be refused rather than bringing one into being.

#### Scenario: the kind-agnostic surface serves every kind
- **GIVEN** resources of more than one registered kind exist,
- **WHEN** the user lists resources without naming a kind, reads one back by its uid, then disables and re-enables it,
- **THEN** every kind's resources appear in the one list, each carrying its uid, kind, name, title, config, reach and enabled flag,
- **AND** the enable/disable round trip is served by the same route for every kind, and each step is audited.

#### Scenario: every kind answers the same lifecycle routes
- **GIVEN** one registered kind that can be disabled, supports reach and carries a title, and one that does none of these
- **WHEN** each resource is read with `GET /api/v1/resources/{uid}`, given a new description with `PATCH /api/v1/resources/{uid}`, and sent a non-null scope with `PUT /api/v1/resources/{uid}/scope`, a title and `POST /api/v1/resources/{uid}/disable`
- **THEN** both kinds answer the read and the description update through the same routes, and the kind that supports no reach, carries no title or cannot be disabled refuses that request and changes nothing
- **AND** the first kind's disable changes it through the kind-agnostic route and is audited

#### Scenario: a non-toggleable kind refuses to be disabled
- **GIVEN** a `knowledge` collection and an `agent`
- **WHEN** each is disabled through `/api/v1/resources` and read back
- **THEN** both requests are refused with 409 `RESOURCE_NOT_TOGGLEABLE`
- **AND** both still read back enabled, with `toggleable` false
- **AND** an agent whose stored reach says off, left from before the kind was non-toggleable, reads back enabled

### Requirement: Keep creation a per-kind seam
Creation is a per-kind seam and MUST stay one. The kind-agnostic create route MUST
accept only kinds that declare themselves creatable through it, and MUST refuse a kind
that owns a creation invariant beyond config validation — a skill's master folder, an
agent's on-disk detection — so that such a kind is registered through its own surface,
which can hold that invariant. A kind that is created only by the system MUST offer no creation
at all. A generic create would have to guess a config shape it cannot know, which is why creation stays the kind's own. What this spec owns is everything that
happens to a resource once a kind has made one.

#### Scenario: refuse a generic create for a kind that owns its creation
- **GIVEN** a registered kind that declares it is not creatable through the kind-agnostic surface,
- **WHEN** a registration for that kind arrives on the kind-agnostic create route,
- **THEN** it is refused as a conflict with the code `GENERIC_CREATE_NOT_ALLOWED`, and no resource file and no audit entry is written,
- **AND** that kind is created only through a surface of its own that holds its invariant.

### Requirement: Treat a resource's name as a mutable label
A resource's `name` is a **label**, unique within its kind and nothing more. For every kind
except those that declare their name fixed, renaming MUST be an ordinary field of the
kind-agnostic update — at the same level as editing a description — and MUST NOT require any other record to be
rewritten, because nothing else holds the name: the resource keeps its identity, its config,
its reach, its enabled state and its audit trail, with the entries written before the change
still saying what it was called then. The same name rules MUST apply to a rename as to a
registration, a collision within the kind MUST be refused before anything moves, and renaming
to the name it already has MUST change nothing and record nothing. The resource's own file,
which is named after the resource, MUST move to the new name in the same vault commit that
records the rename ([vault-storage](../vault-storage/spec.md) "Identify a resource by the uid inside its file"). A kind that keeps an on-disk
artifact named after the resource MUST be given the chance to move it, with a failure aborting
the rename rather than leaving the two disagreeing: a file that cannot be written is refused
before the hook runs, and a write that fails after it asks the kind to move the artifact back.

A kind whose name is visible outside Coffer MUST declare its name fixed, because agents and the
files they read quote that name. Today these are `mcp_server`, whose name prefixes every tool
name an agent sees, and `skill`, whose name is the folder an agent loads it from. A kind MAY
also derive the name from the resource's config, which fixes it too: `agent`, whose name is its
type's ([agent-registry](../agent-registry/spec.md) "Keep one agent per type, named by it"), and
registration MUST refuse any other name for such a kind as a validation error. For a fixed-name
kind, an update whose `name` differs from the current one MUST be refused as a conflict with the
code `NAME_IMMUTABLE`, whichever surface it came through, with nothing moved and nothing
audited. The refusal message MUST say that the resource has to be deleted and registered again
under the new name, and MUST name what a re-registration resets — or, for a derived name, that
the name is the resource's type. None of these kinds carries a title ("Carry an optional
editable title on the kinds that have one"): the fixed name is what every surface shows.

#### Scenario: renaming a resource is an ordinary edit
- **GIVEN** a resource of a kind whose name is not fixed, with a reach set, a secret cited by its
  config, and rows in a table its kind owns,
- **WHEN** the user changes its name through the kind-agnostic update,
- **THEN** the resource is the same resource — its identity, its reach, its
  secret and its kind-owned rows are untouched — and its audit trail comes
  back whole, with the rows written before the change still saying what it was
  called then,
- **AND** a name another resource of that kind already holds is refused with
  nothing moved, as is a name the rules would have refused at registration, and
  submitting the name it already has changes nothing.

#### Scenario: a kind whose name is a directory moves it with the rename
- **GIVEN** a resource of a renamable kind that keeps an on-disk artifact named after it —
  a knowledge collection's directory,
- **WHEN** the user renames it,
- **THEN** the artifact is at the new name with its contents intact and is
  served from there,
- **AND** a rename the kind cannot carry out — something already occupies the
  destination — is refused with the resource and the artifact both untouched, rather
  than leaving a resource pointing at a directory that is not there or merging
  into one that was never its own,
- **AND** a resource file that cannot be written (an unsettled edit on disk) is refused before
  the artifact moves, and a write that fails after the artifact moved puts it back.

#### Scenario: a fixed name refuses a rename
- **GIVEN** a registered MCP server and a registered skill
- **WHEN** the user submits a different name for each through the kind-agnostic update
- **THEN** every attempt is refused as a conflict with the code `NAME_IMMUTABLE`, with a message saying to delete and register the resource again and naming what that resets
- **AND** each resource keeps its name, its on-disk artifact and its audit trail, and no audit entry is written

#### Scenario: a rename moves the resource's file in one commit
- **GIVEN** a resource of a renamable kind, filed as `resources/<kind>/old.json`
- **WHEN** the user renames it to `new`
- **THEN** one vault commit removes `resources/<kind>/old.json` and adds `resources/<kind>/new.json`, and the resource keeps its uid

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor — the originating surface (CLI / API / UI), `system` for the
daemon's own work, `sync` for a change applied from the sync remote, `human` for an edit a person or an agent made to
a vault file on disk that Coffer found and committed, a named background worker
such as `system:memory-sync-worker`, or a domain actor a kind names itself, such as `user`,
`channel`, an agent's name, or `agent` for a knowledge write whose session reported no agent. Every lifecycle change made
through any surface — REST, CLI, or a kind's own command — MUST appear in the audit log
with the originating actor, and no surface can mutate a resource without one. Entries
MUST be readable through the REST route, the Activity page and `coffer log audit`, filterable by kind, resource, event type and
time, and MUST carry both the resource's stable identity and the label it carried at
that moment, so a trail survives a rename while each row keeps saying what the resource
was called then. Filtering one resource's history MUST key on that identity and not on
the label: a label cannot tell a renamed resource from a deleted one whose name was
later taken, and rendering two objects' histories as one is a worse answer than a short
one. The event-type vocabulary is shared: this spec defines the resource and retention
events and every kind contributes its own, so one record answers "what happened" for the
whole vault rather than each kind growing a private log.

An entry's `details` MUST say what changed, not only that something did: a value that
changed carries its value before and after (a name, a scope, a switch, a retention period,
a provider), an action over several things names them or counts them (the agents, files,
skills or pages it touched), and an action with a cause the caller knows names it. A text
edit to a vault file Coffer writes or commits — a knowledge page, a skill
file — carries a unified diff of the edit, cut at 8 KB (UTF-8) with `diff_truncated: true`
and its size before the cut (`diff_bytes`). `details` MUST NOT hold a secret value: a
secret is named by its reference, and a resource's configuration passes its kind's
redactor first. Every audited event is also written to `daemon.log` as one `coffer.<event>`
line carrying the actor, the resource and the entry's `details`, cut at 2 KB with
`details_truncated: true`.

#### Scenario: audit lifecycle changes
- **GIVEN** the user performs any add / enable / disable / update / delete on a server or capability,
- **WHEN** they open the Activity page's audit tab or run `coffer log audit`,
- **THEN** they see one row per change with actor, timestamp, and a payload describing what changed.

#### Scenario: a rename and a knowledge edit say what changed
- **GIVEN** a skill renamed from `notes` to `journal`, and a knowledge page whose one line was edited
- **WHEN** the audit log is read
- **THEN** the rename's details carry `notes` before and `journal` after
- **AND** the edit's details carry a unified diff with the line removed and the line added

#### Scenario: the daemon log line carries the event's details
- **GIVEN** a retention period changed from 30 to 7 days
- **WHEN** `daemon.log` is read
- **THEN** its `coffer.retention_updated` line carries the actor, the table and both periods

### Requirement: Report the passes in flight in one cross-kind read
The system MUST answer, in one cross-kind read, which long passes this
daemon is running right now — each named by its kind, its target and when it started, and, for a run that works through several items one pass at a time, how many of them it has done of how many —
so that a surface can tell whether a pass is under way without every kind growing a
near-identical endpoint of its own. The read MUST start nothing, and the registry MUST
NOT outlive the process: a restart ends any pass it was running and the list comes back
empty, which is the truth rather than a lost record. Whether a pass runs on a timer at
all is internal-engine's; what a pass *does* is its own kind's. The read is served over
REST (`GET /api/v1/upkeep/runs`) and on the command line as the "passes in flight" section
of `coffer daemon status`, which prints the same list, says so when nothing is running, and
carries the list under `--json`.

#### Scenario: the daemon names the passes in flight
- **GIVEN** a long pass over one knowledge collection is running,
- **WHEN** any surface reads the in-flight list,
- **THEN** that pass is named with its kind, its target and when it started,
- **AND** a target absent from the list has no pass running, and the read starts nothing.

#### Scenario: the command line reads the passes in flight
- **GIVEN** passes over two knowledge collections are running
- **WHEN** the operator runs `coffer daemon status --json`, and again once both have ended
- **THEN** the first lists both passes with their kind, target and start time, oldest first,
- **AND** the second lists none, and the table form of `coffer daemon status` says that no pass is running.

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider` and `channel`.
`agent`, `mcp_server`, `skill` and `knowledge` carry none: each is shown by its fixed
name — a knowledge collection by its folder, with an editable description instead
([knowledge](../knowledge/spec.md) "Name a collection by its folder and edit its description in place")
— and a non-empty title for one MUST be refused as a validation error (422) on registration
and on update, with nothing changed. On a kind that carries one, the title MUST be editable
through the kind-agnostic update (`PATCH /api/v1/resources/{uid}`). An empty title MUST clear it. A title longer than 80
characters MUST be refused as a validation error with nothing changed. A title change MUST be
audited like any other update. The web UI MUST show the title in place of the name
wherever a resource is listed or shown when a title is set, and the name when it is not. The
title MUST be a key of the resource's own file, left out while it is empty, so it travels with
the resource to the user's other machines through vault-sync, and a
resource that arrives without one MUST keep its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource of a kind that carries a title, with no title
- **WHEN** a client sends `PATCH /api/v1/resources/{uid}` with the title "Team search" and then lists that kind
- **THEN** the list and the resource read carry "Team search" as the `title` beside the unchanged `name`, and the web UI shows the title where the name was shown
- **AND** the change is audited as an update, and the resource's name, uid, reach and enabled state are unchanged

#### Scenario: an over-long title is refused
- **GIVEN** a resource with a title set
- **WHEN** the user submits a title of 81 characters through the update route, and then an empty title
- **THEN** the first is refused as a validation error and the stored title is unchanged
- **AND** the second clears the title, and surfaces show the name again

#### Scenario: a kind without a title refuses one
- **GIVEN** a registered MCP server, a registered skill and a registered agent
- **WHEN** the user submits a title for each through the kind-agnostic update, and registers an MCP server with a title
- **THEN** each is refused as a validation error (422) and nothing is stored
- **AND** each of those resources is still shown by its fixed name

### Requirement: Converge what Coffer writes outside its database with one reconciler
Everything Coffer keeps true outside its own files — its MCP entry in each
agent's config, the skill links it delivers, a provider connection's projection
into an agent's settings — MUST be converged by one
level-triggered reconciler ([ADR](../../../docs/decisions/one-level-triggered-reconciler-compares-parameters.md)).
Each target MUST state the items it wants with their full parameters, computed
from Coffer's own state, and read what is there into the same shape; a pass
MUST pair the two and treat an item whose parameters differ as drift exactly as
it treats a missing one — presence is how an entry is found, never how it is
judged current. Each target MUST decide every difference by its own direction
policy: repair it, report it, or report that it cannot be repaired right now
(blocked); a difference the policy does not repair MUST be reported, never
written. A pass MUST run at daemon start before the daemon reports ready, every
60 seconds, early for the targets that follow a kind when a resource of that
kind is written, and on demand after a user's own write, a sync round that applied
changes and a feature switch; a lost early start costs at most one period and never
correctness. A target that raises MUST be reported and skipped while the pass
goes on, and a write that raises MUST fail only its own item. Passes MUST NOT
overlap, and a multi-step change a service makes (a provider switch, a sync
round's apply) MUST be able to keep passes out until it is done.

#### Scenario: a changed parameter is drift and is repaired
- **GIVEN** an agent whose Coffer entry is present but carries a parameter this build no longer writes — an MCP entry with a shim path an upgrade moved
- **WHEN** a reconcile pass runs
- **THEN** the item is reported as a modification naming the changed parameter and rewritten to the current parameters, every entry that is not Coffer's is left as it was, and the next pass finds nothing

#### Scenario: a target that fails is reported and the pass goes on
- **GIVEN** two targets, one of which cannot read its state
- **WHEN** a pass runs
- **THEN** the failing target is reported with its error and the other target's drift is repaired

#### Scenario: a write brings the next pass forward
- **GIVEN** a target that follows the `agent` kind and one that does not
- **WHEN** an agent resource is written
- **THEN** a pass runs for the first target within moments rather than at the next period, and the second target is not visited by it

### Requirement: Report what needs a person across every kind
`GET /api/v1/attention` MUST list what needs a person
now, from every source whose experimental feature is on: the reconciler's
drift that a pass could not fix, MCP servers whose last test failed (a server
whose key the upstream refused reads `mcp_key_rejected` and offers
`replace_key`, which opens the server's page where the key is replaced),
whose launcher is missing or whose cited secret is absent, agents whose program is
missing, whose connection is partial or who are not connected, a sync stopped on
a conflict or holding deletions, channels reconnecting, disconnected or not
running, model provider connections that an agent or Coffer's speech to text
runs on whose endpoint does not answer (`provider_unreachable`, offering
`check` through `POST /api/v1/providers/{uid}/check`, run in place) or refuses
the key (`provider_key_rejected`, offering `replace_key`, which opens the
connection's page) — read from the kept health verdict
([provider-switching](../provider-switching/spec.md) "Know each connection's
health without opening it"), only while `models` is on — and commands a skill
requires that are missing, older than a skill's minimum or not logged in (kind
`cli`, the command as the uid). Each item MUST carry its kind, the resource's uid and title, a stable
reason code with one sentence, a severity (`error`, `warning`, `info`), when
the condition was first seen where that is known, and exactly one action: a
verb and the REST route and body the kind's own page uses — the list has no
write of its own. Every item MUST also carry `handoff` (Principle IV,
AI-Native): the same prompt the kind's own page offers when its fix is a chore
for an agent — and its reason sentence MUST then name no command to run —
otherwise a prompt the daemon writes from the item's title, reason and action,
carrying no secret. Any item MAY be ignored on this machine by its stable key
([web-ui](../web-ui/spec.md) "Let the user ignore any item on Overview").
The route MUST serve each item's prompt as `handoff.prompt`, the text the web UI copies. A source that fails MUST be reported beside the others'
items, and the answer MUST count the items per kind.

#### Scenario: each item carries one action from its kind's own page
- **GIVEN** an MCP server whose last test failed and a partially connected agent
- **WHEN** the user reads the attention list
- **THEN** the server's item offers `test` through `POST /api/v1/resources/mcp_server/{uid}/test`, the agent's offers `connect` through `POST /api/v1/agents/{uid}/coffer-connection`, errors sort before warnings, and the counts name one item for each kind

#### Scenario: a rejected key is its own attention item
- **GIVEN** an enabled HTTP server whose last test failed with `auth_rejected`
- **WHEN** the user reads the attention list
- **THEN** the server's item reads `mcp_key_rejected` with the reason "Every call is rejected with 401 Unauthorized. The API key looks revoked.", offers `replace_key`, and still carries the diagnosis `handoff`

#### Scenario: every item carries a hand-off prompt
- **GIVEN** an attention item whose kind writes its own hand-off, and another whose source gives none
- **WHEN** the attention list is read
- **THEN** the first carries its kind's `handoff.prompt` and the second a prompt written from its title, reason and action, and the web UI copies exactly each text

#### Scenario: a failing source does not hide the others
- **GIVEN** one source that raises and one that has an item
- **WHEN** the attention list is read
- **THEN** the item is listed and the failing source is reported with its error

#### Scenario: a switched-off feature's signals are left out
- **GIVEN** an attention source tagged with a registered experimental feature that is switched off, holding an item it would report
- **WHEN** the attention list is read
- **THEN** that source's item is not listed and the source is not reported as failing

#### Scenario: a required command that needs attention is listed
- **GIVEN** a skill requiring `gh` with minimum `2.40` and `gh 2.30` installed
- **WHEN** the attention list is read
- **THEN** it carries one `cli` item for `gh` with reason `cli_outdated` whose action is `check` through `POST /api/v1/clis/gh/check`
- **AND** once `gh` is current, present and logged in, no `cli` item is listed

#### Scenario: a connection an agent runs on that fails is listed
- **GIVEN** Claude Code runs on connection A, whose verdict is `unreachable`, and connection B, which nothing runs on, whose verdict is `key_rejected`
- **WHEN** the attention list is read
- **THEN** it carries one `provider` item for A with reason `provider_unreachable` whose action is `check` through `POST /api/v1/providers/{uid}/check`, and none for B
- **AND** once A's verdict is `key_rejected`, its item reads `provider_key_rejected` and offers `replace_key`

### Requirement: Offer every management operation on the command line
Every management operation a person can do on a web UI page or in the desktop
app MUST have a `coffer` command, so an agent can do it as well: creating,
reading, changing and deleting resources, switching them on and off, their
reach, connecting agents, model providers, MCP servers, custom tools, channels,
managed CLIs, skills, knowledge and memory management, secrets and approvals,
activity, sync and settings. A command MUST call the same REST route the page
calls, so the daemon's validation, audit and lifecycle are the same whoever
acts; it MUST NOT reimplement a route or reach the vault's files, `runs.db` or
ciphertext directly. Exempt are only plain file contents a spec declares
directly readable or editable — knowledge documents, a skill's
files, an agent's own config and native-memory files — which an agent reads and
edits with its own tools, and acts whose whole meaning is the window a person
sits at (a native folder picker, opening a file in an editor, terminal or
Finder). Registering, binding, reach, delivery and history restore stay
commands even where what they manage is a file. A command that needs a
person's presence (approving, revealing, writing a key backup) MUST hand that
step to the desktop app's own presence check.

Every such command MUST be recorded in one registry in the CLI package with
the UI operation it stands for and the route(s) it calls; the few commands that
stand for no UI operation (a program runs them, they work while the daemon is
down, or a hand-off names them) are recorded with that reason instead. A test
MUST compare the registry with every route the web UI calls and every command
the desktop shell exposes, and fail on a route or shell command with no command
and no recorded exemption; MUST run every declared command against a recording
transport and assert it calls the route it records; and MUST assert every leaf
of the live command tree is either recorded or has a reason, and every group's
`--help` renders. The coverage table — UI operation, route, command, acceptance
test — is generated from the registry into the CLI reference, in English and
Chinese.

Every command MUST share one contract: `--json` prints the daemon's answer on
standard output and a failure as `{"error": {"code", "message", "details"},
"exit_code"}` on standard error; a body is read from `--data '<json>'`,
`--data @file` or `--data -` (standard input), with repeatable `--set
key=value` merged over it; nothing prompts unless standard input is a terminal
and the command asks for a secret; the daemon's error codes pass through
unchanged; and the exit codes are 0 ok, 2 usage, 3 daemon unreachable, 4 not
found, 5 conflict, 6 invalid input, 7 upstream test failed, 8 secret, 9 approval
pending (with the approval ids and the command that approves them), 10 git
needed, 11 presence not confirmed, 12 desktop app unavailable and 13 a wait
ran out, with 1 for any other failure (a switched-off feature among them). An
operation that runs on after its request returns offers a status command and a
way to wait for its result.

The contract MUST hold on every path, not only the daemon's answer: a name the
command resolves to nothing, a refusal read by an older hand-written reader, and
a daemon that cannot be started each print the same `--json` error envelope. A
file or standard input that cannot be read or is not UTF-8 text exits 6 with
`CLI_INVALID_INPUT` before anything is sent or started. An answer that waits on
approvals exits 9 whether it names them as a list (`pending_approvals`,
`approval_ids`), as `pending_approval_id`, or as an `approval_id` beside a
`pending` state. A test command whose answer reports `ok: false` prints the
whole answer and exits 7. `coffer --verbose` adds the request behind a daemon's
refusal (method, path, status; never a header) to the text or the envelope.
Every management command MUST be reachable from the visible help; only a
command a program runs (`proxy token`) is hidden. The rule is policy over every spec
and is stated as such in [`.agents/openspec.md`](../../../.agents/openspec.md);
this requirement is where it becomes testable, because the assertion runs over
the entire command tree across every spec and so has no narrower home.

#### Scenario: the command line covers every web UI and desktop operation
- **GIVEN** the routes the web UI calls through its typed client and the desktop shell's commands
- **WHEN** they are compared with the CLI's registry
- **THEN** every route has a command or a recorded exemption naming a plain file or the window, and every desktop command has a command or a reason
- **AND** an exemption for a route the web UI no longer calls fails the comparison

#### Scenario: a route the web UI calls without a command fails the test
- **GIVEN** a route the web UI starts calling that no command records
- **WHEN** the comparison runs
- **THEN** it fails naming the route

#### Scenario: every command is a UI operation or has a recorded reason
- **GIVEN** the CLI's live command tree
- **WHEN** it is read beside the registry and the recorded reasons
- **THEN** every leaf is either a recorded UI operation or carries `program`, `offline`, `hand-off` or `no-ui` with a one-line why, never both
- **AND** every group's `--help` renders

#### Scenario: each declared command calls the route it records
- **GIVEN** every command declared over one route
- **WHEN** each is run against a transport that records its requests
- **THEN** each sends the method and route it records, with its body from `--data` and `--set`

#### Scenario: a command takes JSON from a file or stdin and fails with a stable code
- **GIVEN** a command that takes a body
- **WHEN** it is run with `--data -` on standard input, with `--data @file`, with JSON that does not parse, and against a daemon answering 404 with `--json`
- **THEN** the first two send the body read, the third exits 6 with the code `CLI_INVALID_INPUT`, and the last exits 4 printing the daemon's error envelope and the exit code as JSON on standard error

#### Scenario: every failure path keeps the JSON error contract
- **GIVEN** a command run with `--json`
- **WHEN** a name it resolves matches nothing, an older reader's route refuses, a `--data @file` is not UTF-8, or a test's answer says `ok: false`
- **THEN** the first three print one `{"error", "exit_code"}` object on standard error and exit 4, 6 and 6 with nothing sent for the file, and the last prints the answer and exits 7

#### Scenario: a single pending approval exits 9
- **GIVEN** a change whose answer names one approval as `pending_approval_id`, or as `approval_id` beside a `pending` state
- **WHEN** the command that made it ends
- **THEN** it exits 9 printing `next: coffer approval approve <id>`

#### Scenario: management commands are visible in help
- **GIVEN** the CLI's live command tree
- **WHEN** each registry command is looked up from the root help
- **THEN** no management command sits under a hidden group or is hidden itself, and the only hidden leaf is the program-run `proxy token`

#### Scenario: a plain file is read with the reader's own tools
- **GIVEN** a plain file that its owning spec declares directly readable or editable
- **WHEN** a person or an agent needs it
- **THEN** it is read and edited with their own tools at the path the web UI, the spec or the hand-off prompt names, and no command reads or writes its content
- **AND** `coffer path logs` and `coffer path skill-data` still say where the log files and a skill's working files are

#### Scenario: a kept command surfaces the daemon's errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** it reaches a command that calls the daemon,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` adds the request behind it (method, path and status)
