## ADDED Requirements

### Requirement: Check the installed binaries for a new release
A daemon running from the installer's frozen binaries MUST check for a newer
release of Coffer one minute after it starts and then every 24 hours, so a
machine without the desktop app learns that a release exists. The check MUST
be one read-only `GET` of the GitHub API's latest release for the project,
bounded in time and size and sending nothing about the user; a failure keeps the
last result and is logged once per failure streak. `update_check` in
`~/.coffer/daemon-config.json` (the Check automatically switch on Settings ›
About) MUST turn the periodic check off, and `COFFER_UPDATE_CHECK=off` MUST pin
it off. A daemon running from the desktop app or from source MUST NOT check:
the app checks for itself and a source checkout is upgraded with git.

`GET /api/v1/daemon/upgrade` MUST report, beside the install method and the
hand-off, whether this daemon checks, whether the switch is on, when it last
checked successfully, the last failure, and the newest release found — its
version, release notes, publication date and page — when it is newer than the
running version. `POST /api/v1/daemon/upgrade/check` MUST check now and answer
the same record; `PUT /api/v1/daemon/upgrade/auto-check` MUST set the switch.

#### Scenario: the daemon reports a newer release of its binaries
- **GIVEN** a daemon running Coffer 0.3.0 from the installer's binaries, and a latest release v0.4.0
- **WHEN** `POST /api/v1/daemon/upgrade/check` is called
- **THEN** `GET /api/v1/daemon/upgrade` reports 0.4.0 with its notes and the time of the check

#### Scenario: the app's daemon leaves checking to the app
- **GIVEN** a daemon running from the desktop app's bundle
- **WHEN** `GET /api/v1/daemon/upgrade` is read
- **THEN** it reports that this daemon does not check, and nothing is fetched

### Requirement: Upgrade the installed binaries from the command line
`coffer update` MUST upgrade the installer's frozen binaries to the newest
release: download the command-line archive for this machine and the release's
`SHA256SUMS`, refuse an archive whose checksum does not match, put each binary
over its public name in `~/.coffer/bin` the way the installer does (a temporary
sibling, then a rename), and restart the daemon from the new
`~/.coffer/bin/coffer-daemon`. Nothing is replaced until the archive has
verified. `coffer update --check` MUST only report the running and the newest
version. When the running daemon is the desktop app's, `coffer update` MUST ask
the app to install its signed update instead (`coffer app update install`); a
source run MUST say to upgrade the checkout and change nothing. Already on the
newest release it MUST say so and change nothing.

#### Scenario: an update installs the verified archive and restarts the daemon
- **GIVEN** Coffer 0.3.0 installed by the installer and a latest release v0.4.0 whose archive matches its checksum
- **WHEN** the person runs `coffer update`
- **THEN** the binaries in `~/.coffer/bin` are 0.4.0's and the daemon is restarted from them

#### Scenario: an archive that does not match its checksum installs nothing
- **GIVEN** a latest release whose archive's SHA-256 differs from its `SHA256SUMS` line
- **WHEN** the person runs `coffer update`
- **THEN** it fails naming the checksum mismatch and `~/.coffer/bin` is unchanged

### Requirement: Uninstall Coffer from this machine
`POST /api/v1/daemon/uninstall` MUST remove what Coffer wrote outside
`~/.coffer` and then stop the daemon, so uninstalling is one action instead of a
list of manual steps. In order, it MUST take the model-provider routing out of
every agent's settings, disconnect every agent (its MCP entry and memory hook),
remove every skill link Coffer delivered with its delivery records, keep any
reconcile pass from restoring them, remove the start-at-login job, remove the
terminal launch files Coffer wrote, remove the installer's `PATH` lines (the
`# Added by Coffer installer` marker and the line after it) from the shell
profiles, and delete `~/.coffer/bin`. Each step MUST be attempted even when an
earlier one failed, and the answer MUST list every step as done, nothing to do,
or failed with its reason. The vault, the settings, the skills' own folders and
the history MUST stay, so installing Coffer again finds them.

With `delete_data`, the request MUST carry a presence grant for the operation
`uninstall` over the target `delete-data`, redeemed before anything changes; an
unverified grant MUST refuse the whole request. After the daemon has stopped
serving and released its lock, it MUST then delete the master key's Keychain
items and `~/.coffer`.

`coffer uninstall` MUST run the same. With the desktop app installed it MUST
open the app's uninstall dialog instead, where the person confirms. Otherwise it
MUST ask before uninstalling, unless `--yes` is given; `--delete-data` MUST ask
for the words `delete my data` at an interactive terminal — no flag skips that,
and without a terminal it MUST refuse — and deletes the master key's Keychain
items and `~/.coffer` only after the daemon has exited.

#### Scenario: uninstall removes every footprint and keeps the vault
- **GIVEN** a connected agent with a provider switch, two delivered skills, start at login on and the installer's `PATH` line in `~/.zshrc`
- **WHEN** `POST /api/v1/daemon/uninstall` is called without `delete_data`
- **THEN** the agent's MCP entry, memory hook and provider keys are gone, the skill links are gone, the launch agent is gone, the `PATH` line and its marker are gone and `~/.coffer/bin` is gone
- **AND** the answer lists each step and the daemon stops, while `~/.coffer/vault` is unchanged

#### Scenario: deleting the data needs a presence grant
- **GIVEN** a running daemon
- **WHEN** `POST /api/v1/daemon/uninstall` is called with `delete_data` and no valid grant
- **THEN** it is refused and nothing is removed

#### Scenario: the command line will not delete the data without a terminal
- **GIVEN** no desktop app installed
- **WHEN** `coffer uninstall --delete-data --yes` runs with no interactive terminal
- **THEN** it refuses, and nothing is removed

## MODIFIED Requirements

### Requirement: Hand an upgrade of Coffer to an agent
The desktop shell checks for and installs updates itself. A browser has
nothing to install with, and how a copy of Coffer is upgraded depends on how it
was installed, so the daemon MUST answer the token-gated
`GET /api/v1/daemon/upgrade` with the install method it detects — `binaries`
(the installer's or a release archive's frozen binaries), `app` (the macOS
desktop app) or `source` (a source checkout) — and a `handoff` prompt for the
person's agent. The prompt MUST name the running version,
the install method with the daemon's executable (and the checkout for a source
run), the machine, and the install page's Upgrade section, and MUST tell the
agent to keep `~/.coffer` exactly as it is, to restart the daemon, and to
confirm with `coffer --version` and `coffer daemon status` that both report the
new version. For the installer's binaries it MUST say that `coffer update` does
the upgrade and the restart. It carries the standing rules of every hand-off.

#### Scenario: the upgrade hand-off names how this copy was installed
- **GIVEN** a daemon running Coffer 0.3.1 from the installer's frozen binaries
- **WHEN** `GET /api/v1/daemon/upgrade` is read
- **THEN** the answer's install method is `binaries` and its prompt names 0.3.1, the executable, the machine, `coffer update` and the install page's `#upgrade` section
- **AND** the prompt says to keep `~/.coffer` and to verify with `coffer --version` and `coffer daemon status`
