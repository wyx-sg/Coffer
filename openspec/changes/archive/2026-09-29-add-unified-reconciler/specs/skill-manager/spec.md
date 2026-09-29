## RENAMED Requirements

- FROM: `### Requirement: Reconcile deliveries per agent on every trigger`
- TO: `### Requirement: Reconcile deliveries from state on every pass`

- FROM: `### Requirement: Heal safely repairable drift at daemon boot`
- TO: `### Requirement: Heal safely repairable drift on every pass`

## MODIFIED Requirements

### Requirement: Reconcile deliveries from state on every pass
The system MUST keep every agent's delivered set equal to the predicate of "Deliver a skill only where it is enabled and in scope" alone, as the skill-link target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"). An agent's wanted set is `{s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}` for an enabled agent and empty for a disabled one — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. Each wanted delivery is a link at `<agent skill dir>/<skill name>` pointing at the skill's master folder, judged by both paths: a wanted skill the agent does not hold is delivered, a held copy no longer wanted is reclaimed, and a held link whose path no longer matches the agent's skill directory (its `config_dir` moved) is re-delivered at the new path and removed from the old one. Because the reconciler runs on every pass, this holds whatever changed the state — a skill enabled, disabled, rescoped, imported or removed, an agent registered, enabled, disabled or moved, a sync import, or nothing Coffer heard about — and a user's own write runs the pass for skills at once, so the change is visible when the write answers. A disabled agent's copies are reclaimed and restored when it is enabled again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill whose scope names only the `claude_code` agent's uid,
- **THEN** the pass that follows delivers it to `claude_code` only, and `codex` receives nothing.

#### Scenario: moving an agent's config directory moves its deliveries
- **GIVEN** an agent holding a delivered skill, whose `config_dir` is then changed to another existing directory
- **WHEN** the change is saved
- **THEN** the skill is linked under the new directory's skills folder, the link under the old one is gone, and the move is recorded as a relink in the audit log

### Requirement: Heal safely repairable drift on every pass
The system MUST remediate the drift kinds "Repair repairable drift from master" designates safely repairable — a missing link and a tampered link — on every reconcile pass, without waiting for a person to act: at daemon start, on the reconciler's period and whenever a pass is brought forward, so drift that accumulated while the daemon was down, or between any two events, is found on the next pass. Drift kinds that repair does not consider safely repairable — a foreign directory at a link path, a missing master, an orphan master folder — MUST never be auto-remediated and stay reported: in the reconciler's plan (`GET /api/v1/reconcile/plan`), in the attention list and in the log, each with skill, agent, drift kind, on-disk path and a reason, for manual action.

#### Scenario: skill drift self-heals at daemon boot
- **GIVEN** an agent's delivered skill link is missing (deleted) or tampered (repointed elsewhere), whether while the daemon was not running or while it was
- **WHEN** the next reconcile pass runs — at daemon start or on its period
- **THEN** the link is re-created pointing to master exactly as the opt-in repair would do it, a tampered one backed up first, and the repair is recorded in the audit log with actor `system`

#### Scenario: boot heal leaves unsafe drift for a human to find
- **GIVEN** a foreign regular directory occupies a delivered skill's link path, or a binding's master folder no longer exists
- **WHEN** a reconcile pass runs
- **THEN** neither is touched — the foreign content and the missing master are left exactly as found — and each is reported as blocked with skill, agent, drift kind, path and reason

#### Scenario: a boot heal failure never blocks startup
- **GIVEN** the skill-link target raises while reading its state (e.g. a filesystem it cannot read)
- **WHEN** the daemon starts
- **THEN** the failure is reported and logged, the other targets are still reconciled, and the daemon still comes up

### Requirement: Repair repairable drift from master
The system MUST provide a drift repair that re-delivers repairable drift — missing link and tampered link — from the master library, and MUST NOT modify foreign/user content (replaced-with-regular), a missing master, or an orphan master; those are left intact and reported as requiring manual action. This repair runs (a) automatically per "Heal safely repairable drift on every pass", audited with actor `system`, and never allowed to fail startup; and (b) on demand via the CLI (`coffer skill verify --fix`, or `coffer drift repair`) and REST (`POST /skills/repair`, or `POST /api/v1/reconcile/apply`) for anyone who wants to trigger or inspect a repair directly, audited with the caller as actor. Each repair, automatic or on-demand, MUST be audited.

#### Scenario: opt-in repair re-delivers repairable drift from master
- **GIVEN** an agent skill directory where one enabled binding has a missing Coffer link, another has a tampered Coffer link (a stale link pointing elsewhere), a third binding's path is occupied by a foreign regular directory the user owns, and a fourth binding's master folder no longer exists,
- **WHEN** the user runs the opt-in repair (`coffer skill verify --fix` / `POST /skills/repair`),
- **THEN** the missing link is re-created pointing to master, the tampered link is backed up to `<path>.coffer-backup-<ts>` and then re-created pointing to master, the foreign regular directory is left completely untouched and still appears in the report as requiring manual action, the missing-master entry is left and reported as requiring manual action, and each re-delivery is recorded as a repair event in the audit log.
