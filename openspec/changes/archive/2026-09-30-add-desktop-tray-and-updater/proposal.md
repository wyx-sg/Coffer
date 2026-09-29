## Why

The desktop app's tray offered three items — open, restart, quit — and an icon that was the full-colour app icon with a red dot painted on it. It said nothing about whether the daemon was up, on which port or which version, or that something on Overview needed the user; a user who had closed the window had no way to tell a healthy Coffer from a dead one. A new version reached a desktop user only if they went looking for a new `.dmg`, and the release pipeline could not produce anything but an unsigned, un-notarised build: the master key's Keychain access group, the hardened runtime and notarisation (ADR master-key-lives-in-the-macos-keychain) all wait on a signed release, and nothing in the workflow could make one even once the credentials exist.

## What Changes

- **Menu bar item** (design canvas 1.5 Menu bar). A monochrome template image of the Stroke C mark that macOS tints for light and dark menu bars, with a solid dot when something needs the user and dimmed and struck through when no daemon is serving. The menu, in order: a status line (Daemon running · port · version, or Daemon offline); "N things need you" when the attention list has items (a single sync problem is named), opening Overview; Open Coffer; New conversation; Settings… ⌘, opening the Settings modal; Check for updates… — "Update available — Restart to install X" once a check has found one; Start at login with a checkmark (the Settings › Daemon setting); Restart daemon, or Start daemon while offline; Quit Coffer ⌘Q. Offline, the items that need a daemon are greyed out. Labels follow the interface language. One light loopback poll feeds it; the sync alert's notification and Dock badge are unchanged, and the separate Sync menu entry is folded into "needs you".
- **Auto-update.** The shell checks a manifest (`latest.json`) on the newest GitHub Release at launch and every six hours (unless the user switches Check automatically off), and on demand from Settings › About or the menu bar. The archive is verified against an updater public key compiled into the shell, including the version it was signed for. Nothing installs until the user chooses Download and restart; the relaunched shell replaces the previous version's daemon through the one restart. A failed check or install is shown on About, recorded in the daemon log, and leaves the running version untouched. In a browser, About says updates are installed by the desktop app and offers no control.
- **Settings › About** shows the update state — up to date, a newer version with its notes and Download and restart with progress, or a failed check that keeps the last successful check's time — and the Check automatically switch.
- **Release signing.** The release workflow signs the frozen binaries (through PyInstaller, so every library they unpack is signed too) and the app with a Developer ID under the hardened runtime with the `keychain-access-groups` entitlement for `<TEAM_ID>.coffer`, stamps that group into `build_identity.py` and the shell, notarises the CLI binaries, the app and the `.dmg`, staples the app and the `.dmg`, and publishes the signed updater archive and `latest.json` beside the `.dmg`. Each step runs only when its credentials are present and logs which secret is missing when not, so a build without them is the unsigned build it was and stays green. `RELEASING.md` lists what the owner must create.

## Capabilities

### New Capabilities

### Modified Capabilities
- `desktop-app`: the menu bar item; the update check and install against a signed manifest; signing and notarisation gated on credentials; the updater admitted as a Rust-only plugin; the frontend's update check sanctioned as host-conditional; the quarantine step documented for unsigned builds only.
- `web-ui`: Settings › About carries the update check and the Check automatically switch.
- `experimental-features`: switching `vault_sync` off clears the menu bar's sync marks; there is no separate Sync menu entry to remove.

## Impact

- Desktop: `desktop/src/{tray,tray_state,tray_watch,tray_nav,updater,update_state,update_relaunch}.rs`; `sync_watch.rs` runs per tick from `tray_watch.rs` and no longer owns a menu entry or paints the icon; `tauri-plugin-updater`; `plugins.updater` in `tauri.conf.json`; template icons under `desktop/icons/tray/` rendered by `scripts/render_tray_icons.sh`; entitlements template under `desktop/entitlements/`.
- Frontend: `lib/shellUpdates.ts`, `lib/hooks/useShellUpdates.ts`, `pages/settings/UpdatesSection.tsx`; `lib/tauri.ts` gains `shellInvoke` / `onShellEvent`.
- Release: `.github/workflows/release.yml`; `scripts/{release_plan.py,release_signing.sh,stamp_build_identity.py,make_update_manifest.py}`; the PyInstaller specs read the signing identity and entitlements from the environment.
- Docs: `docs-site/architecture/distribution.md`, `docs-site/guides/desktop-app.md`, `RELEASING.md`, the distribution ADR's Option K.
