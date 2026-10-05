## MODIFIED Requirements

### Requirement: Hand conflicting files to an agent
Files both machines edited MUST be offered to the person's agent to merge, beside the two
answers and the editor: a round stopped on conflicts (both sides changed the file, or the merge git
made is not a valid document) and a join's differing files (both sides hold the file with no common
base) are the same question and share one set of routes and one prompt shape. The person hands over
every such file at once or one file; `POST /api/v1/sync/stop/handoff` (a join's:
`POST /api/v1/sync/join-choices/handoff`) takes the optional `paths`, writes each file's marked-up copy
under `derived/sync-conflicts/`, records the hand-off with its time, and returns the prompt. The body
may also carry the `agent` the hand-off was started on; sending the request
again with it attaches it without a second hand-off. The prompt states the goal and the
constraints only:

- the vault's path, to read for context;
- each file, when each machine changed it and the marked-up copy to write the merge into, which holds
  both versions between conflict markers;
- keep what each side added, and ask the person where the two contradict;
- write only those copies, leaving the vault's own files and its git history alone, because Coffer
  writes the merged file into the vault when the person marks it resolved.

It MUST carry no shell command, no secret's value and no secret file's path or contents.

An agent's merge is never an answer. A file handed over reads `handed_off` while its copy is still
git's marked-up text or holds a conflict marker, and `merged_by_agent` once the copy differs from it
and holds no marker, with `merged_at` the time the copy was saved; the person checks the merge in the
copy itself, opened in their editor, because Coffer shows no merged text or diff of its own. The file stays unresolved: **Mark resolved** is the `edited` answer, read from the
copy (`POST /api/v1/sync/stop/files/answer`, or a join's `POST /api/v1/sync/join-choices`, which commits
the merge as this machine's version for the next round to push), and it is refused while a conflict
marker is left, naming the line. **Back to two choices** (`POST /api/v1/sync/stop/files/discard`, a
join's `.../join-choices/discard`) forgets the copy, the hand-off and any answer for the file. Asking
again for a file already merged starts it over from the marked-up text. Nothing is written into the
vault until the round continues, or, for a join, until the file is answered.

An encrypted secret (`secret/*.enc`) MUST NOT be handed to an agent or hand-merged. It offers only
keep this machine's and take the other's: no editor copy is written, and a hand-off or an edited
answer for it is refused (`SYNC_SECRET_NOT_EDITABLE`). The prompt MAY say how many secret files wait
for the person. A same-name resource with another uid, one uid at two paths, and a file changed on
one side and deleted on the other are decisions, not merges, and are not handed over either.

#### Scenario: an agent's merge is shown to be checked and marked resolved
- **GIVEN** a round stopped because both machines changed the same lines of one document
- **WHEN** the files are handed to an agent, the agent writes its merge into the copy the prompt names, and the person marks it resolved and continues
- **THEN** the prompt names the vault, the file, both machines and the copy, and carries no shell command
- **AND** the file reads `handed_off` until the copy holds a merge, then `merged_by_agent` with the time of the merge while the round still has an unanswered file, and the file's versions carry no merged text or diff
- **AND** marking it resolved is refused while a conflict marker is left, and once it is accepted the merged text is what the vault holds after the round

#### Scenario: going back to two choices discards an agent's merge
- **GIVEN** a conflicting file an agent has merged, even one already marked resolved
- **WHEN** the person goes back to two choices
- **THEN** the copy is gone, the file is unresolved with no agent state, and keeping this machine's or taking the other's answers it
- **AND** handing it over again, or asking again after a merge, starts from the marked-up text

#### Scenario: a join's differing files are handed to an agent too
- **GIVEN** a machine that joined a remote holding a file that differs from this machine's, with no common base
- **WHEN** the join's files are read, handed to an agent, merged in the copy and answered `edited`
- **THEN** the file has the shape a stopped round's conflicting file has, with the same agent states
- **AND** the merge is committed as this machine's version, so the next round pushes it and the other machine takes it

#### Scenario: an encrypted secret in conflict offers only the two choices
- **GIVEN** a round stopped on a `secret/*.enc` file among its conflicts
- **WHEN** the person asks for an editor copy of it, hands it to an agent, or answers it "edited"
- **THEN** each is refused, the file is marked a secret that an agent may not merge, and the prompt carries none of its contents
- **AND** keeping this machine's or taking the other's version answers it


### Requirement: Show a conflict as a banner
A round stopped on conflicts MUST be shown as a card on the Status tab, above the rounds table, not
as a row. The card lists each conflicting file with its area, when each machine changed it and
whether it has an answer, and carries **Resolve conflicts** beside a hand-off that gives every
conflict to an agent at once. That card can be ignored, as the same item on the Overview, and returns
when the set of conflicts changes. The Resolve conflicts view MUST offer, for each file:

- keep this machine's, and take the other's, each saying what it changes here;
- **Open in editor** on the marked-up copy, after which the file reads "Editing in your editor" with
  **Mark resolved** and **Back to two choices** and shows nothing of the copy's text — the editor is
  where it is read — except for an encrypted secret;
- a hand-off that gives that one file to an agent (see "Hand conflicting files to an agent"), after
  which the file reads "Merged by an agent · check it" with **Open in editor**, **Mark resolved** and
  **Back to two choices**, and no diff of the merge.

There is no merge or text editor in the page.

The view says how many files are answered, lets the person leave the round for later, and offers
Continue round once every file has an answer. A hold is shown the same way, on its own card, leading
to the Review held deletions view with its two answers (see "Ask the user to confirm a tripped breaker"). So are a join preview and a join's
differing files, each on its own card; a join's differing files are listed and opened in the same
Resolve view as conflicts, titled for the join and ending in **Apply choices**.

#### Scenario: a conflict is shown as a banner above the runs
- **GIVEN** a vault whose last round stopped on a conflict
- **WHEN** the Status tab renders
- **THEN** a card above the rounds table names each conflicting file and leads to its answers


### Requirement: Ask the user to confirm a tripped breaker
A tripped breaker MUST hold the round before anything is checked out or pushed
and record which direction it is — **outgoing** (this machine's own commits
would remove the files from the remote) or **incoming** (the remote's would
remove them here) — and which files, grouped by folder with the share of each
folder they are. The person answers: **delete** them (the round continues and
applies or pushes the deletions) or **restore** them (the round continues and
the files are kept, pushed back if the remote had lost them). Both answers are
on REST (`POST /api/v1/sync/hold/confirm`, `POST /api/v1/sync/hold/restore`) and the Sync page,
whose Review held deletions view lists the files by folder and offers the two answers as two buttons —
**Keep the files** and **Delete N files** — each acting at once: the view itself names what a delete
removes, so no second dialog repeats it.

#### Scenario: an oversized deletion is held for confirmation
- **GIVEN** a machine that removed 22 documents of one folder, and the machine that receives that deletion
- **WHEN** each runs a round
- **THEN** the first is held outgoing and the second incoming, each listing the files by folder, with nothing applied or pushed
- **AND** confirming pushes the deletion, while restoring keeps the files here and pushes them back

#### Scenario: the held deletions view answers with one press
- **GIVEN** a round held on an outgoing deletion of 22 files in one folder
- **WHEN** the person opens Review held deletions and presses Delete 22 files
- **THEN** the view listed the files by folder before the press, no second dialog opened, and the hold was confirmed
- **AND** pressing Keep the files instead restores them at once

### Requirement: Restore to a revision without discarding later work
Going back to an earlier version of a vault file or folder MUST NOT discard
anything the vault gained since: restoring writes that version back as a new
commit — made by the person's agent through the hand-off of [vault-storage](../vault-storage/spec.md)
"Hand restoring an earlier version of a vault file to an agent", or by the person with git —
touching only the paths restored and never rewriting history, and the next round publishes it like
any other change.
Undoing what one round did is its rollback (see "Snapshot before checking out
and roll a round back from it").

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a file with two versions in the vault's history
- **WHEN** the first version's bytes are written back and committed as a restore
- **THEN** the file holds the first version's bytes as a new commit, and no earlier commit is rewritten

