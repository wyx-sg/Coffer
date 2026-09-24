## MODIFIED Requirements

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`, `rollback`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref]`,
`remote show`, `remote clear`, `machine list`, `machine rename <name>`,
`machine remove <id>`, `key export <file>`, `key import <file>`,
`key fingerprint`.

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with `--at`, `confirm`, `reject`, `rebuild` with `--yes` and `rollback`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials` and `--credential-ref`, `remote show`, `remote clear`, `machine list`, `machine rename`, `machine remove`, `key export`, `key import` and `key fingerprint`

### Requirement: Pause a configured remote without forgetting it
A configured remote MUST carry an `enabled` switch, and switching it off MUST
pause sync without forgetting anything. While it is off every round MUST report
`disabled`, record nothing, commit and push nothing, and raise no attention on
any surface — `coffer sync status` exits zero, the web UI does not mark its sync
entry and the desktop shell marks nothing — even over a round the vault was
paused on, because a user who met a hold by switching sync off has answered it
too. The remote, the pointer and the history MUST all be kept, so switching it
back on resumes where the vault left off. Re-running `coffer sync remote set`
MUST keep a paused remote paused — it changes what it names and nothing else:
every option it is not given keeps its stored value, including the branch, the
interval, whether credentials travel, the push credential and the working tree
— and a remote configured for the first time is stored enabled, with the
defaults for every option it is not given.

#### Scenario: a paused remote runs no round and asks for nothing
- **GIVEN** a joined vault whose last round is held at the deletion guard, and
  its remote then switched off
- **WHEN** a note is written and a round is requested
- **THEN** the round reports `disabled`, the history is exactly what it was, the
  note is not on the remote, and the pointer and the remote are kept
- **AND** `coffer sync status` exits zero, the web UI does not mark its sync
  entry and the desktop shell marks nothing

#### Scenario: reconfiguring a paused remote keeps it paused
- **GIVEN** a configured remote that has been switched off
- **WHEN** `coffer sync remote set` is run again with a different interval
- **THEN** the stored remote carries the new interval and is still switched off
- **AND** a remote set for the first time is stored switched on

#### Scenario: reconfiguring a remote changes only what it names
- **GIVEN** a configured remote with a non-default branch, interval, push
  credential and working tree, carrying credentials
- **WHEN** `coffer sync remote set` is run again naming only a new interval
- **THEN** the stored remote carries the new interval and every other setting
  exactly as it was
- **AND** running it with `--without-credentials` switches credential sync off
  and changes nothing else
