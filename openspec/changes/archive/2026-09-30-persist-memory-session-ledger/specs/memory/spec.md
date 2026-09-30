## MODIFIED Requirements

### Requirement: Retrieve the notes a prompt names
For every prompt the developer sends a hook-driven session, Coffer MUST rank the notes of the session's repository partition and of `global` against the prompt — each note's title, description, search terms and body — with a lexical ranker (BM25, CJK text as bigrams), and MUST add to the session the **top three** notes that score at or above a **relevance floor** and that this session has not already been given. Each is delivered as the absolute path of its file and its substance (see "Word delivered notes as provenance plus fact"), and the whole delivery MUST stay within **1,500 UTF-8 bytes**. A prompt of fewer than three words, or a bare nudge such as `continue`, `ok` or `继续`, MUST retrieve nothing. What a session was already given is remembered per `session_id` — the id the agent hands its hook, never a process id — and survives a daemon restart (see "Remember what a session was given across daemon restarts").

The ranking index is derived: it is held in memory, rebuilt from the note files when a partition's `notes/` changes, and never written. Nothing chunks or embeds a note.

#### Scenario: a prompt brings in the notes it names
- **GIVEN** a repository partition holding a note about running `make verify` under Node 20 and unrelated notes, and a `global` partition
- **WHEN** a session opened in that repository sends the prompt "why does make verify fail with undici AbortSignal under node"
- **THEN** the hook answers with `additionalContext` naming the Node 20 note's absolute path, at most three notes in all, every one scoring at or above the floor
- **AND** the text is at most 1,500 UTF-8 bytes

#### Scenario: a short or trivial prompt retrieves nothing
- **GIVEN** a partition whose notes would match the words of the prompt
- **WHEN** the session sends `继续`, then `ok`, then a two-word prompt
- **THEN** the hook prints nothing for each, and no delivery is audited

#### Scenario: a note already delivered in the session is not delivered again
- **GIVEN** a session that was given a note for one prompt
- **WHEN** the same session sends a prompt that ranks the same note first, and a second session sends that prompt too
- **THEN** the first session is not given the note again, and the second session is

## ADDED Requirements

### Requirement: Remember what a session was given across daemon restarts
What each session was given — the notes delivered at its prompts, and the triggers that held or annotated one of its commands — MUST survive a daemon restart, so a restart neither brings a note into a session again nor lets a trigger hold a second command in it. The record MUST be the audit log's delivery fires (see "Audit every delivery fire"), which already name each fire's session, notes and trigger: the daemon MUST rebuild the per-session record from the fires of the last **seven days** before it answers its first prompt or command, and MUST add no table for it (see "Add no table of its own"). A session idle for longer than that is treated as new. A rebuild that fails MUST be logged and leave the record empty rather than stop delivery.

#### Scenario: a daemon restart gives a session nothing twice
- **GIVEN** a session that was given a note at a prompt and had a command held by a trigger, and then the daemon is restarted
- **WHEN** the same session sends the same prompt and runs the same command, and a new session does both too
- **THEN** the first session is given nothing and its command passes
- **AND** the new session is given the note and its command is held
