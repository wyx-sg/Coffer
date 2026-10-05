## ADDED Requirements

### Requirement: Approve from the command line with the person's own presence check
`coffer approval list`, `show`, `approve` and `reject` MUST manage approvals from the command line.
`coffer approval approve <id>…` MUST NOT approve anything itself: it asks the daemon for a desktop
request naming exactly the approvals given, each still pending and pinned to the target fingerprint
it names at that moment, and waits; the desktop app's shell runs the operating system's presence
check (Touch ID or the login password) whose prompt names each action, destination — with the
custom-tool environment — target and secret, signs a grant over exactly what it showed, and calls
the approve route ("Release plaintext and approvals only after a presence check in the shell"). A
single approval's grant MUST be signed over `<id>@<fingerprint>` and the daemon MUST apply it only
while the approval is still pending for that fingerprint, re-evaluating destinations first; a target
that moved is refused with `APPROVAL_TARGET_CHANGED` and nothing is applied, and a grant is good for
one request. The command then reports each approval's state as the daemon holds it — not what the
shell said — and exits `0` when every one is approved and `11` otherwise. A check the person
cancels, that fails, that times out, or that cannot run leaves every approval pending and sends no
request that needs it. When no shell has polled the daemon lately the command MUST start the
desktop app and wait for it, and where it cannot (no app, not a Mac) exit `12` with nothing
approved; nothing clicks or scripts the app's window. No flag — `--yes`, `--force` or any other —
skips the check. Several ids MUST be confirmed together only when each was named, is still pending
and was shown to the person; one that cannot be one of several (turning the protection off, a grant
to local programs) gets its own prompt. No agent receives the master key, a grant, a nonce, a
signature or a secret's value: `coffer secret reveal <ref>` and `coffer secret backup-key` start the
app's own reveal and backup, whose value is shown, and whose passphrase is typed, in the app.

#### Scenario: a command line approval asks the person and applies after the check
- **GIVEN** a pending approval and the desktop app running
- **WHEN** an agent runs `coffer approval approve <id> --json` and the person passes the presence check
- **THEN** the system prompt names what the approval sends and where, the approval is applied, and the command prints it `approved` and exits 0

#### Scenario: a check that is not confirmed leaves the approval pending
- **GIVEN** a pending approval and the desktop app running
- **WHEN** the person cancels the presence check, it fails, or nobody answers before `--timeout`
- **THEN** the command exits 11 saying it was not confirmed, and the approval is still pending

#### Scenario: a moved target or a replayed grant approves nothing
- **GIVEN** a pending approval whose destination is changed after the request is made and before the person answers
- **WHEN** the shell prompts, and a grant pinned to the old fingerprint is sent, and a valid grant is sent twice
- **THEN** the shell refuses the moved target, the daemon answers `APPROVAL_TARGET_CHANGED` to the stale grant, and the second use of a grant is refused as `PRESENCE_GRANT_INVALID`, with nothing approved but the one valid request

#### Scenario: the desktop app is started, or the command says it is unavailable
- **GIVEN** a pending approval and no desktop shell polling the daemon
- **WHEN** `coffer approval approve <id>` runs where the app can be started, and again where it cannot
- **THEN** the first starts the app and proceeds to its prompt, and the second exits 12 with `CLI_APP_UNAVAILABLE` and the approval pending

#### Scenario: no flag skips the presence check
- **GIVEN** a pending approval
- **WHEN** `coffer approval approve <id> --yes` or `--force` is run
- **THEN** the command refuses the unknown option, exits 2, and no prompt is shown and nothing is approved

#### Scenario: several approvals cover exactly the ones named and still waiting
- **GIVEN** three pending approvals
- **WHEN** two of them are approved in one command, and then one already approved is named beside the third
- **THEN** exactly the two named are approved, and the second command is refused before any prompt because one named approval is no longer waiting, leaving the third pending

## MODIFIED Requirements

### Requirement: Report a pending approval on the command line by exiting
A command whose change leaves a secret waiting for a person MUST say so on standard error — the
approval ids and the command that approves them, `coffer approval approve <id>…` — and exit `9`,
which an agent reads as "the change is saved, ask the person to approve, do not retry": a
registration that cites a secret from a new destination answers `SECRET_BINDING_PENDING`, and with
`--json` the same is printed as `{"status": "pending_approval", "approval_ids", "next"}`. Storing a value with `coffer
secret set` waits for nobody, so it has no `--wait` and never exits `9`. Approvals are listed on the
Secrets page, by `GET /api/v1/secrets/approvals` and by `coffer approval list`; refused with the
Reject button, `POST .../reject` or `coffer approval reject`; and approved only after the person's
presence check in the desktop app, which `coffer approval approve` asks for ("Approve from the
command line with the person's own presence check").

#### Scenario: a command whose change leaves a binding waiting exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** a command registers a second server citing it and the daemon answers `SECRET_BINDING_PENDING`
- **THEN** the command prints the daemon's message, the approval id and `coffer approval approve <id>`, and exits `9`

#### Scenario: storing a replacement value with the command line waits for nobody
- **GIVEN** a secret sent to an MCP server, and a provider connection's key stored under a ref
- **WHEN** the user stores a new value for each ref with `coffer secret set`
- **THEN** each command prints `stored: <ref>` and exits `0`, the store holds the new value, and no approval waits
