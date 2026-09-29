## RENAMED Requirements

- FROM: `### Requirement: Clear an active flag the agent's config contradicts at boot`
- TO: `### Requirement: Clear an active flag the agent's config contradicts`

## MODIFIED Requirements

### Requirement: Clear an active flag the agent's config contradicts
On every reconcile pass ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), the provider-projection target MUST compare, for each enabled agent an active connection reaches, the keys Coffer's projection would write — base URL, model keys, the key helper command, Codex's provider block and its model catalogue — with the keys the agent's native config carries, by value and not by presence. Where Coffer's keys are present but differ, the connection MUST be projected again. Where they are absent and no agent of that type carries them, the system MUST clear `is_active`, so every surface then says the agent is on its built-in login, and MUST NOT write the projection back, because a flag left from an earlier session is no warrant to re-route a user's agent through a gateway they are not currently using; the exceptions are a pass run for a sync import, which carries the user's explicit switch from another machine, and an item a person applies, both of which project. Where they are absent from one agent of a type while another agent of that type carries them, that agent MUST be projected too. For Codex, the `shell_environment_policy.exclude` entry alone does not count as carrying the projection: it selects no provider. The opposite drift — Coffer's keys present while no active connection reaches the agent — MUST be reported rather than removed, unless the pass runs for a sync import or a person applies
that item. A multi-step switch MUST keep reconcile passes out until its writes and its flags agree. `is_active` is not redundant with `enabled`: `enabled` is the user's switch on the resource, while `is_active` records that this is the connection currently written into the agents it reaches — a claim about a file on disk that the agent's own CLI, other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears an active flag the agent's config does not carry
- **GIVEN** an active connection reaching a registered Claude Code agent whose `settings.json` carries none of Coffer's keys
- **WHEN** a reconcile pass runs at daemon start or on its period
- **THEN** the connection's `is_active` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

#### Scenario: a leftover shell exclude entry is not a Codex projection
- **GIVEN** an active connection reaching a registered Codex agent whose `config.toml` holds only `[shell_environment_policy]` with `exclude = ["COFFER_PROVIDER_KEY"]`
- **WHEN** a reconcile pass runs
- **THEN** the connection's `is_active` is cleared

#### Scenario: a projection whose values went stale is projected again
- **GIVEN** an active connection projected into a Claude Code agent, whose `settings.json` then carries another base URL or another key helper command than the connection's
- **WHEN** a reconcile pass runs
- **THEN** the pass reports a modification naming the changed keys and writes the connection's projection again, recorded in the audit log with actor `system`

#### Scenario: keys no active connection claims are reported, not removed
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's keys while no connection is active for it
- **WHEN** a reconcile pass runs on its period
- **THEN** the drift is reported and the file is left as it was
- **AND** when the user applies that item, Coffer's keys are removed

### Requirement: Converge connections across machines
The `provider` kind MUST be registered into the composition root's kind table so the sync exporter
and the resource applier carry it automatically ([vault-sync](../vault-sync/spec.md)): the exporter
writes each row to `resources/provider/<uid>.yaml`, git three-way-merges the tree against the remote,
and the applier puts the resulting difference back one document at a time. An incoming document MUST
NOT change the local row's reach (`enabled` / `scope`), which is one decision the user makes per
machine: a row that already exists keeps the reach it has, and a row that has just arrived takes the
kind's own default. Credentials travel as Fernet ciphertext at `credentials/<ref>.enc`, only when the
remote is configured to carry them; the master key never enters the repository, and no raw key MUST
appear in the sync tree's plaintext.

Projection is a machine-local side effect, so after a round applies, the reconcile pass it runs
with the import's warrant MUST re-derive every agent's projection from the converged rows: for each
agent type with a registered agent, the active connection whose scope reaches it is projected, and a
type with no active connection is de-projected — the import carries the user's switch either way.

#### Scenario: a provider profile round-trips through sync export and import
- **GIVEN** a connection with a credential ref exists on one machine,
- **WHEN** a converge round runs — the exporter writes the connection into the tree and the resource **applier** puts that document into the second machine's vault,
- **THEN** the row lands there with identical `config` fields, the credential ciphertext is present at `credentials/<ref>.enc`, and no secret appears anywhere in the tree's plaintext. A later edit converges the same way, so the second machine ends up with the edited config and description.

#### Scenario: an import projects a switch made on another machine
- **GIVEN** a connection activated on another machine, whose row arrives here with `is_active` set while this machine's agent carries none of Coffer's keys
- **WHEN** the round's reconcile pass runs
- **THEN** the connection is projected into the agent rather than its flag being cleared
