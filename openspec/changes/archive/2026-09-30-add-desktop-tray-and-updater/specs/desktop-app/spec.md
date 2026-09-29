## ADDED Requirements

### Requirement: Show the daemon and what needs the user in the menu bar
The shell MUST keep an item in the macOS menu bar whose icon is the Stroke C mark as a monochrome template image, so macOS tints it for a light or a dark menu bar, drawn with a solid dot while anything needs the user and dimmed and struck through while no daemon is serving. Its menu MUST offer, in this order: a status line naming the daemon's port and version while it runs, or that it is offline; an entry counting what needs the user — the items of the Overview's attention list, a single sync problem named rather than counted — shown only when there is something, and opening Overview; Open Coffer; New conversation; Settings… (⌘,), opening the Settings modal over the page the user is on; the update entry (see "Check for updates against a signed release manifest"), which reads Check for updates… and, once a check has found a signed release, "Update available — Restart to install" with its version; Start at login, checked when the daemon's login service is installed — the same setting as the web UI's — and switching it; Restart daemon, which reads Start daemon while none is serving, and runs the one restart (see "Restart by stopping the running daemon first"); and Quit Coffer (⌘Q). While no daemon is serving, New conversation, Settings… and Start at login MUST be greyed out and the attention entry MUST be absent. What the menu bar says MUST follow the daemon without the user opening the window: a daemon that stops answering MUST read as offline within one poll, and a launching app MUST allow a cold daemon a few polls before calling it offline.

#### Scenario: the menu bar says whether the daemon is running
- **GIVEN** a daemon serving on port 8000 at version 0.4.2
- **WHEN** the user opens the menu bar item
- **THEN** the first line reads "Daemon running · port 8000 · 0.4.2" and cannot be chosen
- **AND** the icon is the plain mark, Start at login carries its checkmark, and the last two entries are Restart daemon and Quit Coffer

#### Scenario: the menu bar counts what needs the user
- **GIVEN** a daemon whose attention list holds two items
- **WHEN** the menu bar polls it
- **THEN** the icon carries the dot and the menu shows "2 things need you" under the status line
- **AND** choosing it opens the window on Overview

#### Scenario: an offline daemon greys out what needs it
- **GIVEN** the menu bar item of an app whose daemon has stopped
- **WHEN** the next poll finds no daemon answering
- **THEN** the icon is dimmed and struck through, the status line reads "Daemon offline" and the attention entry is gone
- **AND** New conversation, Settings… and Start at login are greyed out, and Restart daemon reads Start daemon

#### Scenario: the menu bar offers an update that is ready
- **GIVEN** a check that found signed version 0.4.3
- **WHEN** the user opens the menu bar item
- **THEN** the update entry reads "Update available — Restart to install 0.4.3"
- **AND** while the update downloads the entry shows its progress and cannot be chosen again

### Requirement: Check for updates against a signed release manifest
The shell MUST check for a newer version of Coffer at launch and every six hours while it runs, unless the user has switched Check automatically off on the web UI's Settings › About tab, and on demand from that tab (spec [web-ui](../web-ui/spec.md) "Check for and install updates on Settings › About") and from the menu bar, through the Tauri updater against a release manifest published on GitHub Releases. A new version otherwise reaches a user only if they think to download a new `.dmg`, and a desktop user is the one least likely to watch a releases page. The check and the download MUST run in the shell's own process, not in the webview, so the webview's content policy stays loopback and IPC only (see "Restrict the webview to loopback and IPC"). A build made without an updater key MUST say it does not check for updates and MUST NOT check.

Every update MUST be signed with the project's updater key and verified against the public key built into the shell — including the version it was signed for — before it is installed; an update whose signature is missing or does not verify MUST be refused and reported, never installed. The release workflow MUST publish, beside each tag's `.dmg`, the updater archive of the same `.app`, its signature, and the manifest naming the version, the archive's URL and the signature. A check at launch or on the timer MUST NOT interrupt the user: it records its time and result for the About tab and the menu bar to show, and only the user's own Download and restart — on the About tab, or the menu bar's Restart to install — downloads and installs anything. Installing MUST download and verify the archive, replace the `.app`, and relaunch the shell; the relaunched shell finds the previous version's daemon and replaces it through the one restart (see "Restart by stopping the running daemon first"), so the new version's daemon answers. A check or download that fails — no network, an unreachable manifest, a refused signature — MUST be reported to the About tab and recorded (see "Write the shell's records into the daemon log"), and MUST leave the running version untouched.

#### Scenario: the shell checks at launch and every six hours
- **GIVEN** the shell launched with a newer signed release on the manifest
- **WHEN** it starts, and again after six hours of running
- **THEN** each time it checks the manifest without showing a dialog, and records the check's time and the newer version for the About tab
- **AND** nothing is downloaded or installed until the user chooses Download and restart

#### Scenario: an update is installed only with a valid signature
- **GIVEN** a manifest whose archive's signature does not verify against the shell's built-in public key
- **WHEN** the user chooses Download and restart
- **THEN** the shell refuses the update, reports the refused signature to the About tab and the daemon log, and keeps running the current version

#### Scenario: installing an update relaunches onto the new version
- **GIVEN** a newer signed release and a daemon from the running version
- **WHEN** the user chooses Download and restart and the archive verifies
- **THEN** the shell replaces the `.app`, relaunches, and restarts the previous version's daemon through the one restart
- **AND** the About tab and the daemon status both report the new version

#### Scenario: a release publishes the update manifest
- **GIVEN** a release tag matching `v*` is pushed with the updater key in the repository's secrets
- **WHEN** the release workflow finishes
- **THEN** the release carries, beside the `.dmg`, the updater archive, its signature and a manifest naming that version, the archive's URL and the signature

### Requirement: Sign and notarise a release when its credentials are present
When the repository holds a Developer ID Application certificate and its Team ID, the release workflow MUST sign the three frozen binaries — and every library they unpack — and the app with that Developer ID under the hardened runtime, without `get-task-allow`, with the `keychain-access-groups` entitlement for `<Team ID>.coffer`, and MUST stamp the same group into the daemon's and the shell's build so the master key is kept where only those binaries can read it ([credentials](../credentials/spec.md) "Keep the master key behind a storage port chosen by the build"). When it also holds an App Store Connect API key it MUST notarise the CLI binaries, the app and the `.dmg`, and staple the app and the `.dmg`. Each of these steps MUST run only when the credentials it needs are present, and a run without them MUST say which are missing and still build and publish the unsigned release, so the pipeline stays green before the owner has an Apple Developer Program membership.

#### Scenario: a release without signing credentials builds unsigned
- **GIVEN** a release run with no Developer ID, notary or updater secrets
- **WHEN** the workflow runs
- **THEN** every signing, notarisation and updater step is skipped with a line naming the missing secret
- **AND** the run publishes the unsigned CLI archive and `Coffer-unsigned-<triple>.dmg` as before

#### Scenario: a signed release carries the hardened runtime and its keychain access group
- **GIVEN** a release run holding the Developer ID certificate, its password and the Team ID
- **WHEN** the binaries and the app are built
- **THEN** each is signed by that team under the hardened runtime with `keychain-access-groups` for `<Team ID>.coffer` and without `get-task-allow`
- **AND** `build_identity.KEYCHAIN_ACCESS_GROUP` in the frozen daemon, and the shell's compiled access group, are that same `<Team ID>.coffer`

## MODIFIED Requirements

### Requirement: Host the UI locally in an application window
Coffer MUST ship a macOS desktop shell that hosts the built web UI **as a local asset**, not as a page loaded from the daemon's origin. Hosting it locally is what distinguishes an application from a bookmarked browser window: a daemon that is slow, absent or wedged yields an actionable screen rather than a connection error, and the daemon's port is never visible in an address bar.

The window MUST NOT be shown before a daemon answers. Every surface the UI can offer before then is an apology — a page whose every query reports "not ready" under a banner explaining why — and an application that opens on that reads as broken rather than as early; with the daemon running as a login service ([daemon](../daemon/spec.md)) the wait is normally imperceptible. It MUST be shown once the attempt to reach a daemon has failed, since an invisible app cannot report why it has nothing to show. Building the page MUST NOT wait on the handshake either — the wait belongs to the shell, and a webview that blocks on a retrying handshake would never paint at all.

The shell MUST present a window the OS treats as an application — Dock icon, Cmd-Tab entry — and a resident menu bar item (see "Show the daemon and what needs the user in the menu bar"); closing the window MUST hide to the menu bar rather than exit, and re-activating from the Dock MUST restore it.

The menu bar item's labels, its tooltip and the sync notification MUST be in the interface language the user chose in the web UI, and MUST follow a switch without a restart. The choice lives in the webview's storage, which the shell cannot read, so the page reports it over IPC when it starts and on every switch. Until it has, the tray MUST follow the OS language — the same fallback the page itself uses.

#### Scenario: the window waits for a daemon, and opens either way
- **GIVEN** the app is launched with no daemon running,
- **WHEN** the app starts one,
- **THEN** no window is shown until that daemon answers, so the application is never on screen in a state where nothing in it works,
- **AND** the window is shown anyway once the attempt has failed, because an invisible app cannot report that it could not start a daemon,
- **AND** the page itself is built without waiting on the handshake, so the wait is the shell's and not a blank webview's.

#### Scenario: closing the window hides the app to the tray
- **GIVEN** the app is running with its window open,
- **WHEN** the user closes the window,
- **THEN** the process stays alive with its tray entry intact instead of exiting,
- **AND** re-activating from the Dock restores the window.

#### Scenario: the tray speaks the interface language
- **GIVEN** the user has chosen Chinese as the interface language,
- **WHEN** the app starts,
- **THEN** the tray reads 打开 Coffer, 重启守护进程 and 退出 Coffer,
- **AND** switching the interface to English relabels the tray in English without a restart.

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Two host-conditional affordances are sanctioned in the offline banner, both reached through the credential supplier's module, because only the shell can offer them: the Restart control, and the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"). A third is sanctioned on the web UI's Settings › About tab: the update check and install (see "Check for updates against a signed release manifest"), reached through the credential supplier's update half (`shellUpdates.ts`, which reaches the shell only through the supplier's own invoke and event helpers); in a browser that tab says updates are installed by the desktop app and offers no control. The presence-gated actions — reveal and copy a secret, write a master key backup, approve a pending approval — are sanctioned the same way, reached through the same module (see "Release plaintext and approvals only after a presence check in the shell"): outside the shell they answer that they are unavailable, and the page offers "Open in Coffer app" in their place. Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with. One host-conditional report is sanctioned beside them, in the same module and rendering nothing: the page tells the shell its interface language so the tray can be labelled in it (see "Host the UI locally in an application window"); outside the shell it does nothing, since a browser has no tray.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the credential supplier (with its update half) and the offline banner — which carries the Restart control and the version-skew warning — no frontend module branches on whether it is running inside the shell; the presence-gated actions and the About tab's update check are reached through the credential supplier's modules.

### Requirement: Reimplement no daemon route in the shell
The shell MUST NOT reimplement any capability the daemon already exposes over HTTP. Native folder selection, opening a file in the user's editor and revealing it in the file manager are daemon routes, and a webview reaches them exactly as a browser tab does; duplicating them in the shell would reintroduce a host-conditional branch in the frontend for no user-visible gain. It MUST declare no native dialog or opener plugin. A native plugin is admissible only where the daemon **cannot** stand in, and then only on the Rust side, with no permission granted to the webview: a system notification is one such case, because there is no loopback route that raises one and only the installed bundle can post a notification as Coffer at all ([vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is"); the updater is the other, because a process the app spawned cannot replace the app it runs inside (see "Check for updates against a signed release manifest"). The presence check behind a reveal, a key backup or an approval is not a daemon route and is the shell's alone: a LocalAuthentication prompt can only be raised by the installed app, and the grant it produces is what the daemon's presence-gated routes require (see "Release plaintext and approvals only after a presence check in the shell"); the folder a key backup goes into is still picked through the daemon's folder route. The shell MUST NOT deploy binaries into `~/.coffer/bin/` — that is the daemon's frozen-start job ([daemon](../daemon/spec.md), distribution), and two processes writing that directory race.

#### Scenario: the shell reimplements no daemon route
- **GIVEN** the shell's source,
- **WHEN** its capabilities and dependencies are read,
- **THEN** it declares no dialog or opener plugin, grants the webview no updater permission, and writes nothing into `~/.coffer/bin/`,
- **AND** the webview's content policy allows loopback and IPC and nothing else.

### Requirement: Document clearing the quarantine attribute
A release built without a Developer ID is neither signed nor notarised (see "Sign and notarise a release when its credentials are present"), so a browser-downloaded `.dmg` from it carries macOS's quarantine attribute and the app is refused on double-click. Such a `.dmg` MUST say so in its name (`Coffer-unsigned-…`), and the release notes and the README MUST carry the quarantine-clearing step as prominently as they carry it for the terminal tier, for as long as an unsigned build can be published.

#### Scenario: the install instructions carry the quarantine-clearing step for the app
- **GIVEN** the release notes the release workflow publishes and the README,
- **WHEN** a user reads how to install the `.dmg`,
- **THEN** each carries the exact command that clears the quarantine attribute from `/Applications/Coffer.app`,
- **AND** the release notes carry it in the same notice as the terminal tier's quarantine step.
