## Why

Upgrading and removing Coffer are manual today. The install page's Upgrade
section asks the person to re-run the installer and restart the daemon, and its
Uninstall section is a four-step list: disconnect each agent, turn every skill
off, switch off start at login, stop the daemon, delete `~/.coffer/bin`, edit
the shell profile, trash the app. The desktop app already updates itself from a
signed manifest, but a machine that installed only the command line has no way
to learn a new release exists, and nothing at all removes Coffer's footprint
from the agents' own configuration.

## What Changes

- **`coffer update`** upgrades the installer's frozen binaries in place: it reads
  the newest release from GitHub, downloads the command-line archive, verifies
  it against the release's `SHA256SUMS`, installs it the way the installer does
  and restarts the daemon onto it. On a machine running the desktop app it hands
  the update to the app's signed updater; a source checkout is told to pull.
  `coffer update --check` only reports.
- **The daemon checks for a new release** of the frozen binaries once a day
  (only when it runs from them; the app checks for itself), behind a switch on
  Settings › About, and the About page in a browser shows what it found with the
  command that installs it.
- **Uninstall**, one action that undoes what Coffer wrote outside `~/.coffer`:
  the daemon disconnects every agent (MCP entry and memory hook), takes the
  model-provider routing back out of the agents' settings, removes every skill
  link it delivered, removes the start-at-login job, deletes `~/.coffer/bin`
  and the installer's `PATH` lines and the terminal launch files it wrote, then
  stops. Coffer's own records stay, so installing again finds the vault as it
  was.
  - Settings › About in the desktop app gets **Uninstall Coffer…**: a
    confirmation that names each step, with an unticked **Also delete my data**
    that deletes `~/.coffer` and the master key's Keychain items after Touch ID;
    the app then moves itself to the Trash and quits.
  - `coffer uninstall` runs the same. With the desktop app installed it opens
    that dialog in the app; otherwise it asks in the terminal, and deleting the
    data needs the words typed at an interactive terminal (no flag skips it).
  - In a browser, About shows the command.
- The install page's Upgrade and Uninstall sections describe these instead of
  the manual steps.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `daemon`: adds "Check the installed binaries for a new release", "Upgrade the
  installed binaries from the command line" and "Uninstall Coffer from this
  machine"; "Hand an upgrade of Coffer to an agent" names `coffer update`.
- `desktop-app`: adds "Uninstall Coffer from the app"; "Serve the command
  line's desktop requests" opens the uninstall dialog.
- `web-ui`: "Check for and install updates on Settings › About" shows the
  daemon's check in a browser; adds "Offer uninstall on Settings › About".

## Impact

Backend: a release-check module, the update and uninstall services, two daemon
routes (`/daemon/upgrade/*`, `/daemon/uninstall`), the presence grant op
`uninstall`, a data purge run after the daemon has stopped, and the `coffer
update` / `coffer uninstall` commands. Frontend: About's updates section in a
browser and a new Uninstall section and dialog. Desktop: an `uninstall_coffer`
command and an `uninstall` desktop request. Docs: install, desktop app, daemon,
CLI reference, filesystem and distribution pages (en and zh). Shell canvas:
the About boards.
