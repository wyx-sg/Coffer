## MODIFIED Requirements

### Requirement: Report skill drift on request
The system MUST provide a `verify` operation — a read-only facility on the CLI (`coffer skill verify`), on REST (`POST /skills/verify`) and on the Skills page (**Check copies**) — that compares each enabled binding to its on-disk target — and each delivery the rule wants whose path a folder Coffer did not put there already occupies — and reports drift categories (missing link, tampered link, foreign content at the link path, missing master, orphan master), and exits non-zero on the CLI when drift is found. Asking for the report MUST NOT itself repair anything. The drift report is ephemeral: each binding whose on-disk target disagrees with the binding state, categorized by drift type. A report entry carries the skill, the agent, the kind and the path, and no remedy text: each surface says what to do about a kind in its own words — the command line prints a remedy naming its own commands (`coffer skill verify --fix` for a missing or tampered link), and the Skills page says that **Repair** puts a missing or repointed link back. An entry of a kind no repair settles also carries the hand-off of "Hand unsettled skill drift to an agent with a prompt". The Skills page lists the report's findings with the skill, the agent, the path and what the kind means, and offers the repair of "Repair repairable drift from master" for the findings it covers; the other findings stay listed for the user to act on.

#### Scenario: detect drift in agent skill directories
- **GIVEN** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **WHEN** the user runs `coffer skill verify` (CLI) or calls `POST /skills/verify` (REST),
- **THEN** the report lists each drift type, the command line with a remedy naming its own commands, and exits with a non-zero status; asking for the report never itself repairs anything — repair runs only along the separate paths in "opt-in repair re-delivers repairable drift from master" and the boot-heal scenarios below.

#### Scenario: check agents' copies from the skills page
- **GIVEN** one skill whose delivered link is missing and another whose link path holds a folder Coffer did not put there
- **WHEN** the user chooses Check copies on the Skills page
- **THEN** both findings are listed with the skill, the agent and the path, the missing link saying that Repair puts it back, and nothing on disk has changed
- **AND** choosing Repair re-creates the missing link, while the foreign folder is left as it was and stays listed

#### Scenario: a folder in the way of a first delivery is reported
- **GIVEN** an agent whose skills directory already holds a real folder named like a skill, and that skill is then imported with a reach that grants the agent
- **WHEN** the drift report runs
- **THEN** it lists that path as foreign content at the link path for the skill and the agent, and the folder is left exactly as it was

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or with `coffer skill add <git-url> [--ref <ref>] [--path <subpath>]`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no secret Coffer supplies: a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the user takes a newer one through "Update a Git-imported skill from its source". A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written. When this machine has no `git`, staging MUST be refused `SKILL_SOURCE_UNREACHABLE` whose details carry `reason: "git_missing"` and `handoff`, a prompt (Principle IV, AI-Native) asking the person's agent to install git on this machine — naming its OS and architecture — and to confirm with `git --version`, naming no install command; the add dialog MUST offer it beside the refusal, as the change-source and update dialogs do beside theirs.

#### Scenario: add a skill from a repository subpath at a ref
- **GIVEN** a repository whose `skills/review/SKILL.md` is valid on tag `v1.2`
- **WHEN** the user adds it with ref `v1.2` and subpath `skills/review` and confirms
- **THEN** the skill is added from that commit, and its source records the URL, `v1.2`, `skills/review` and the commit id
- **AND** a later commit on the repository changes nothing until the user applies it as an update

#### Scenario: an unreachable repository writes nothing
- **GIVEN** a URL that git cannot fetch
- **WHEN** the user tries to add from it
- **THEN** the dialog shows git's message and nothing is written

#### Scenario: a skill import with no git hands installing it to an agent
- **GIVEN** a machine with no `git`
- **WHEN** a Git source is staged
- **THEN** it is refused `SKILL_SOURCE_UNREACHABLE` with `reason: "git_missing"` and a prompt that names this machine's OS and architecture and `git --version`, naming no install command, and nothing is written
- **AND** the add dialog offers Copy prompt beside the refusal

### Requirement: Update a Git-imported skill from its source
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`coffer skill update <name> --check`), and periodically, every six hours — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. Choosing it MUST show a preview of the change to the skill's folder — the files added, removed and changed, with a diff, and the commits in the range — and apply nothing until the user confirms; confirming replaces the folder's content atomically with the new commit's, moves the pin to it, keeps the skill's reach and delivered links, and is audited as an update. An update whose `SKILL.md` names a different skill, or which fails the checks of "Validate imported skill folders against AgentSkills", is refused and changes nothing. When the skill's folder has been edited locally since the pinned commit (its content no longer matches the content hash recorded for that commit), the update MUST show a **conflict** instead of a plain preview, offering **Keep mine** (leave the folder and the pin as they are and stop offering this update until a newer commit arrives), **Take theirs** (apply the new commit, discarding the local edits), **Compare** (the local folder, the pinned commit and the new commit side by side) and **Merge with an agent**: the preview carries `handoff`, a prompt (Principle IV, AI-Native) that asks the person's agent to merge the new commit into the local edits in the master folder — naming the skill, the master folder as the only place to edit, the files edited since the pin, the pinned and new commits with the commits' subjects, and the repository (without any credential in its URL), ref and folder to read upstream from, read-only — to show the person the diff, and to leave recording the merge to the person, who then records it per "Record an update merged into local edits". A preview with no local edits carries a `null` `handoff`. Building the prompt writes nothing. A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing. On the command line `coffer skill update <name>` previews and asks before applying, refuses a conflict unless `--take-theirs` or `--keep-mine` says which side to keep, `--prompt` prints the merge hand-off exactly as the preview serves it, and `--yes` skips the question.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3` with commits that change the skill's folder
- **WHEN** the periodic check runs, or the user chooses Check for updates
- **THEN** the skill shows Update available with the range `a1..c3` on the Skills page and its detail page
- **AND** nothing under `~/.coffer/skills/` has changed

#### Scenario: an update is applied after its preview
- **GIVEN** a skill showing Update available and not edited locally
- **WHEN** the user opens the update, reviews the preview of added, removed and changed files, and confirms
- **THEN** the folder holds `c3`'s content, the source is pinned to `c3`, the skill's reach and delivered links are unchanged, and the update is audited
- **AND** closing the preview without confirming leaves the folder and the pin at `a1`

#### Scenario: a local edit makes the update a conflict
- **GIVEN** a skill pinned to `a1` whose `SKILL.md` the user edited, and `main` at `c3`
- **WHEN** the user opens the update
- **THEN** the dialog shows a conflict offering Keep mine, Take theirs and Compare instead of a plain preview
- **AND** Keep mine leaves the edited folder and the `a1` pin in place and stops offering `c3`, while Take theirs applies `c3` and discards the edit

#### Scenario: a conflict hands merging the update to an agent
- **GIVEN** a skill pinned to `a1` whose `notes.txt` the user edited, and `main` at `c3` with a commit that changes the skill's folder
- **WHEN** the user opens the update and chooses Merge with an agent
- **THEN** the dialog offers Copy prompt and, where a managed agent is available, Ask an agent, beside Keep mine and Take theirs
- **AND** the prompt names the master folder, `notes.txt` as a local edit, `a1` and `c3` with the commit's subject and the repository to read upstream from, tells the agent to edit only the master folder and not to record the merge itself, and nothing on disk or in the pin has changed

#### Scenario: an unreachable source is reported and changes nothing
- **GIVEN** a Git-imported skill whose repository can no longer be fetched
- **WHEN** the user chooses Check for updates
- **THEN** the skill shows git's message and the time of its last successful check
- **AND** the folder and the pin are unchanged

#### Scenario: update a skill from the command line
- **GIVEN** a Git-imported skill whose ref has a newer commit that changes its folder
- **WHEN** the user runs `coffer skill update <name>` and answers yes
- **THEN** the command prints the commit range and the files that change, and after the answer the folder holds the new commit's content and the pin has moved
- **AND** with a local edit the same command refuses the update until the user passes `--take-theirs` or `--keep-mine`

## ADDED Requirements

### Requirement: Record an update merged into local edits
After the local edits of a Git-imported skill have been merged with an upstream update (by the person's agent, per the hand-off of "Update a Git-imported skill from its source"), the person MUST be able to record it — **I merged it** in the update dialog, confirmed first; `POST /api/v1/skills/{uid}/source/merged` with the upstream `commit`; `coffer skill update <name> --merged <commit>`. Recording MUST move the pin to that commit and MUST NOT touch the master folder's files; the pin's content hash becomes that commit's own content, so the merged folder still counts as locally edited against its new base and a later update is a conflict again that lists exactly the edits carried over. The update is no longer offered, and the recording is audited as `skill_update_merged` with the old and the new commit. The commit MUST be an update waiting for the skill — the ref's newest commit or one of the commits between the pin and it that change the skill's folder, given in full or by a unique prefix of at least seven characters — and anything else (no newer commit, the pinned commit itself, a commit not on the ref) MUST be refused with `409 SKILL_UPDATE_NOT_PENDING`, changing nothing.

#### Scenario: recording a merge moves the pin and keeps the merged files
- **GIVEN** a skill pinned to `a1` with a local edit, `main` at `c3`, and the master folder merged with `c3` by an agent
- **WHEN** the user chooses I merged it and confirms, or runs `coffer skill update <name> --merged c3`
- **THEN** the skill is pinned to `c3`, the master folder's files are exactly as the merge left them, `c3` is no longer offered, and the recording is audited as `skill_update_merged` from `a1` to `c3`
- **AND** when `main` moves on again the update is a conflict listing only the edit carried over

#### Scenario: recording a merge refuses a commit that is not the update
- **GIVEN** a skill pinned to `a1`
- **WHEN** a merge is recorded against `a1` itself, against a commit that is not on the ref, or while the ref has nothing newer
- **THEN** it is refused with `409 SKILL_UPDATE_NOT_PENDING`, the pin stays at `a1`, and nothing is audited

### Requirement: Hand unsettled skill drift to an agent with a prompt
The three drift kinds no pass settles — a folder Coffer did not make at a skill's link path, a folder in the skills store no skill owns, and a skill whose master folder is gone — MUST each carry a hand-off prompt (Principle IV, AI-Native) built from the finding alone, the same text on the drift report entry (`handoff` on `POST /skills/verify` and `POST /skills/repair`, printed by `coffer skill verify --prompt`) and on the finding's attention item: for a folder in the way, compare it with the skill's master folder, say whether it holds edits worth keeping, and recommend **Adopt this folder** or **Replace it with Coffer's link**; for a folder no skill owns, say what it is and whether its `SKILL.md` names it, and recommend **Add to library** or **Delete folder**; for a missing master, look for a copy that can be restored (the folders Coffer set aside under `~/.coffer/backup/skills/`, a copied copy in an agent's skills folder, the skill's source) and, once the person agrees, copy it back to where the master belongs. The prompts MUST tell the agent to move, delete or edit no folder itself except that one agreed copy; the choice stays the button the person presses, and the buttons stay (Check again, Repair, the two choices of "Resolve a folder in the way of a skill's link", Add to library and Delete folder, Remove the skill). The Skills page MUST offer Copy prompt and, where a managed agent is available, Ask an agent beside each such finding, in the compare of a folder in the way, on the pane of a folder no skill owns and on the Files tab of a skill whose master is gone. A missing or tampered link carries a `null` `handoff`: Repair is its fix. The attention items' reasons for these kinds MUST name no command to run.

#### Scenario: a folder in the way is handed to an agent to compare
- **GIVEN** a skill whose link path in an agent's skills folder holds a real folder with a file of the user's
- **WHEN** the drift report runs and the attention list is read
- **THEN** the report entry's hand-off names that folder and the skill's master folder, offers the choice between Adopt this folder and Replace it with Coffer's link, and tells the agent to move, delete or edit no folder itself
- **AND** the attention item carries the same prompt, its reason names no command, and the folder is left exactly as it was

#### Scenario: a missing master is handed to an agent to find a copy
- **GIVEN** a delivered skill whose master folder was removed outside Coffer
- **WHEN** the drift report runs and the attention list is read
- **THEN** the report entry's hand-off names where the master folder belongs, the backup folder under `~/.coffer/backup/skills/` and the command that prints the skill's source, and asks for a copy to be copied, not moved, back once the person agrees
- **AND** the attention item carries the same prompt and its reason names no command
