## MODIFIED Requirements

### Requirement: Audit every lifecycle change
The system MUST record an audit entry for every lifecycle change to any resource or
capability, including the actor — the originating surface (CLI / API / UI), `system`, or a
domain actor a kind names itself, such as `user`, `channel` or an agent's name. Every lifecycle change made
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

### Requirement: Reach every management operation from both REST and the CLI
Users MUST be able to perform every management operation through both (a) a REST API and
(b) a `coffer` command-line interface, sharing the same underlying daemon and a
consistent error model; the reviewed CLI command tree and the management API MUST stay in
step in both directions, so neither can gain an operation the other lacks without the
parity test failing. The rule is policy over every spec and is stated as such in
[`.agents/openspec.md`](../../../.agents/openspec.md); this requirement is where it becomes
testable, because the assertion runs over the entire command tree across every spec and
so has no narrower home. A spec that cannot honour it records the gap in its own
`## Purpose` rather than leaving the omission to be discovered.

#### Scenario: command line covers every visual operation
- **GIVEN** the daemon is running,
- **WHEN** the CLI's live command tree is read,
- **THEN** it is **exactly** the reviewed table of every group the composition root registers and every subcommand under each — `daemon`, `open`, `resource`, `scope`, `audit`, `retention`, `mcp`, `credentials`, `agent`, `channel`, `skill`, `knowledge`, `memory`, `provider`, `engine`, `sync`, with their nested groups — asserted in both directions, so a UI operation cannot ship a CLI counterpart without a reviewer seeing it here and a CLI command cannot appear without someone deciding it belongs,
- **AND** the groups whose surface is options rather than subcommands are claimed by those options instead, since an empty subcommand set would assert nothing about them,
- **AND** every group's `--help` renders, so an import-time error in one command module cannot wait for a user to reach for it,
- **AND** machine-readable JSON output is available for scripting.

#### Scenario: command line surfaces same errors
- **GIVEN** any failure surfaced by the management API,
- **WHEN** triggered through the command line,
- **THEN** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.
