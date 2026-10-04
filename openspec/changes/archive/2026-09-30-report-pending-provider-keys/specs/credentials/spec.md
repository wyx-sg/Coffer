## MODIFIED Requirements

### Requirement: Answer a pending approval on the command line by waiting or exiting
A command that saves a change which then waits for approval — `coffer mcp add`,
every `coffer <kind> edit` (including `coffer provider edit` with `--secret` or
`--base-url`), `coffer channel add`, `coffer provider add`, `coffer sync remote
set`, `coffer credentials set` and `coffer config set secrets.require_approval
off` — MUST print `waiting for approval in the Coffer app` with what waits and
its approval id, and exit `9`; with `--wait` it MUST poll until the person
answers, exiting `0` once approved and non-zero once rejected. What a change to
a destination waits on includes a pending replacement of the value of a secret
that destination cites, not only a pending binding to it. `coffer credentials
approvals` MUST list what waits (`--all` includes decided ones, `--json` for
scripts) and `coffer credentials reject <id>` MUST refuse one; no command
approves.

#### Scenario: the command line reports a pending approval and exits 9
- **GIVEN** a secret already sent to one MCP server
- **WHEN** the user registers another server citing it with `coffer mcp add`
- **THEN** the server is registered, the command prints "waiting for approval in the Coffer app" naming the approval, and exits `9`
- **AND** `coffer credentials approvals` lists that approval

#### Scenario: the command line waits for the approval with --wait
- **GIVEN** a command run with `--wait` whose change waits for approval
- **WHEN** the approval is applied in the desktop app
- **THEN** the command reports it approved and exits `0`

#### Scenario: the command line reports a pending provider key and exits 9
- **GIVEN** a provider connection whose key is in use
- **WHEN** the user runs `coffer provider edit` with a new `--secret`, then with a new `--base-url`, and then `coffer provider add` for a second connection citing the same key with `--credential-ref`
- **THEN** each change is saved, and each command prints "waiting for approval in the Coffer app" naming its approval and exits `9`, while the stored key keeps its old value
- **AND** a `coffer provider edit` that changes only the description exits `0`
