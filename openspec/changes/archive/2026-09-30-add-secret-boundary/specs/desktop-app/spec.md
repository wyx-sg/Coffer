## ADDED Requirements

### Requirement: Release plaintext and approvals only after a presence check in the shell
The shell MUST expose, over IPC, revealing a secret, writing a master key
backup, approving a pending approval and reporting whether the daemon is a
development build, and MUST run a fresh LocalAuthentication check
(`deviceOwnerAuthentication`: Touch ID or the login password) before each one,
with no reuse window. The operating system's prompt MUST name what it approves —
the secret, the backup, or the approval's own description — and in a
development build MUST say so. Only after the check passes does the shell ask
the daemon for a challenge, sign it with the grant key derived from the master
key ([credentials](../credentials/spec.md) "Release plaintext only to a
present human in the desktop app") and send the request; a cancelled check
sends nothing. The shell reads the master key at the moment of signing — from
the signed release's Keychain access group, or in a development build from the
key file — and MUST NOT store or cache it or the grant key. In a development
build without LocalAuthentication the check MUST fall back to a modal
confirmation in the app window, never to no check. The shell MUST raise one
native notification per pending approval it has not seen, and tell the page so
its approval sheet opens.

#### Scenario: a presence grant signs exactly the approved operation
- **GIVEN** a master key and a challenge for one operation and one target
- **WHEN** the shell signs it
- **THEN** the signature is the one the daemon computes for that operation, target and nonce, and differs for any other

#### Scenario: every presence prompt names what it approves
- **GIVEN** a reveal, a key backup and an approval
- **WHEN** the shell builds each presence prompt
- **THEN** each names its operation and target, and in a development build each says it is a development build

#### Scenario: a pending approval raises one notification
- **GIVEN** the daemon lists a pending approval the shell has not seen
- **WHEN** the shell polls twice
- **THEN** it raises one notification for it, and none for an approval it already announced

## MODIFIED Requirements

### Requirement: Consume the one frontend build the daemon serves
The shell MUST consume the same `frontend/dist` build the daemon serves. It adds a credential *supplier* (see "Supply the page its daemon connection over IPC") and MUST NOT introduce a second frontend code path, a host-conditional branch, or a separate UI build — one artifact is what keeps the two hosts from drifting. Two host-conditional affordances are sanctioned in the offline banner, both reached through the credential supplier's module, because only the shell can offer them: the Restart control, and the version-skew check that warns when the shell has reached a daemon from an earlier app version (see "Find or start a daemon by a fixed resolution order"). The presence-gated actions — reveal and copy a secret, write a master key backup, approve a pending approval — are sanctioned the same way, reached through the same module (see "Release plaintext and approvals only after a presence check in the shell"): outside the shell they answer that they are unavailable, and the page offers "Open in Coffer app" in their place. Outside the shell the skew check always answers "matches", since a browser is served by whichever daemon is running and has no pairing to be out of step with. One host-conditional report is sanctioned beside them, in the same module and rendering nothing: the page tells the shell its interface language so the tray can be labelled in it (see "Host the UI locally in an application window"); outside the shell it does nothing, since a browser has no tray.

#### Scenario: the shell hosts the one build the daemon serves
- **GIVEN** the shell's bundle configuration and the daemon's frozen-build recipe,
- **WHEN** each names the web UI it ships,
- **THEN** both name the repository's `frontend/dist`, produced by the frontend's single `npm run build`,
- **AND** outside the credential supplier and the offline banner — which carries the Restart control and the version-skew warning — no frontend module branches on whether it is running inside the shell; the presence-gated actions are reached through the credential supplier's module.

### Requirement: Reimplement no daemon route in the shell
The shell MUST NOT reimplement any capability the daemon already exposes over HTTP. Native folder selection, opening a file in the user's editor and revealing it in the file manager are daemon routes, and a webview reaches them exactly as a browser tab does; duplicating them in the shell would reintroduce a host-conditional branch in the frontend for no user-visible gain. It MUST declare no native dialog or opener plugin. A native plugin is admissible only where the daemon **cannot** stand in: a system notification is the one such case today, because there is no loopback route that raises one and only the installed bundle can post a notification as Coffer at all ([vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is"). The presence check behind a reveal, a key backup or an approval is not a daemon route and is the shell's alone: a LocalAuthentication prompt can only be raised by the installed app, and the grant it produces is what the daemon's presence-gated routes require (see "Release plaintext and approvals only after a presence check in the shell"); the folder a key backup goes into is still picked through the daemon's folder route. The shell MUST NOT deploy binaries into `~/.coffer/bin/` — that is the daemon's frozen-start job ([daemon](../daemon/spec.md), distribution), and two processes writing that directory race.

#### Scenario: the shell reimplements no daemon route
- **GIVEN** the shell's source,
- **WHEN** its capabilities and dependencies are read,
- **THEN** it declares no dialog or opener plugin and writes nothing into `~/.coffer/bin/`,
- **AND** the webview's content policy allows loopback and IPC and nothing else.
