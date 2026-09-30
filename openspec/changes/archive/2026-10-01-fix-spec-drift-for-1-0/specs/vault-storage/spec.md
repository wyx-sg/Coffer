## ADDED Requirements

### Requirement: List recent vault changes and the hand edits kept out
The vault's recent commits SHALL be readable newest first, across the whole
vault or under one path prefix, each with its writer, time, summary and the
paths it changed, a page at a time (`GET /api/v1/vault/changes`; on the CLI one
folder's commits are `coffer vault history <folder>/`). The hand edits the
vault refused (see "Keep the last valid version when a hand edit is invalid")
SHALL be listed with the path, the finding's code, severity and message — on
REST as `GET /api/v1/vault/problems` and on the CLI as `coffer vault problems`
(`--json` for scripts), which says so when there are none.

#### Scenario: recent changes list the vault's commits newest first
- **GIVEN** one commit under `knowledge/` and a later one under `skills/`
- **WHEN** the recent changes are read under the prefix `knowledge`, and then for the whole vault two at a time
- **THEN** the first lists only the knowledge commit with the path it changed
- **AND** the second lists two commits and a cursor to the older ones

#### Scenario: refused hand edits are listed on REST and the command line
- **GIVEN** a resource file hand-edited into something that does not parse
- **WHEN** `GET /api/v1/vault/problems` is read
- **THEN** it names the file with the code `invalid_document` and severity `error`
- **AND** with nothing refused, `coffer vault problems` says there are no problems and `--json` prints an empty list

### Requirement: Refuse to start on a git older than 2.40
The vault's history and every sync round run on the machine's own `git`, and a
round's merge (`merge-tree --write-tree --merge-base`) needs git 2.40. The
daemon MUST check the version before it opens the vault and MUST refuse to
start on an older one, saying which version it found and which it needs. How
git is updated depends on the machine, so the refusal MUST name no installer or
package manager: it carries a prompt the person can give their agent to update
git, as a missing git's refusal does.

#### Scenario: a git older than 2.40 stops the daemon with a hand-off
- **GIVEN** a machine whose `git` reports version 2.30
- **WHEN** the daemon opens the vault
- **THEN** it refuses to start, naming 2.30 and 2.40
- **AND** the refusal carries a prompt asking an agent to update git and confirm with `git --version`, and names no installer
