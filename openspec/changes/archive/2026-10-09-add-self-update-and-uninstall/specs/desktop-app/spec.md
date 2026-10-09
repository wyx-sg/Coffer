## ADDED Requirements

### Requirement: Uninstall Coffer from the app
The shell MUST offer uninstalling Coffer to the page as one command that takes
whether to delete the data. With the data, it MUST first run the presence check
(Touch ID or the login password) with a prompt that says the data will be
deleted, and send the daemon's uninstall a grant for `uninstall` over
`delete-data`; a cancelled check sends nothing. Before it calls the daemon it
MUST stop starting daemons — no handshake, menu bar restart or update relaunch
starts one again in this run. It then calls the daemon's uninstall (spec
[daemon](../daemon/spec.md) "Uninstall Coffer from this machine"), waits for the
daemon to exit, returns the daemon's step list to the page, moves its own `.app`
to the Trash and quits. A failed call MUST leave the app running, report the
reason to the page, and start daemons again.

#### Scenario: uninstalling from the app removes Coffer and the app
- **GIVEN** the app running with its daemon
- **WHEN** the page asks the shell to uninstall without deleting the data
- **THEN** the shell calls the daemon's uninstall, waits for the daemon to exit, returns its steps, moves the `.app` to the Trash and quits

#### Scenario: deleting the data waits for the person's presence
- **GIVEN** the page asking the shell to uninstall and delete the data
- **WHEN** the person cancels the Touch ID prompt
- **THEN** nothing is sent to the daemon and the app keeps running

## MODIFIED Requirements

### Requirement: Serve the command line's desktop requests
The shell MUST serve the requests the command line leaves with the daemon (`/api/v1/desktop/requests`):
it asks for the next one about once a second — each ask is how the daemon knows the app is running —
and runs the same presence-checked flow its own buttons run, one request at a time. For an approval
request it MUST read each approval from the daemon, refuse one whose target fingerprint is not the
one the request was pinned to, show the operating system's prompt and sign the grant pinned to that
target ("Release plaintext and approvals only after a presence check in the shell"); for a reveal it
MUST run the reveal flow and show the value in the window, sending it nowhere else; for a key backup
it MUST open the page's own backup dialog, where the person types the passphrase, and keep the
request open while that dialog is: it ends the request done only once its own export has written
the file, with the path and key fingerprint the daemon answered (never a path the page reports),
and cancelled when the dialog closes without one; for the update commands it MUST run the
updater and report its state; and for an uninstall it MUST open the page's own uninstall dialog
(with Also delete my data ticked when the command asked for it) and report that it opened it — the
person confirms there. It then tells the daemon how the request ended — done, cancelled or
failed with its reason — which approves nothing by itself. The shell
never acts on a request by clicking or scripting its own window.

#### Scenario: the shell serves a command line approval
- **GIVEN** a desktop request for two approvals, each pinned to its target
- **WHEN** the shell claims it
- **THEN** it reads both approvals from the daemon, shows one prompt naming them, signs over exactly those approvals and targets, and reports the request done
- **AND** a request whose approval's target moved is reported failed, with nothing signed

#### Scenario: the shell opens the uninstall dialog for the command line
- **GIVEN** a desktop request `uninstall` asking to delete the data
- **WHEN** the shell claims it
- **THEN** it opens Settings › About's uninstall dialog with Also delete my data ticked and reports the request done, uninstalling nothing itself
