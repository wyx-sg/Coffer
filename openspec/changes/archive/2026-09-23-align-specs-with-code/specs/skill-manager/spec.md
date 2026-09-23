## MODIFIED Requirements

### Requirement: Validate imported skill folders against AgentSkills
The system MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size at most 50 MB, a fixed cap. A folder that violates any of these MUST be rejected with `unprocessable_entity` (422) and nothing persisted. A folder over the size limit is rejected as `SKILL_INVALID` with `details.reason` `size_limit_exceeded`.

#### Scenario: reject import of an invalid skill folder
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder that is missing `SKILL.md` or has empty `name`/`description` frontmatter,
- **THEN** the request is rejected with a clear error, and nothing is written to `~/.coffer/skills/` or the database.

#### Scenario: reject import containing path-escape symlinks
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder containing a symlink that resolves outside the folder,
- **THEN** the request is rejected with the offending paths listed, and nothing is persisted.

#### Scenario: reject a skill with an over-long description
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder whose SKILL.md `description` exceeds 1024 characters,
- **THEN** the request is rejected as invalid frontmatter, and nothing is written to `~/.coffer/skills/` or the database.

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([ADR resource-identity-is-an-immutable-uid](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)); the CLI and web UI let the user pick agents by name and store their uids. A uid that matches no agent registered here is legal and simply never matches.
- `{"agents": []}` — nobody receives it, while the skill stays in the library, converged and visible.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, a converge round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What converges is the skill — its files, its metadata — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and dormant on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of "Track delivered copies as internal bookkeeping" nor any field on the agent resource; the agent resource carries no skill-delivery policy at all. `enabled` is a real switch: disabling a skill reclaims every delivered copy (master untouched) and re-enabling redelivers it to every agent its scope still grants. Scope is a hard grant: narrowing it to exclude an agent reclaims that delivery on the next reconcile even if the copy got there some other way, and widening it delivers; no per-agent state can hold a copy against the scope or keep one away from an agent the scope grants. A DISABLED AGENT is a separate matter and is never written into at all — the predicate names the agents a skill belongs to, while an agent the user switched off is one Coffer does not touch; its held copies are reclaimed and re-enabling it reconciles them back. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per "Reclaim a delivered copy without touching master", and MUST deliver a copy the predicate now grants but the agent does not hold. This predicate governs **delivery** — writing a skill into an agent's own filesystem — and is the only path by which a skill reaches an agent (see "Expose no skill tools over MCP").

#### Scenario: a skill with no scope reaches every registered agent
- **GIVEN** two registered agents and an enabled skill whose scope is unset (`None`),
- **WHEN** the delivery reconcile runs for each agent,
- **THEN** both agents hold a delivered copy, and registering a third agent delivers the skill there too with no further user action.

#### Scenario: a skill scoped to no agent reaches nobody
- **GIVEN** two registered agents each holding a delivered copy of an enabled skill,
- **WHEN** the user sets the skill's scope to `[]`,
- **THEN** both delivered copies are reclaimed, the skill remains in the library (still listed, still exported), and no agent receives it until its scope grants one again.

#### Scenario: disabling a skill reclaims every delivered copy
- **GIVEN** an enabled skill delivered to two agents,
- **WHEN** the user disables the skill resource,
- **THEN** both symlinks are removed and both delivery records are cleared, while the skill's scope and its master folder are unchanged.

#### Scenario: re-enabling a skill redelivers it
- **GIVEN** a disabled skill with no delivered copies and a scope granting two agents,
- **WHEN** the user re-enables the skill resource,
- **THEN** it is redelivered to both agents — links re-created, delivery records restored — with no per-agent action.

#### Scenario: scoping a skill away from an agent reclaims the delivered copy
- **GIVEN** an enabled skill currently delivered to an agent whose uid its scope includes,
- **WHEN** the user edits the skill's scope to exclude this agent and the next reconcile runs,
- **THEN** the delivered symlink is removed and the delivery record is cleared — scope is a hard grant, and no per-agent state can hold the copy against it.

### Requirement: Reconcile deliveries per agent on every trigger
The system MUST reconcile deliveries per agent from the predicate of "Deliver a skill only where it is enabled and in scope" alone. A reconcile computes the agent's wanted set as `{s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}` — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. It delivers every wanted skill the agent does not hold, and reclaims every held copy that is no longer wanted. It MUST run on: a skill being enabled or disabled, a skill's scope being edited, a skill being imported, a skill being removed, an agent being registered, an agent being enabled or disabled, an agent's `config_dir` changing, and the post-import hook after a sync import. A disabled agent's wanted set is empty, so the same reconcile reclaims its copies and restores them when it is enabled again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill whose scope names only the `claude_code` agent's uid,
- **THEN** the post-import reconcile delivers it to `claude_code` only, and `codex` receives nothing.
