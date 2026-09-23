## MODIFIED Requirements

### Requirement: Carry channel pairings as platform identity
Channel peer pairings MUST travel as **platform identity** — chat id, sender
id, display name and pairing time, keyed by the channel's uid — because a channel that moved to
another machine without its pairings would make the owner re-pair from their
phone on every rebind.

#### Scenario: a channel's pairings travel with it
- **GIVEN** a paired `channel` on one machine,
- **WHEN** the two machines converge and the channel is rebound to the other,
- **THEN** the owner's pairing is present on the machine that now runs it and no
  re-pairing is asked for, and the conversation pointer each machine holds is
  its own.

### Requirement: Keep the active conversation pointer local
The active conversation pointer MUST NOT travel, and neither MUST the agent a
chat's thread has stuck to. Conversations are machine-local, and a published
pointer would name a conversation the other machine does not have; the sticky
agent names an agent installed on this machine, which the other machine may not
have either.

#### Scenario: the active conversation pointer is not published
- **GIVEN** a paired chat whose pairing has an active conversation on this machine
- **WHEN** the pairings state area is exported
- **THEN** the exported document carries the chat's platform identity
- **AND** it names no conversation

### Requirement: Withhold derived output in both halves
**Derived output MUST NOT converge, in either half.** A resource whose bytes
each machine regenerates for itself — from material that already converges
plus that machine's own machine-local state — MUST be withheld from the tree and
MUST be ignored when a document for it arrives. This is the rule of "Let a kind
withhold its own rows" at the granularity of one **row**: a kind that otherwise
converges MUST be able to declare that a particular row does not, and that
row declaration MUST live on the kind rather than as a name the sync layer
recognises. The master-folder half is a set of tree paths held in the sync
layer, because the sync layer may not import the kind; a contract test MUST pin
that set to the kind's own spelling of the name, so the two cannot drift apart
in silence. The exporter and the applier MUST both consult both halves.

Coffer's own generated skill `coffer-guide` is the case this exists for. Its
text is rendered locally from the running build, the knowledge files (which
converge on their own) and **which collections this machine has enabled** — and
`enabled` is reach, which "Keep reach machine-local" keeps machine-local. So two
machines holding identical files still render different bytes, each correct
where it is. Converging it had each round overwrite the other machine's master
folder and its resource row (whose `version_hash` is that folder's digest), the
overwritten machine re-render at its next boot or curation pass, and the
exchange repeat: a commit and an audit event per tick on both machines, forever,
over an artifact neither machine reads from the other. **Both halves MUST be
withheld**: the master folder under `skills/`, which "Converge knowledge files
and the skill store" otherwise mirrors, and the resource document, which
"Converge resource definitions as serialized documents" otherwise publishes.

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** two machines holding the same knowledge files, one with a
  collection enabled and the other with it disabled, so each has rendered its
  own `coffer-guide` master folder and registered its own `skill:coffer-guide`
  row,
- **WHEN** both converge, and then converge again,
- **THEN** neither machine's `SKILL.md` or row has been changed by the other,
  the remote carries neither `skills/coffer-guide/` nor
  `resources/skill/coffer-guide.yaml`, the second round publishes and applies
  nothing, and the knowledge files and an ordinary imported skill converge as
  usual.

### Requirement: Keep the working tree outside the vault
The working tree defaults to `~/.coffer/sync`. Every round mirrors the vault
into it and may `reset --hard` it, so it MUST NOT be at, inside or above any
vault directory (knowledge, skills, memory), nor at or above `~/.coffer` itself;
inside `~/.coffer` only the default location is accepted, and a relative path
MUST be refused.

#### Scenario: a working tree pointed inside the vault is refused
- **GIVEN** a request to configure the working tree at a knowledge directory, or
  at `~/.coffer` itself, or at a relative path,
- **WHEN** the remote is configured over REST with that working tree,
- **THEN** each is refused with the reason named and no repository is created.

### Requirement: Keep machine identity across reinstalls
`machine_id` MUST survive reinstalling and uninstalling Coffer. A machine that
comes back under a new identity becomes a ghost: it rejoins as a stranger, its
old descriptor lingers in the registry with nobody to update it, and anything
that named it — the curation owner, its own recovered pointer — silently stops
meaning this machine.

#### Scenario: a machine identity survives reinstalling Coffer
- **GIVEN** a machine whose `~/.coffer` is deleted and Coffer reinstalled, on a
  host that exposes a stable identifier,
- **WHEN** it adopts the remote again,
- **THEN** it returns under the same machine id and its descriptor is updated
  rather than duplicated, so it rejoins as itself rather than as a stranger.

### Requirement: Write only this machine's descriptor
Each machine MUST write exactly one document, at `machines/<machine_id>.yaml`,
and MUST write no other machine's. Every machine owning a disjoint path is what
makes these documents unable to conflict.

#### Scenario: the machine registry shows every machine and cannot conflict
- **GIVEN** two machines that have both converged,
- **WHEN** the machines table is read on either,
- **THEN** it lists both with their names, last converged day and whether each
  one's key matches this machine's, marks the local one, and the working tree holds one descriptor
  per machine with no merge conflict between them.

### Requirement: Scope names agents only
`scope` MUST name agents, by uid, and nothing else — `{ agents: [...] }`.
`null` means every agent, a list restricts to it, `[]` matches nothing and is
dormant, and an unknown agent uid is legal and simply never matches. There MUST
be no machine axis: reach is machine-local (see "Keep reach machine-local"), so a
machine already names the resources it activates by *holding* that scope, and
machine ids inside the scope would record the same fact a second time with two
ways to disagree.

#### Scenario: a scope names agents and nothing else
- **GIVEN** scopes of `null`, a list of agent uids, an empty list, and a list naming an agent that does not exist
- **WHEN** each is matched against the registered agents
- **THEN** `null` matches every agent, the list matches exactly its agents, the empty list matches none, and the unknown uid matches nothing without being refused
- **AND** a scope that carries a machine axis is refused

### Requirement: Snapshot before applying and roll back from it
Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative.

Step 4 MUST tag `L` as the pre-apply snapshot, whose tree is by construction the
vault's state immediately before the apply. Rollback MUST be the same machinery
run backwards — applying `M..L`. The most recent **ten** snapshots MUST be kept.
A rollback MUST NOT move the pointer: the reverted vault is an ordinary local
change, which the next round publishes to the remote. Moving the pointer back
would make the next round re-derive the diff just undone and apply it again.

#### Scenario: a round can be rolled back
- **GIVEN** a completed round that applied a diff,
- **WHEN** the user rolls it back,
- **THEN** the vault returns to the state the pre-apply snapshot holds and the
  pointer stays where it was, so the next round publishes the undo as an
  ordinary local change rather than re-applying the diff,
- **AND** a round that applied nothing here offers no Undo at all, because the
  snapshot it left is the state the vault is already in.

### Requirement: Run an unattended rewriter on one owner machine
A worker that rewrites vault content with no human approving the diff is safe on
one machine and unsafe on several. Two machines rewriting one corpus each merge
the same pair of documents into a *different* result, and git merges that
cleanly — both agree the originals are deleted, the two results are additions at
different paths — so the vault holds the same content twice with nothing
reported as a conflict.

An unattended rewriter of synced vault content MUST name **one owner machine**,
MUST run only on the machine that setting names, and MUST be a clean no-op on
every other. The owner MUST be **synced state**, so every machine agrees who it
is; the knowledge **curation** pass is the case that exists today and its owner
travels in the `internal-engine` state document that already carries its switch.
If the owner machine is off, no pass happens, which is the accepted trade for a
background nicety. The retention worker is exempt: it prunes the audit log, MCP
invocation records and conversations, none of which sync.

#### Scenario: tidy runs only on its owner machine
- **GIVEN** two converged machines with curation enabled and one of them named
  as the owner,
- **WHEN** the curation interval elapses on both,
- **THEN** a pass runs on the owner and is a no-op on the other, and the vault
  holds one rewritten document rather than two.

### Requirement: Never overlap a tidy pass and a round
A curation pass and a converge round MUST NOT overlap. Both write the vault and an
export taken mid-rewrite is a torn snapshot, so they MUST take the same lock. A
pass MUST additionally be skipped while a conflict or a pending confirmation is
outstanding, so a rewrite is never piled onto an unresolved divergence.

#### Scenario: a tidy pass and a converge round do not overlap
- **GIVEN** a curation pass in progress,
- **WHEN** a converge round starts,
- **THEN** the round waits for the pass to finish before it serializes the
  vault, so the exported tree is never a half-rewritten corpus.

### Requirement: Let an edit beat a tidy deletion
Where the owner's curation pass deleted a document another machine edited, the **edit
MUST win**: the document survives with its edit, the deletion is dropped, and
the round MUST NOT report a conflict. A fresh edit is something a person or an
agent just decided; the deletion is a housekeeping judgement the next pass will
simply make again.

#### Scenario: an edit outlives a tidy deletion
- **GIVEN** a note the owner's curation pass merged away and deleted, and the same
  note edited on the other machine before it converged,
- **WHEN** the two meet in a round,
- **THEN** the note is still present with its edit, the deletion is dropped, and
  the round does not report a conflict.

### Requirement: Fold consecutive quiet rounds into one row
Consecutive rounds that changed **nothing** — no documents either way, no join,
no failure, no locked ref — MUST be folded into one row reporting the span and
the count. They are the majority, and one row each buries everything that
matters; they MUST NOT be dropped, because they are the only evidence that a
vault which stopped converging on Tuesday is not simply a vault with nothing to
do. A round that failed once is noise; a round that has failed every hour since
Tuesday is the answer.

Repeats that are not quiet MUST fold the same way, by outcome: consecutive
rounds that **failed**, and consecutive rounds **held** for confirmation, each
fold into one counted row, because an expired credential is ten identical
failures by morning and a held round is re-raised every hour until it is
answered — neither is more true for being printed ten times. A round that
applied or published documents MUST NOT fold, however many like it came before,
and rounds of different outcomes MUST NOT fold together. A lone round MUST stay
a row of its own. The **newest** round MUST never be folded: it is the state the
vault is in now and the only round that may carry Undo or a hold's answers.

#### Scenario: consecutive quiet rounds fold into one counted row
- **GIVEN** a runs history holding a stretch of consecutive rounds that changed nothing
- **WHEN** the Runs tab renders
- **THEN** the stretch is one row that reports its span and how many rounds it stands for
- **AND** every round in it is still reachable from that row

#### Scenario: repeated failures fold into one row and the newest round stands alone
- **GIVEN** a runs history whose newest three rounds failed the same way, preceded by a round that published a document
- **WHEN** the Runs table's rows are built
- **THEN** the newest failure is a row of its own, the two failures before it are one row counting two, and the round that published is a row of its own
- **AND** a stretch of consecutive rounds held for confirmation folds the same way beneath a newer round
