## MODIFIED Requirements

### Requirement: Release plaintext and approvals only after a presence check in the shell
The shell MUST expose, over IPC, revealing a secret, writing a master key
backup, approving a pending approval and reporting whether the daemon is a
development build, and MUST run a fresh LocalAuthentication check
(`deviceOwnerAuthentication`: Touch ID or the login password) before each one,
with no reuse window. The operating system's prompt MUST name what it approves —
the secret, the backup, or the approval's own description — and in a
development build MUST say so. Only after the check passes does the shell ask
the daemon for a challenge, sign it with the grant key derived from the master
key ([secret](../secret/spec.md) "Release plaintext only to a
present human in the desktop app") and send the request; a cancelled check
sends nothing. The backup command takes the passphrase the page collected,
refuses one under eight characters before the presence check, and MUST pass it
only in the daemon's export request — never into a log, a stored file or the
signed grant. The shell reads the master key at the moment of signing — from
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
