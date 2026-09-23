## ADDED Requirements

### Requirement: Pause a configured remote without forgetting it
A configured remote MUST carry an `enabled` switch, and switching it off MUST
pause sync without forgetting anything. While it is off every round MUST report
`disabled`, record nothing, commit and push nothing, and raise no attention on
any surface — `coffer sync status` exits zero, the web UI does not mark its sync
entry and the desktop shell marks nothing — even over a round the vault was
paused on, because a user who met a hold by switching sync off has answered it
too. The remote, the pointer and the history MUST all be kept, so switching it
back on resumes where the vault left off. Re-running `coffer sync remote set`
MUST keep a paused remote paused — it changes what it names and nothing else —
and a remote configured for the first time is stored enabled.

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

## MODIFIED Requirements

### Requirement: Say a vault needs a human where the user already is
A vault whose last round needs a human — held for confirmation, conflicted,
failed to push or run, or waiting to join (`awaiting_join`) — MUST say so where
the user already is, not only on the page built for it. `coffer sync status`
MUST exit non-zero, the web UI MUST mark its **navigation entry** for the sync
page, and the desktop shell MUST raise it as a notification and mark its icon. A
held vault converges no further, and neither does a machine that has not joined
its remote, so a hold nobody sees is an outage that looks like silence: the
first one in the field stood for four days.

The web UI's mark MUST be cleared by **visiting the page**, not by the situation
changing, and MUST NOT return for the same situation. The rounds are
timer-driven: one broken remote is a fresh round every hour, and a notice that
re-raised itself on each would cover every page in the app hourly with something
the user read the first time. A mark keyed on what is wrong — the outcome, the
error, the direction and areas a hold was raised over — asks once, and asks
again only when the answer would be different.

#### Scenario: a held vault says so where the user already is
- **GIVEN** a round held at the deletion guard, so nothing converges and
  nothing is backed up until someone answers it,
- **WHEN** the user is anywhere other than the sync page — at a terminal, on
  another page of the web UI, or with only the desktop shell in front of them,
- **THEN** `coffer sync status` exits non-zero, the web UI's navigation entry
  for sync is marked, and the shell has marked its icon and raised one
  notification — once for that condition, not once per poll,
- **AND** opening the sync page clears the web UI's mark, which does not
  return while the same thing is wrong, however many rounds re-raise it.

#### Scenario: a machine that has not joined says so everywhere
- **GIVEN** a machine with a remote configured that it has not joined, so its
  round reports `awaiting_join` and converges nothing
- **WHEN** the user is anywhere other than the sync page
- **THEN** `coffer sync status` exits non-zero and points at `coffer sync adopt`,
  the web UI's navigation entry for sync is marked, and the desktop shell marks
  its icon and raises one notification
