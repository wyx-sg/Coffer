## 1. Updates for the installer's binaries

- [x] 1.1 Release lookup module: latest release from the GitHub API, semver compare, bounded fetch
- [x] 1.2 Daemon release check (first after a minute, then daily; `update_check` switch, env pin) for binaries only
- [x] 1.3 `GET /daemon/upgrade` reports the check; `POST /daemon/upgrade/check`; `PUT /daemon/upgrade/auto-check`
- [x] 1.4 The binaries hand-off names `coffer update`
- [x] 1.5 `coffer update [--check]`: download, verify SHA256SUMS, swap binaries, restart the daemon; app and source branches

## 2. Uninstall

- [x] 2.1 Uninstall service: provider routing, disconnect, skill links, reconciler freeze, login job, Warp files, PATH lines, `~/.coffer/bin`
- [x] 2.2 Presence grant op `uninstall`; data purge (Keychain items, `~/.coffer`) after the server stops
- [x] 2.3 `POST /daemon/uninstall` with its step report, then stop
- [x] 2.4 `coffer uninstall [--yes] [--delete-data]`: app delegation, terminal confirmation, purge after exit
- [x] 2.5 Desktop: `uninstall_coffer` command (presence, no daemon restarts, wait, Trash, quit) and the `uninstall` desktop request

## 3. Web UI

- [x] 3.1 About › Updates in a browser shows the daemon's check, its switch and `coffer update`
- [x] 3.2 About › Uninstall section and dialog (desktop), command (browser); `?uninstall=1`

## 4. Docs, contracts and canvas

- [x] 4.1 `make contracts`; CLI reference and coverage
- [x] 4.2 Install page Upgrade and Uninstall, desktop app guide, daemon guide, distribution, filesystem (en and zh)
- [x] 4.3 Shell canvas: About boards for the browser updates state and the uninstall section and dialog
