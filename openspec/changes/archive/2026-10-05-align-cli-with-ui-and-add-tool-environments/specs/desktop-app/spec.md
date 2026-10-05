## ADDED Requirements

### Requirement: Serve the command line's desktop requests
The shell MUST serve the requests the command line leaves with the daemon (`/api/v1/desktop/requests`):
it asks for the next one about once a second — each ask is how the daemon knows the app is running —
and runs the same presence-checked flow its own buttons run, one request at a time. For an approval
request it MUST read each approval from the daemon, refuse one whose target fingerprint is not the
one the request was pinned to, show the operating system's prompt and sign the grant pinned to that
target ("Release plaintext and approvals only after a presence check in the shell"); for a reveal it
MUST run the reveal flow and show the value in the window, sending it nowhere else; for a key backup
it MUST open the page's own backup dialog, where the person types the passphrase; and for the update
commands it MUST run the updater and report its state. It then tells the daemon how the request
ended — done, cancelled or failed with its reason — which approves nothing by itself. The shell
never acts on a request by clicking or scripting its own window.

#### Scenario: the shell serves a command line approval
- **GIVEN** a desktop request for two approvals, each pinned to its target
- **WHEN** the shell claims it
- **THEN** it reads both approvals from the daemon, shows one prompt naming them, signs over exactly those approvals and targets, and reports the request done
- **AND** a request whose approval's target moved is reported failed, with nothing signed
