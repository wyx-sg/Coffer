## MODIFIED Requirements

### Requirement: Keep every document's history and undo a pass as a whole
Every accepted write to a collection MUST be a git commit naming its writer ([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)). Until the vault is itself one git repository, the commits MUST be kept in a repository of the knowledge root's own — a hidden entry like every dot-prefixed one (see "Hide dot-prefixed entries except the inbox"), which vault sync never mirrors — shaped to fold into the vault's history once the vault is one. A person's save, restore, undo or delete names the user; material promoted on arrival names whoever submitted it — the user, or the agent named by the session's identity; a curation pass is **one commit** naming Coffer's curation and the item it curated — and, for an item an agent wrote, that agent, taken from the `knowledge_written` audit event of the submission; a change that arrives through vault sync names sync; and a change any other writer made in the tree — a person's own editor, an agent's file tools — MUST be committed as an edit on disk before Coffer's next commit, so it is never counted as Coffer's. A document's history MUST list its versions newest first with their writer and time, show the diff of each, and restore any version as a new commit. A pass MUST be undoable **as a whole**: undoing it puts every document it wrote or retired back exactly as it was before the pass, as one new commit naming the user, and does not put the item it consumed back in the inbox; when a later commit changed one of the same documents, the undo MUST be refused naming that document rather than overwrite the later change, and the refusal (409 `KNOWLEDGE_UNDO_CONFLICT`) MUST carry in its details, beside the document and the later version, `handoff`: a prompt the daemon writes asking the person's agent to undo the pass by hand — naming the pass and its summary, the knowledge folder, every document it touched and what it did to each, each document edited since with the version that last changed it, and where to read the pass's diff and the later ones in the history repository — reversing what the pass changed while keeping the later edits, editing only the files (Coffer records them as an edit on disk), committing nothing itself, and showing each result first. `coffer knowledge undo` MUST print the same prompt when it is refused. Only a curation pass is undone this way — any single version is restored instead. A machine with no git keeps every write working and records no history, and the history reads answer 503 `KNOWLEDGE_HISTORY_UNAVAILABLE`; git is looked for on every read, so one removed while the daemon runs is answered the same way. When the cause is that git is not installed, the refusal's details MUST carry `reason: "git_missing"` and `handoff`, a prompt asking the person's agent to install git on this machine — naming its OS and architecture and what needed git — the way that fits the machine, confirming it with `git --version`; neither the prompt nor the error's message may name an install command, and the `coffer knowledge` history commands MUST print the same prompt.

#### Scenario: a document's history lists its versions with their writers
- **GIVEN** a document the user created through Add a document, that a pass then merged a Claude Code item into, and that the user then edited
- **WHEN** its history is read
- **THEN** it lists three versions newest first, written by the user, by Coffer's curation naming Claude Code's item, and by the user, each with its diff
- **AND** restoring the first version writes a new commit and leaves the history intact

#### Scenario: undo a pass as a whole
- **GIVEN** a pass that changed two documents and retired a third
- **WHEN** the user undoes it
- **THEN** one new commit puts all three documents back as they were before the pass

#### Scenario: an undo that would overwrite a later change is refused
- **GIVEN** a pass that changed a document the user has edited since
- **WHEN** the user undoes the pass
- **THEN** the undo is refused naming that document, and nothing is written

#### Scenario: an edit on disk becomes a version of its own
- **GIVEN** a document a person edits in their own editor, outside Coffer
- **WHEN** the user then saves another document from the web UI
- **THEN** the edited document's history shows the edit as its own version, written on disk, and the save's commit holds only the saved document

#### Scenario: a refused undo carries a prompt for undoing the pass by hand
- **GIVEN** a pass that changed a document the user has edited since
- **WHEN** the user undoes the pass
- **THEN** the refusal names the document and the version that edited it, and carries a prompt naming the pass, that document with that version, the history command that shows the pass's diff, keeping the later edits and committing nothing
- **AND** nothing is written

#### Scenario: no git hands installing it to an agent
- **GIVEN** a machine with no git
- **WHEN** a document is written and its history is then read
- **THEN** the write works and the read is refused `KNOWLEDGE_HISTORY_UNAVAILABLE` with reason `git_missing` and a prompt to install git naming this machine and `git --version`, and neither the prompt nor the message names an install command
