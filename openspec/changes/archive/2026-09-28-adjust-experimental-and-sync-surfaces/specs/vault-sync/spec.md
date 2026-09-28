## REMOVED Requirements

### Requirement: Present a Sync page with Runs and Setup tabs
**Reason**: The machine registry moves back to a tab of its own.
**Migration**: See "Present a Sync page with Runs, Setup and Machines tabs".

## ADDED Requirements

### Requirement: Present a Sync page with Runs, Setup and Machines tabs
The web UI MUST present a top-level **Sync** page with **three** tabs. **Runs**,
the landing tab: every round this machine has run, as a table — when, outcome,
what it applied here, what it published, the commit. **Setup**: the remote and
the master key, which are one errand rather than two screens. **Machines**: the
machine registry, which a user comes back to — to rename this machine or retire
one that is gone — long after the remote and the key were set. There MUST be no
Status tab — what a vault is *doing* is the newest row of what it has *been*
doing, and a separate tab for it put one situation in two places and made it
actionable in only one.

#### Scenario: the Sync page opens on Runs beside Setup and Machines
- **GIVEN** the web UI
- **WHEN** the user opens the Sync page
- **THEN** it has exactly three tabs, Runs, Setup and Machines, and opens on Runs
- **AND** a link to a tab that no longer exists lands on Runs

## MODIFIED Requirements

### Requirement: Keep point-in-time restore on the command line
Restoring at a point in time MUST stay a CLI operation and no page may offer it:
`--at` names a revision in the *remote's* history, which no route exposes, so a
page could only offer a blind date box with no preview of what would come
back.

#### Scenario: no page offers a point-in-time restore
- **GIVEN** the Sync page with a configured remote and a history of rounds
- **WHEN** the user looks through its Runs, Setup and Machines tabs
- **THEN** none of them offers a restore or a date to restore to
