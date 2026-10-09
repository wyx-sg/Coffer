## MODIFIED Requirements

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor — the originating surface (CLI / API / UI), `system` for the
daemon's own work, `sync` for a change applied from the sync remote, `human` for an edit a person or an agent made to
a vault file on disk that Coffer found and committed, a named background worker
such as `system:memory-aggregate-worker`, or a domain actor a kind names itself, such as `user`,
`channel`, an agent's name, or `agent` for a knowledge write whose session reported no agent. Every lifecycle change made
through any surface — REST, CLI, or a kind's own command — MUST appear in the audit log
with the originating actor, and no surface can mutate a resource without one. Entries
MUST be readable through the REST route, the Activity page and `coffer log audit`, filterable by kind, resource, event type and
time, and MUST carry both the resource's stable identity and the label it carried at
that moment, so a trail survives a rename while each row keeps saying what the resource
was called then. Filtering one resource's history MUST key on that identity and not on
the label: a label cannot tell a renamed resource from a deleted one whose name was
later taken, and rendering two objects' histories as one is a worse answer than a short
one. The event-type vocabulary is shared: this spec defines the resource and retention
events and every kind contributes its own, so one record answers "what happened" for the
whole vault rather than each kind growing a private log.

An entry's `details` MUST say what changed, not only that something did: a value that
changed carries its value before and after (a name, a scope, a switch, a retention period,
a provider), an action over several things names them or counts them (the agents, files,
skills or pages it touched), and an action with a cause the caller knows names it. A text
edit to a vault file Coffer writes or commits — a knowledge page, a memory note, a skill
file — carries a unified diff of the edit, cut at 8 KB (UTF-8) with `diff_truncated: true`
and its size before the cut (`diff_bytes`). `details` MUST NOT hold a secret value: a
secret is named by its reference, and a resource's configuration passes its kind's
redactor first. Every audited event is also written to `daemon.log` as one `coffer.<event>`
line carrying the actor, the resource and the entry's `details`, cut at 2 KB with
`details_truncated: true`.

#### Scenario: audit lifecycle changes
- **GIVEN** the user performs any add / enable / disable / update / delete on a server or capability,
- **WHEN** they open the Activity page's audit tab or run `coffer log audit`,
- **THEN** they see one row per change with actor, timestamp, and a payload describing what changed.

#### Scenario: a rename and a knowledge edit say what changed
- **GIVEN** a skill renamed from `notes` to `journal`, and a knowledge page whose one line was edited
- **WHEN** the audit log is read
- **THEN** the rename's details carry `notes` before and `journal` after
- **AND** the edit's details carry a unified diff with the line removed and the line added

#### Scenario: the daemon log line carries the event's details
- **GIVEN** a retention period changed from 30 to 7 days
- **WHEN** `daemon.log` is read
- **THEN** its `coffer.retention_updated` line carries the actor, the table and both periods
