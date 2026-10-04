## ADDED Requirements

### Requirement: Show a setup screen while the daemon waits for git
While the daemon reports `status: "setup"` (spec [daemon](../daemon/spec.md)
"Wait in a setup state when git is missing or too old"), the shell MUST show one
setup screen in the workspace in place of every page — the sidebar stays, as
with the offline state — and no page of its own. The screen MUST say what is
wrong ("git isn't installed on this machine", or "git 2.30 is older than 2.40,
which Coffer needs", from the status's `reason`, `found` and `needed`), why
Coffer needs it in one sentence (the vault keeps its history and syncs with
git), the hand-off with the daemon's prompt as given (the shared Ask an agent ▾
/ Copy prompt control; with no managed agent available, as in the setup state,
Copy prompt), and Check again. Check again MUST ask the daemon to look again
(`POST /api/v1/daemon/setup/check`); when git is still not there the screen
stays and says when it last checked; when it is, the page MUST restart the
daemon the way its host restarts it — the desktop shell's restart, or the
daemon's own restart in a browser — and continue into the app once the
restarted daemon answers, with no manual reload.

#### Scenario: the setup screen says git is missing and hands the install to an agent
- **GIVEN** a daemon in its setup state with `reason: "git_missing"`
- **WHEN** the app opens on any page
- **THEN** the workspace shows the setup screen saying git isn't installed on this machine and that the vault keeps its history and syncs with git
- **AND** it offers the daemon's install prompt through the hand-off control and a Check again button

#### Scenario: the setup screen names the version that is too old
- **GIVEN** a daemon in its setup state with `reason: "git_too_old"`, `found: "2.30"` and `needed: "2.40"`
- **WHEN** the setup screen shows
- **THEN** it says git 2.30 is older than 2.40, which Coffer needs

#### Scenario: check again restarts the daemon once git is there
- **GIVEN** the setup screen, on a machine where git has since been installed
- **WHEN** the person presses Check again
- **THEN** the page asks the daemon to look again, and on `ready: true` restarts the daemon
- **AND** when git is still missing the screen stays and says it checked again
