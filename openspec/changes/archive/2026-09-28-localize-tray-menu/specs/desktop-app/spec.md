## MODIFIED Requirements

### Requirement: Host the UI locally in an application window
Coffer MUST ship a macOS desktop shell that hosts the built web UI **as a local asset**, not as a page loaded from the daemon's origin. Hosting it locally is what distinguishes an application from a bookmarked browser window: a daemon that is slow, absent or wedged yields an actionable screen rather than a connection error, and the daemon's port is never visible in an address bar.

The window MUST NOT be shown before a daemon answers. Every surface the UI can offer before then is an apology — a page whose every query reports "not ready" under a banner explaining why — and an application that opens on that reads as broken rather than as early; with the daemon running as a login service ([daemon](../daemon/spec.md)) the wait is normally imperceptible. It MUST be shown once the attempt to reach a daemon has failed, since an invisible app cannot report why it has nothing to show. Building the page MUST NOT wait on the handshake either — the wait belongs to the shell, and a webview that blocks on a retrying handshake would never paint at all.

The shell MUST present a window the OS treats as an application — Dock icon, Cmd-Tab entry — and a resident tray offering at least open, restart daemon, and quit; closing the window MUST hide to the tray rather than exit, and re-activating from the Dock MUST restore it.

The tray's labels, its tooltip and the sync notification MUST be in the interface language the user chose in the web UI, and MUST follow a switch without a restart. The choice lives in the webview's storage, which the shell cannot read, so the page reports it over IPC when it starts and on every switch. Until it has, the tray MUST follow the OS language — the same fallback the page itself uses.

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
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Two host-conditional affordances are sanctioned, both rendered in the offline banner and both reached through the credential supplier's module, because only the shell can offer them: the Restart control, and the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"). Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with. One host-conditional report is sanctioned beside them, in the same module and rendering nothing: the page tells the shell its interface language so the tray can be labelled in it (see "Host the UI locally in an application window"); outside the shell it does nothing, since a browser has no tray.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the credential supplier and the offline banner — which carries the Restart control and the version-skew warning — no frontend module branches on whether it is running inside the shell.
