## MODIFIED Requirements

### Requirement: Show the Skills page as the final canvas draws it
The Skills page MUST follow canvas 4.3: a compact header (title, count, help) over the library beside a reading pane. A library row MUST show, in place of its description, the one thing that needs the reader; rows ticked for bulk actions MUST show the selection both as a bar under the filter and in the reading pane (which skills, Set reach…, Delete N skills…). The open skill's Files tab MUST be one card — the folder's files with SKILL.md first beside the open file's header bar and body — whose edit mode refuses a stale save while keeping the text. The Requires tab MUST link each command to the CLIs page, and offer the same hand-off to an agent its CLI page does for a command that needs the user. Below the commands it MUST list each secret the skill declares (spec skill-manager "Declare the secrets a skill requires") with whether it is set; a secret that is not set MUST read "secret <name> is not set" and open the Secrets page, with no hand-off to an agent and no command of its own, because setting a secret is the person's task. A library row whose most urgent item is such a secret MUST read "Needs secret <name> · not set", and the open skill MUST carry a banner naming each secret that is not set with Open Secrets. A folder in the way of an agent's link, a delete Coffer refuses, a master folder that is gone and a Git source to change MUST each be answered where they are shown, with the choice confirmed before anything is written. The Add skill dialog MUST carry the Available to reach control.

#### Scenario: a library row says what needs attention in place of its description
- **GIVEN** a skill whose declared command is missing and a Git skill with an update waiting
- **WHEN** the user opens the Skills page
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" where their descriptions would be

#### Scenario: selected skills are set or deleted together from the reading pane
- **GIVEN** the built-in skill and two of the user's skills
- **WHEN** the user ticks the two skills
- **THEN** the reading pane names both, says the built-in skill can't be selected, and Delete 2 skills… deletes both after one confirmation

#### Scenario: a skill file changed on disk refuses the save and keeps the text
- **GIVEN** a skill file open for editing
- **WHEN** the save is refused because the file changed on disk
- **THEN** the header says Not saved, the edited text is still there, Reload, Compare and Copy my text are offered, and Save stays off

#### Scenario: the requires tab links to the CLIs page and hands a command to an agent
- **GIVEN** a skill whose declared commands are missing or not logged in
- **WHEN** the user opens its Requires tab
- **THEN** each command shows its state, Open in CLIs, and Copy prompt / Ask an agent, and the tab offers no install, copy-command or login step of its own

#### Scenario: a folder in the way of a skill's link is resolved by a confirmed choice
- **GIVEN** a skill whose link in one agent is a real folder Coffer did not make
- **WHEN** the user opens Review… from the skill's banner and chooses Adopt this folder
- **THEN** the dialog shows the difference first, and only the confirm button resolves that agent's copy by keeping its version

#### Scenario: a delete refused because a copy is not Coffer's stays open and says why
- **GIVEN** a skill whose delete the daemon refuses because an agent's copy is not Coffer's link
- **WHEN** the user confirms the delete
- **THEN** the dialog stays open, names the folder, says Coffer won't remove it, and offers Try again

#### Scenario: a skill whose master folder is gone offers the ways forward
- **GIVEN** a skill whose master folder was removed outside Coffer
- **WHEN** the user opens it
- **THEN** a banner says the master folder is gone, and the Files tab offers Restore it from History (not available while a skill's versions are not recorded) and Remove the skill, which opens the delete confirmation

#### Scenario: a folder no skill claims is added in place or moved out
- **GIVEN** a folder in the skills store that no skill claims
- **WHEN** the user opens it under Not in your library
- **THEN** it shows its path, whether its SKILL.md is valid and its file count, Delete folder… asks first, and Add to library… adds it and opens the new skill

#### Scenario: changing a skill's source shows the change before anything is replaced
- **GIVEN** a skill added from Git
- **WHEN** the user opens Change source…, enters another repository and chooses Check source
- **THEN** the dialog shows the change against the current version with a button to take it, and cancelling applies nothing and drops the staged source

#### Scenario: a skill is added with the reach chosen in the dialog
- **GIVEN** the Add skill dialog with Available to set to Disabled or to chosen agents
- **WHEN** the user adds the skill
- **THEN** each added skill is turned off, or scoped to the chosen agents, and with every agent nothing more is written

#### Scenario: the requires tab lists a skill's secrets and opens Secrets for a missing one
- **GIVEN** a skill declaring the command `jq` and the secrets `GITHUB_TOKEN`, which is set, and `NPM_TOKEN`, which is not
- **WHEN** the user opens its Requires tab
- **THEN** below the commands `GITHUB_TOKEN` reads Set and `NPM_TOKEN` reads "secret NPM_TOKEN is not set" with Open Secrets, which opens `/secrets`
- **AND** the secrets offer no Copy prompt and no command

#### Scenario: a skill that needs a secret that is not set says so and links to Secrets
- **GIVEN** a skill declaring `GITHUB_TOKEN`, which is not set, and `NPM_TOKEN`, which is
- **WHEN** the user opens the Skills page and the skill
- **THEN** its library row reads "Needs secret GITHUB_TOKEN · not set"
- **AND** a banner above its tabs says "secret GITHUB_TOKEN is not set." with Open Secrets linking to `/secrets`, and does not name `NPM_TOKEN`
