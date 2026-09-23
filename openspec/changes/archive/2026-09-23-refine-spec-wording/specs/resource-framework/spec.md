## MODIFIED Requirements

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor — the originating surface (CLI / API / UI), `system` for the
daemon's own work, `sync` for a change applied from the sync remote, a named background worker
such as `system:memory-aggregate-worker`, or a domain actor a kind names itself, such as `user`,
`channel`, an agent's name, or `agent` for a knowledge write whose session reported no agent. Every lifecycle change made
through any surface — REST, CLI, or a kind's own command — MUST appear in the audit log
with the originating actor, and no surface can mutate a resource without one. Entries
MUST be readable through both surfaces, filterable by kind, resource, event type and
time, and MUST carry both the resource's stable identity and the label it carried at
that moment, so a trail survives a rename while each row keeps saying what the resource
was called then. Filtering one resource's history MUST key on that identity and not on
the label: a label cannot tell a renamed resource from a deleted one whose name was
later taken, and rendering two objects' histories as one is a worse answer than a short
one. The event-type vocabulary is shared: this spec defines the resource and retention
events and every kind contributes its own, so one record answers "what happened" for the
whole vault rather than each kind growing a private log.

#### Scenario: audit lifecycle changes
- **GIVEN** the user performs any add / enable / disable / update / delete on a server or capability,
- **WHEN** they open the audit view (CLI or UI),
- **THEN** they see one row per change with actor, timestamp, and a payload describing what changed.
