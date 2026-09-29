## 1. Menu bar item

- [x] 1.1 Template icons: `desktop/icons/tray/{tray,tray-attention,tray-offline}.svg` from the Stroke C mark (canvas 1.5), rendered to 18 px and 36 px PNGs by `scripts/render_tray_icons.sh`
- [x] 1.2 `tray_state.rs`: status line, attention entry (count; a single sync problem named), update entry, Start at login, Restart/Start daemon, greyed items while offline, icon and tooltip — all pure
- [x] 1.3 `tray.rs`: build the menu in the canvas order with ⌘, and ⌘Q, write the state onto it, insert/remove the attention entry, repaint the icon only when it changes; `tray_nav.rs` opens a page or the Settings modal over the current page
- [x] 1.4 `tray_watch.rs`: one poll of `daemon.json` + `/daemon/status` every 10 s, attention and residency every 60 s and on reconnect, woken by tray actions; Start at login through `PUT /api/v1/daemon/residency`
- [x] 1.5 `sync_watch.rs` runs per tick from the watcher, marks the menu bar through `tray::set_sync_alert`, keeps the notification and Dock badge; the Sync entry and `badge_rgba` go
- [x] 1.6 Tray labels in English and Chinese (`tray_locale.rs`)

## 2. Auto-update

- [x] 2.1 `tauri-plugin-updater`, registered with the compile-time `COFFER_UPDATER_PUBKEY`; `plugins.updater` endpoint and `requireSignedVersion` in `tauri.conf.json`; no webview permission
- [x] 2.2 `update_state.rs`: the status record and its transitions (busy refusal, failed check keeps the last good result, install needs an offered update), six-hourly wall-clock schedule
- [x] 2.3 `updater.rs`: launch + six-hourly checks honouring Check automatically, `update_status` / `check_for_updates` / `install_update` / `set_update_auto_check` commands, `coffer://update` events, failures logged under `coffer.desktop`
- [x] 2.4 `update_relaunch.rs`: the relaunched shell replaces a skewed daemon through `restart_daemon` once
- [x] 2.5 Frontend: `lib/shellUpdates.ts` through `shellInvoke` / `onShellEvent` in `lib/tauri.ts`, `useShellUpdates`, `UpdatesSection` on About, the Check automatically preference reported from `main.tsx`; en/zh strings

## 3. Release pipeline

- [x] 3.1 `scripts/release_plan.py`: presence-only gating with one annotation per skipped step, and the `tauri build --config` merge
- [x] 3.2 `scripts/release_signing.sh`: temporary keychain import, entitlements rendering, signature verification, notarytool, stapler, cleanup
- [x] 3.3 `scripts/stamp_build_identity.py` and `desktop/entitlements/coffer.entitlements.in` (`keychain-access-groups` for `<TEAM_ID>.coffer`); PyInstaller specs sign with `COFFER_CODESIGN_IDENTITY` / `COFFER_ENTITLEMENTS_FILE`
- [x] 3.4 `release.yml`: plan, identity, stamp, verify, notarise the CLI binaries, sign/notarise the app through Tauri, notarise and staple the `.dmg`, the updater archive + `latest.json` (`scripts/make_update_manifest.py`), keychain cleanup; release notes for signed and unsigned builds

## 4. Tests

- [x] 4.1 `acceptance(desktop-app, …)` for "the menu bar says whether the daemon is running", "the menu bar counts what needs the user", "an offline daemon greys out what needs it", "the menu bar offers an update that is ready" (`tray_state_tests.rs`)
- [x] 4.2 `acceptance(desktop-app, …)` for "the shell checks at launch and every six hours", "an update is installed only with a valid signature" (`update_state_tests.rs`) and "installing an update relaunches onto the new version" (`update_relaunch.rs`)
- [x] 4.3 `acceptance(desktop-app, …)` for "a release publishes the update manifest", "a release without signing credentials builds unsigned", "a signed release carries the hardened runtime and its keychain access group" (`test_release_signing.py`); "the shell hosts the one build the daemon serves" and "the shell reimplements no daemon route" follow the modified requirements (`test_desktop_shell_surface.py`)
- [x] 4.4 `acceptance(web-ui, …)` for "about shows the version and when updates were last checked", "checking by hand finds a newer version", "download and restart installs the newer version", "a failed check keeps the last good result", "about in a browser offers no update control" (`UpdatesSection.test.tsx`)

## 5. Docs

- [x] 5.1 `docs-site/architecture/distribution.md`: signing, notarisation, the updater feed, what the owner must provide
- [x] 5.2 `RELEASING.md`: the owner's checklist
- [x] 5.3 `docs-site/guides/desktop-app.md`: the menu bar and updates
- [x] 5.4 ADR distribution-pyinstaller: Option K is built, gated on credentials
- [x] 5.5 `desktop-app` Purpose: auto-update in scope; the IPC commands and the release's updater feed

## 6. Verify and archive

- [x] 6.1 `make verify`, `make desktop-lint`, `make desktop-test`
- [x] 6.2 Archive the change (`npx openspec archive add-desktop-tray-and-updater --yes`)
