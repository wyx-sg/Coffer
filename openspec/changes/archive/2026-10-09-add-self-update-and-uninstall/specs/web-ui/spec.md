## ADDED Requirements

### Requirement: Offer uninstall on Settings › About
Settings › About MUST end with an **Uninstall** section. In the desktop shell it
MUST offer **Uninstall Coffer…**, which opens the shell's one confirmation
dialog ("Confirm a destructive action in one dialog that names its cost"),
titled "Uninstall Coffer?", listing what uninstalling does — disconnect every
agent and take Coffer's model routing out of their settings, remove the skill
links Coffer delivered, turn off start at login, remove the command-line tools
and the installer's `PATH` lines, move the app to the Trash — and saying that
the vault, secrets, skills and settings in `~/.coffer` stay, so installing again
finds them, and that the agents must be connected again. It MUST carry an
unticked **Also delete my data (~/.coffer)**; ticking it MUST say, as a danger
note, that this deletes every secret, skill, knowledge collection and the
master key for good, offer **Back up the master key** first, and turn the
confirm button into **Uninstall and delete data**. Confirming runs the shell's
uninstall (spec [desktop-app](../desktop-app/spec.md) "Uninstall Coffer from
the app"); while it runs the dialog cannot be left, a failure stays in it with
the reason, and on success it shows each step's outcome before the app quits.
`?uninstall=1` (and `&delete=1`) in the address MUST open the dialog (with the
data option ticked). In a browser the section MUST instead say that uninstalling
runs from the desktop app or the command line and show `coffer uninstall` with a
copy button.

#### Scenario: the uninstall dialog names what it removes and keeps the data by default
- **GIVEN** Settings › About open in the desktop shell
- **WHEN** the user chooses Uninstall Coffer…
- **THEN** the dialog lists each step, says `~/.coffer` stays, and shows Also delete my data unticked with the confirm button reading Uninstall

#### Scenario: ticking delete my data warns and offers a backup
- **GIVEN** the uninstall dialog open
- **WHEN** the user ticks Also delete my data
- **THEN** a danger note says the data and the master key are deleted for good, Back up the master key is offered, and the confirm button reads Uninstall and delete data

#### Scenario: about in a browser shows the uninstall command
- **GIVEN** the web UI opened in a browser
- **WHEN** the user opens `/settings/about`
- **THEN** the Uninstall section shows `coffer uninstall` with a copy button and no Uninstall Coffer… control

## MODIFIED Requirements

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
check for updates.

In a browser, a page the daemon serves cannot replace the application, so About
MUST NOT offer Download and restart. When the daemon runs from the installer's
binaries, About MUST show the daemon's own check (spec
[daemon](../daemon/spec.md) "Check the installed binaries for a new release") —
when it last checked, up to date or the newer version with its notes, a
**Check for updates** control and the **Check automatically** switch, which
here sets the daemon's switch — and, when a newer version is found, the command
`coffer update` with a copy button. Otherwise it MUST say that updates are
installed by the desktop app. In both cases it MUST offer the daemon's upgrade
hand-off (spec [daemon](../daemon/spec.md) "Hand an upgrade of Coffer to an
agent") — Copy prompt, and Ask an agent when a managed agent is available. The
desktop shell never asks for that hand-off.

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
- **GIVEN** the web UI opened in a browser on a daemon running from the desktop app
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows the version and says updates are installed by the desktop app
- **AND** it shows no Check for updates or Download and restart control, and offers Copy prompt with the daemon's upgrade hand-off

#### Scenario: about in a browser shows the daemon's check and coffer update
- **GIVEN** the web UI opened in a browser on a daemon running from the installer's binaries that found a newer release
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows the newer version, its notes, when the daemon checked, the Check automatically switch and `coffer update` with a copy button, and no Download and restart control
