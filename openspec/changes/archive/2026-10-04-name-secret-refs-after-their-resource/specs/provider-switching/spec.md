## RENAMED Requirements

- FROM: `### Requirement: Rename a connection without moving anything else`
- TO: `### Requirement: Rename a connection without moving anything but its own secret`

## MODIFIED Requirements

### Requirement: Rename a connection without moving anything but its own secret
A connection MUST be renamable through the framework's own kind-agnostic route — the `name` field on
`PATCH /api/v1/resources/{uid}` — and from the connection's edit dialog, which calls that
route; this kind MUST NOT serve a rename route of its own. The
operation MUST change the label and nothing else the label names: the resource keeps its `uid`, a
`secret_ref` the connection owns moves to the ref named for the new name (`provider/<new name>/key`,
spec [secret](../secret/spec.md) "Name a resource's secret after the resource and its slot") with
the secret readable there and nothing left at the old ref, a shared ref stays where it is, the
`audit_log` rows MUST NOT be repointed — they follow the resource by uid and go on spelling the name
each event carried when it happened — and a connection an agent runs on MUST NOT be re-projected, because the
projected `apiKeyHelper` cites the agent's uid. Codex's provider label (`Coffer (<name>)`) is cosmetic and
goes stale until the next projection rewrites it. It MUST record a `resource_renamed` audit event
naming both names. A name another connection already holds MUST be refused with
`RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent connection MUST be a 404;
renaming to the current name MUST be a no-op and MUST record nothing. The optional display title
every resource carries ([resource-framework](../resource-framework/spec.md), set
through the same `PATCH /api/v1/resources/{uid}`) is not a rename and leaves the name alone. On the web, the edit dialog's
Name field submits this rename ahead of the patch, and the page stays where it is, because its route
is the uid.

#### Scenario: rename a connection and keep its secret, audit trail and projection
- **GIVEN** a connection `acme` with an inline secret, which a registered Claude Code agent runs on,
- **WHEN** `PATCH /api/v1/resources/<uid> {"name": "acme-eu"}` is called,
- **THEN** the connection keeps the same `uid` and answers there under the label `acme-eu`, its `secret_ref` is `provider/acme-eu/key` with the secret readable there and nothing at `provider/acme/key`, the agent's projected `apiKeyHelper` is byte-for-byte what it was (it names the uid), and the whole history — including the rows recorded before the rename, which still spell the old name — comes back when querying the audit log by uid.
#### Scenario: reject a rename onto a name another connection already uses
- **GIVEN** two connections `acme` and `taken`,
- **WHEN** `acme` is renamed to `taken`,
- **THEN** the response is 409 `RESOURCE_ALREADY_EXISTS` and both connections still carry their original labels, each still reachable at its own uid with its secret intact.
#### Scenario: rename a connection over REST
- **GIVEN** the daemon is running with a connection `acme`,
- **WHEN** a client patches the connection's `name` to `acme-eu` through `PATCH /api/v1/resources/<uid>`, and then patches it to `taken` while another connection is named `taken`,
- **THEN** the first answers under the label `acme-eu` at the same `uid` and records a `resource_renamed` entry naming both names,
- **AND** the second is refused with 409 `RESOURCE_ALREADY_EXISTS`, and the connection is still `acme-eu`.
