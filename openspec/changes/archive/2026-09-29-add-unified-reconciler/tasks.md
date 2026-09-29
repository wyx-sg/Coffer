## 1. Core

- [x] 1.1 Pure vocabulary and diff (`domain/reconcile.py`): items with full parameters, differences, decisions, triggers, outcomes, the `Changed` hint
- [x] 1.2 Target protocol, `Applied` / `AuditEvent` / undo (`application/reconcile/ports.py`)
- [x] 1.3 The reconciler: registry, writing pass, dry-run, manual apply, hints with settle, period loop, hold, re-entrancy, first-seen bookkeeping, per-pass budget log
- [x] 1.4 Audit after the write in the same call; undo on audit failure
- [x] 1.5 `resources.rev` (migration 0107) and the hinting resource repository
- [x] 1.6 Composition: built before the kinds, boot pass before ready, periodic loop started and cancelled first at shutdown, one sync post-import hook with the import warrant, the round's apply held

## 2. Targets (one per projection-registry asset) and what they replace

- [x] 2.1 MCP entry (`mcp_entry`): shim path and `--agent-uid` compared; stale entry repaired; misplaced entry moved install-first; missing launcher blocked. Removes the one-off home-file migration
- [x] 2.2 Skill links (`skill_link`): delivered set and link health from state; reclaim, relink on a moved config dir, foreign content and missing master blocked, orphan masters reported. Removes the per-agent delivery reconcile, the verify/repair walk, the skill boot heal, the relink and auto-bind paths and the agent post-import side effects; `skill verify` / `repair` read the plan
- [x] 2.3 Provider projection (`provider_projection`): owned keys compared by value; stale projection re-projected; contradicted flag cleared; import and manual warrants project and de-project; switch held. Removes the provider boot heal and the provider post-import reconcile
- [x] 2.4 Delivery hook (`delivery_hook`): command compared; stale repaired; withdrawn with memory off; installed on the switch or on request only. Removes the memory boot heal and the switch's own reconcile

## 3. Read models

- [x] 3.1 `GET /api/v1/reconcile/plan`, `POST /api/v1/reconcile/apply` and their contract
- [x] 3.2 `GET /api/v1/attention` over the reconciler-drift source and one source per kind (MCP health / launcher / secret, agent program / connection, sync conflict / held deletions, channel state); feature-filtered, failures isolated
- [x] 3.3 `coffer drift list|repair`, `coffer attention`; parity table

## 4. Tests

- [x] 4.1 PR #413 reproduction (delivery hook) and the MCP-entry case (shim path, `--agent-uid`)
- [x] 4.2 Dry-run writes nothing under an isolated home (fingerprint before and after)
- [x] 4.3 Audit failure restores the file
- [x] 4.4 Per-target policy tests; hint, period, hold, re-entrancy
- [x] 4.5 Pass cost measured (`tests/integration/perf/test_reconcile_pass_cost.py`, benchmark tier)

## 5. Docs

- [x] 5.1 docs-site architecture page "The reconciler"; layering tree; index and sidebar
- [x] 5.2 `.agents/stack.md`; memory, daemon, providers and agents guide pages; ADR cross-references; data models
