## Context

Three install methods exist (`application/upgrade_handoff.py`): the desktop
app, the installer's frozen binaries and a source checkout. The app updates
itself (spec desktop-app "Check for updates against a signed release
manifest"); the other two have only the agent hand-off on Settings › About.
Coffer writes into files it does not own: the agents' MCP config, settings and
hooks, their skill folders, `~/Library/LaunchAgents`, shell profiles and Warp's
launch configurations. Removing those by hand is the four-step Uninstall
section of the install page.

## Goals / Non-Goals

**Goals:** one command upgrades the frozen binaries; the daemon tells a
command-line-only machine that a release exists; one action removes Coffer's
footprint outside `~/.coffer`; deleting `~/.coffer` is separate, explicit and
gated by the person's presence where the app can check it.

**Non-goals:** a silent background install (the app's own rule — nothing
installs until the person asks — holds for the binaries too); updating a
source checkout; release channels or branches (ADR
experimental-features-instead-of-a-release-branch); restoring the agents'
own MCP entries that "Import from your agents" moved into Coffer (their
backups stay in `~/.coffer/config-backups`).

## Decisions

### D1. The update reuses the installer's semantics

`coffer update` downloads `coffer-cli-<triple>.tar.gz` and `SHA256SUMS` from the
newest release, refuses an archive whose checksum does not match, and copies
each binary over its public name in `~/.coffer/bin` by a temporary sibling and a
rename, exactly as `install.sh` does. It then stops the daemon and starts the
new `~/.coffer/bin/coffer-daemon`, which deploys itself into its versioned
directory and re-points the links (spec daemon "Deploy frozen
sibling binaries and back up the history database before migrating"), so rollback and pruning stay one mechanism. The
checksum file comes from the same release, so this protects against a broken
download, not against whoever controls the release — the same trust the
installer asks for. The app keeps its minisign-verified updater; on a machine
whose daemon is the app's, `coffer update` asks the app to install
(`app update install`).

The newest release is read from the GitHub API's `releases/latest`, the same
"latest, not a pre-release" the app's manifest URL follows.

### D2. The daemon checks only for the binaries it runs from

A daemon running from the installer's binaries checks the release once a
minute after it starts and then daily, like the price-list refresh: one `GET`,
bounded in time and size, nothing about the user sent, a failure logged once per
streak. `update_check` in `daemon-config.json` switches it off
(`COFFER_UPDATE_CHECK=off` pins it off, for tests). A daemon running from the app
leaves checking to the shell; a source run never checks. The result is on
`GET /daemon/upgrade`.

### D3. Uninstall is a daemon operation, then a stop

The daemon owns every footprint and the services that remove them, so
`POST /api/v1/daemon/uninstall` does the work and then stops itself; the
command line and the app only start it and finish around it. Order matters:

1. Inside `Reconciler.hold()`: take the model-provider routing out of every
   agent (`ProviderService.deactivate`), disconnect every agent
   (`AgentConnectionService.disconnect` — MCP entry and memory hook), and remove
   every skill link with its binding rows (`SkillService.cleanup_bindings_for_agent`).
   Provider routing and MCP entries both run Coffer binaries, so they go first.
2. Freeze the reconciler for the rest of the process, so a periodic pass cannot
   put a link back before the daemon exits.
3. Remove the start-at-login job (`login_service.uninstall`), Warp launch files
   (`~/.warp/launch_configurations/coffer-*.yaml`), the installer's `PATH`
   lines (the `# Added by Coffer installer` marker and the line after it, in the
   profiles `install.sh` writes) and `~/.coffer/bin`.
4. Answer with one row per step (done, nothing to do, or failed with the
   reason), then stop through the one graceful exit path.

Each step is best-effort and reported; one failure does not stop the others.
Skill intent, provider records other than the switch, the vault and every
setting stay, so a reinstall finds the vault and delivers the skills again; the
agents have to be connected again, because "connected" is the entry in their
own files.

### D4. Deleting the data happens after the daemon has stopped

`~/.coffer` holds the daemon's open database and its logs, so it is deleted
after the server has stopped: the daemon's exit path runs the purge last, after
the lock and `daemon.json` are released. The purge deletes the master key's
Keychain items (the access-group item and its `master-key.bak-*` copies, by one
delete without an account; in a development build, the login-keychain item)
and then the folder.

Who may ask for it:

- **The desktop app** sends `delete_data` with a presence grant for the new op
  `uninstall` over the target `delete-data`. The daemon redeems it before it
  changes anything; an unverified grant refuses the whole request.
- **The command line** never sends `delete_data`. `coffer uninstall
  --delete-data` asks at an interactive terminal for the words `delete my data`,
  runs the uninstall, waits for the daemon to exit, and purges in its own
  process with the same function. No flag skips the question and a non-TTY run
  refuses, so an agent calling the CLI cannot delete the vault (it could `rm -rf`
  it, but Coffer adds no new way to).
- With the desktop app installed, `coffer uninstall` opens the app's dialog
  (desktop request `uninstall`), where Touch ID gates the data.

### D5. The app finishes by trashing itself

The shell sets an "uninstalling" flag first, so neither the menu bar's restart
nor the handshake starts a daemon again. After the daemon answers it waits for
the daemon to exit, returns the report to the page, moves its own `.app` to the
Trash (`NSFileManager trashItemAtURL`) and quits. Running agent sessions keep
their already-started shim until they restart; that shim finds no daemon
binary to start.

## Risks / Trade-offs

- **Skills that were adopted from an agent leave with the link.** Adoption moved
  the agent's folder into `~/.coffer/vault/skills`. Kept data restores them on
  reinstall; deleting the data deletes them. The dialog and the docs say so, and
  the folder is where to copy one from first.
- **An agent with the token can uninstall (not purge).** Any token holder can
  already disconnect agents and stop the daemon one route at a time; the
  irreversible part needs presence or a terminal.
- **GitHub API rate limits** (60 an hour unauthenticated) are far above one
  check a day.
