## ADDED Requirements

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
the daemon serves cannot replace the application.

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
- **AND** it shows no Check for updates or Download and restart control

## MODIFIED Requirements

### Requirement: Organise Settings into five tabs
Settings MUST carry exactly five tabs, in this order, grouped by what they
manage rather than by how Coffer is built — **General** (display preferences, when the daemon runs, and which
experimental features are switched on),
**Coffer's model** (at `/settings/engine` — Coffer's own machinery: the internal
LLM connection and model its own passes run on, the speech-to-text connection
and model voice messages are transcribed on, and the switch and interval of each
of those passes), **Data** (retention policy and manual prune), **Security**
(where the master encryption key lives — beside the database, or in the OS
keychain), and **About** (version, license, source, and in the desktop app the
update check of "Check for and install updates on Settings › About") — and MUST
open on General.
Clicking a tab swaps the right pane without a full page reload.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the page resolves
- **THEN** it lands on the General tab
- **AND** the settings sidebar shows General, Coffer's model, Data, Security, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload

### Requirement: Leave daemon controls to the CLI
No tab may expose a "Shutdown daemon" or "Rotate token" control — both belong on
the CLI: shutting the daemon down from the web kills the very page you are on
and recovery needs a terminal anyway, and token rotation is a security action a
single-user local app needs maybe once ever, which `coffer daemon rotate-token`
covers. The About tab MUST show version, license, source and the update check
of "Check for and install updates on Settings › About" only, with no
language picker (the sidebar already switches language) and no
installed-resource-kind list (developer detail). Remaining jargon is rewritten
in plain language (e.g. "prune" is phrased as clearing expired data).

#### Scenario: settings drops the confusing controls
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" control or a "Rotate token" control
- **AND** there is no "Daemon" tab and no read-only daemon-status panel
- **AND** the About tab shows version / license / source and the update check only — no language picker, no resource-kind list
