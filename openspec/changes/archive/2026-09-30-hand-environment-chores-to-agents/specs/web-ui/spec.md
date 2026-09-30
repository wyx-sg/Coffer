## MODIFIED Requirements

### Requirement: Hand installing an agent to the person when none is found
While no supported agent is installed on this machine, `GET /api/v1/agents/types` MUST carry
`install_handoff`, a prompt the daemon writes (see
[skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt"
for the shape every hand-off takes) asking the person's assistant to install one of the
supported agents — naming each with its program and settings folder, this machine's OS and
architecture and the `PATH` Coffer looks programs up on — choosing the install method that fits
this machine, keeping any settings folder that already exists, confirming the program with
`--version`, leaving signing in to the person, and then coming back to Scan again; it MUST name
no installer, package manager or command, and it MUST be `null` once any supported agent is
installed. Overview's first run with no agent found MUST offer that prompt through **Copy
prompt** only: there is no agent of Coffer's to ask, and the page MUST carry no install link of
its own.

#### Scenario: with no agent found the install prompt is built by the daemon
- **GIVEN** neither supported agent's program is installed on this machine
- **WHEN** the types are read, and read again after one is installed
- **THEN** the first answer carries an install prompt naming both agents and their settings
  folders, no installer, and the standing rules every hand-off ends with
- **AND** the second carries none

#### Scenario: with no agent found overview offers the install prompt to copy
- **GIVEN** a first run on a machine where no supported agent is found
- **WHEN** Overview renders
- **THEN** beside Scan again it offers Copy prompt with the daemon's install prompt
- **AND** it offers no Ask an agent and no install link

### Requirement: Check for and install updates on Settings › About
In the desktop shell, the About tab MUST show the version running, when updates
were last checked, a **Check for updates** control, and the result of the
latest check — up to date, or a newer version available with its version number,
its release notes and a **Download and restart** control — and a **Check
automatically** switch that turns the shell's launch and six-hourly checks on or
off, kept in the page's storage and reported to the shell at startup. The check
and the install are the shell's (spec [desktop-app](../desktop-app/spec.md)
"Check for updates against a signed release manifest"), reached through the
same module as the shell's other host affordances; the tab only renders what the
shell reports and asks it to act. While a check or a download is running its
control MUST show that it is busy — a download its progress — and not accept a
second press; a check or a download that fails MUST show a readable error on
the tab, keep the last successful check's time, and leave the running version
untouched. A desktop build made without an updater key MUST say it does not
check for updates. In a browser, About MUST show the version and say that
updates are installed by the desktop app, with no update control, because a page
the daemon serves cannot replace the application; it MUST instead offer the
daemon's upgrade hand-off (spec [daemon](../daemon/spec.md) "Hand an upgrade of
Coffer to an agent") — Copy prompt, and Ask an agent when a managed agent is
available — and name no install command itself. The desktop shell never asks
for that hand-off.

#### Scenario: about shows the version and when updates were last checked
- **GIVEN** the desktop shell running version 1.0.0, last checked at launch, with no newer release
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows 1.0.0, the time of that check, that Coffer is up to date, and a Check for updates control

#### Scenario: checking by hand finds a newer version
- **GIVEN** the About tab open in the desktop shell and a newer signed release on the manifest
- **WHEN** the user chooses Check for updates
- **THEN** the control shows it is checking, then the tab shows the newer version number, its notes and a Download and restart control
- **AND** the last-checked time moves to now

#### Scenario: download and restart installs the newer version
- **GIVEN** the About tab showing a newer version available
- **WHEN** the user chooses Download and restart
- **THEN** the tab shows the download's progress and the shell installs the update and relaunches
- **AND** after the relaunch About shows the new version as the one running

#### Scenario: a failed check keeps the last good result
- **GIVEN** the About tab in the desktop shell with the release manifest unreachable
- **WHEN** the user chooses Check for updates
- **THEN** the tab shows a readable error and keeps the time of the last successful check
- **AND** the running version is unchanged

#### Scenario: about in a browser offers no update control
- **GIVEN** the web UI opened in a browser
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows the version and says updates are installed by the desktop app
- **AND** it shows no Check for updates or Download and restart control, and offers Copy prompt with the daemon's upgrade hand-off

## ADDED Requirements

### Requirement: Hand an agent's missing program to an agent on the agent pages
Wherever the web UI shows an agent type whose program is not found — its Agents list row and
the notice under a config-left-behind row, its detail page while it is not added, and the
Overview tab's problem states (config left behind, not found) — it MUST offer the daemon's
`install_handoff` prompt for that type (agent-registry "Hand installing an agent's program to an
agent") through **Copy prompt**, and through **Ask an agent** only while another managed agent
is available to run the conversation: the missing agent itself cannot. A list row, which has
room for one action, MUST make Copy prompt its action and put Ask an agent in its ⋯ menu. None
of these surfaces MUST show an install command or tell the person to restart Coffer. The
Plugins tab of a Claude Code agent whose program is not found, where Uninstall cannot run, MUST
say so and offer the same prompt. The Connect review MUST offer the hand-off a `SHIM_NOT_FOUND`
refusal carries beside Retry (agent-registry "Install Coffer's MCP server into an agent in one
action").

#### Scenario: an agent whose program is not found offers its install prompt
- **GIVEN** Codex not installed and no managed agent available
- **WHEN** the user chooses Copy prompt on the Codex row, then opens the row's ⋯ menu
- **THEN** the daemon's prompt is copied as given, no install command is shown anywhere
- **AND** the menu offers no Ask an agent

#### Scenario: ask an agent is offered only while another managed agent is available
- **GIVEN** Claude Code's config left behind with its program gone, and Codex available as a managed agent
- **WHEN** the user opens the Claude Code row's ⋯ menu and chooses Ask an agent
- **THEN** New conversation opens, and nothing is written or sent
- **AND** with only Claude Code itself managed, the menu offers no Ask an agent

#### Scenario: a connect refused for a missing shim offers the daemon's prompt
- **GIVEN** a registered agent and a daemon that refuses its Connect with `SHIM_NOT_FOUND` carrying a hand-off
- **WHEN** the user applies the Connect review
- **THEN** the review shows the change as failed with copy that names no environment variable or command
- **AND** Copy prompt beside Retry copies the refusal's prompt as given

### Requirement: Offer an MCP server's hand-off beside Test and View log
An MCP server's page MUST offer the backend's hand-off (Copy prompt, and Ask an agent when a managed agent
is available) wherever the server's state is a chore for an agent, passing the prompt on as served and
never assembling it: the missing-launcher callout offers the status read's `handoff` in place of any install
command, and the failing callout and a failed test's result offer the diagnosis `handoff` beside View log
(or Show stderr) while Test stays in the header. The page MUST NOT show a package-manager command or an
"install it, then refresh" instruction.

#### Scenario: a missing launcher offers the hand-off, not an install command
- **GIVEN** an MCP server whose status names a missing launcher and carries a `handoff`
- **WHEN** its page opens
- **THEN** the launcher callout names the launcher and offers Copy prompt, which copies the served prompt, and shows no `brew install` line

#### Scenario: a failed test offers a diagnosis hand-off beside View log
- **GIVEN** an MCP server whose test just failed with an error and a `handoff`
- **WHEN** the result is shown
- **THEN** the result callout shows the error with View log and Copy prompt beside it, and the header still offers Test

### Requirement: Offer the hand-off a knowledge refusal carries beside it
When the daemon refuses a knowledge operation with a hand-off in the error's details
(`details.handoff.prompt`), the Knowledge page MUST offer that prompt (Copy prompt, and Ask an
agent when a managed agent is available) where it shows the refusal, passing the prompt on as
served and never assembling it: a refused **Undo this pass** offers the prompt for undoing the
pass by hand in the note that names the document edited since, which still points at the
per-document History restore; and a History tab or Recent changes that cannot be read because
git is not installed offers the prompt for installing it beside Retry. The page MUST NOT show an
install command.

#### Scenario: a refused pass undo offers the prompt for undoing it by hand
- **GIVEN** a curation pass whose undo the daemon refuses because a document it wrote was edited since, with a hand-off in the refusal
- **WHEN** the user undoes the pass from its page
- **THEN** the note that names the document still points at restoring a single document from its History, and offers Copy prompt, which copies the served prompt

#### Scenario: a history that needs git offers the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** a document's History tab opens
- **THEN** it says the history could not be read, with Retry and Copy prompt, which copies the served prompt, and names no install command

#### Scenario: recent changes that need git offer the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** Recent changes opens
- **THEN** it offers Retry and Copy prompt, which copies the served prompt

