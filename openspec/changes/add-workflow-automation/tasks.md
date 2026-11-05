## 0. Decisions before code (owner review)

- [ ] 0.1 Approve the principle amendment in design §7; then edit `docs-site/architecture/principles.md` and `docs-site/zh/architecture/principles.md`
- [ ] 0.2 Approve the new capability spec `automation` (AGENTS.md §4: adding a spec pauses for the owner)
- [ ] 0.3 Decide where the developer follow-up flow lives (design §8.1)
- [ ] 0.4 Accept ADR `automation-runs-flows-skills-define` (status Proposed → Accepted)

## 1. Runtime core (no workflow yet)

- [ ] 1.1 Move `domain/channel/schedule.py`, `scheduled_task.py`, `scheduled_run.py` to `domain/automation/`; move `scheduler.py`, `runner.py`, `kind.py` to `application/automation/`; chat delivery becomes a port the channel package implements; add the import-linter contract
- [ ] 1.2 Target `chat | workspace`; workspace runs through `TurnOrchestrator.enqueue_message` with a run-recorder sink and `ChatService.create_conversation(channel_uid=None)`
- [ ] 1.3 Schedule `timezone` (zoneinfo) in `next_slot` and `grace_for`; default stays machine-local
- [ ] 1.4 Migration: unique `(task_uid, due_at)` for scheduled triggers; new columns `stage`, `items`, `precheck_decision`, `usage_status`, `idempotency_key`; new outcomes
- [ ] 1.5 Slot claim through the row insert; Run now idempotency key on REST and `coffer task run --idempotency-key`
- [ ] 1.6 `deferred` vs started detection on the first adapter event; stage wall-clock timeout; `close_interrupted` by `may_write`
- [ ] 1.7 `automation_model_calls` from `TurnDone` and proxy records; `unknown` when neither reports
- [ ] 1.8 Delivery policy: workspace result local; optional notify to a paired chat by outcome
- [ ] 1.9 Tests: acceptance(automation, "a workspace task needs no chat"), ("an unknown timezone is refused"), ("a task in another timezone runs at that zone's time"), ("a slot reached twice opens one run"), ("a repeated Run now returns the same run"), ("an agent that is not installed defers the run"), ("usage the agent does not report is unknown"), ("a workspace run posts nothing by default"), ("a listed outcome notifies the named chat"); move the existing scheduled-task markers from `channels` to `automation`

## 2. Workflow contract

- [ ] 2.1 Read `automation.yaml` (skill-manager read model, never scanning); validate params; workflow id from the project manifest
- [ ] 2.2 Precheck and reconcile through the controlled command entry (argv, skill folder, `requires:`, per-secret grants), JSON in/out, schema-validated, timeout
- [ ] 2.3 Policy: windows, calendar file (verified years, fail closed), skip / next-working; checks at slot, precheck, stage start and action begin
- [ ] 2.4 `automation_work_items` with leases (`acquired / busy / reconcile`), version dedup, recheck booking
- [ ] 2.5 `automation_actions` and the tools `coffer__automation_action_begin` / `_end`; reconcile by command or by owner with evidence; audit
- [ ] 2.6 `coffer__automation_report`, result validation, checkpoint writer (atomic, generation, writer), milestones
- [ ] 2.7 Per-stage executors; session continuation only within one agent kind and one item
- [ ] 2.8 Unattended permission mode: Claude Code (`dontAsk` with the user's settings sources) and Codex (user profile, `approvalPolicy: never`, sandbox ≤ `workspace-write`); `needs_approval` outcome; refuse an adapter without such a mode
- [ ] 2.9 Generic fixture flow `sample-counter` (local tracker, local outbox) in `backend/tests/fixtures/`
- [ ] 2.10 Tests: acceptance(automation, "no change starts no model"), ("a failing precheck defers the run"), ("two tasks on one project never own one item"), ("an expired lease over an unknown write is not taken over"), ("a writing stage cut by a daemon stop is unknown"), ("an unknown action is refused after an agent switch"), ("reconcile with evidence releases the item"), ("a report revision is sent once"), ("a hand-over between agents carries the checkpoint, not the session"), ("a merged artefact does not complete the item"), ("a tool that needs approval ends the stage"), ("a slot on a public holiday is skipped"), ("a weekly slot on a holiday moves to the next working day"), ("a write after the window closes is refused"), ("an uncovered calendar year defers the run"), ("a task binds a declared flow"), ("a skill without a contract cannot be bound"), ("an unknown action is resolved from the command line")
- [ ] 2.11 Tests: acceptance(channels, "a repeating task that keeps failing is paused") updated for `deferred`

## 3. Surfaces, contract, docs, canvas

- [ ] 3.1 REST: task fields; `/scheduled-tasks/{uid}/items`, `/actions`, `/actions/{key}/reconcile`, `/precheck` (dry); `make contracts`
- [ ] 3.2 CLI: `coffer task items|actions|reconcile|precheck`; registry entries; `scripts/cli_coverage.py --check`
- [ ] 3.3 Web UI: task dialog (target, workflow, policy, executors), run detail (stages, usage, actions), work items; move the page requirement into `automation`
- [ ] 3.4 `experimental-features` delta: the `scheduled_tasks` switch also withdraws the three automation tools and closes the new routes
- [ ] 3.5 `openspec/specs/automation/data-model.md`, `contracts/`; `channels/data-model.md` trimmed
- [ ] 3.6 Docs (en, zh): scheduled-tasks guide, new workflow-automation guide, architecture daemon/chat pages, CLI reference
- [ ] 3.7 ADR accepted; research note links
- [ ] 3.8 Run canvas boards redrawn (task dialog, run detail, work items)

## 4. Real-run verification (receipts outside the repo)

- [ ] 4.1 R1 `sample-counter` on Claude Code, real model
- [ ] 4.2 R2 `sample-counter` on Codex, real model
- [ ] 4.3 R3 cross-agent hand-over both directions
- [ ] 4.4 R4 daemon killed mid execute; reconcile
- [ ] 4.5 R5 real clock, Asia/Singapore task on a machine in another zone, out-of-window slot

## 5. Developer follow-up migration (personal workflow project; no personal data in this repo)

- [ ] 5.1 M0 freeze and runtime-owner marker
- [ ] 5.2 M1 flow skill with `automation.yaml`; prototype flow-level tests pass
- [ ] 5.3 M2 state import (in-flight actions → `unknown`)
- [ ] 5.4 M3 shadow precheck, event keys match
- [ ] 5.5 M4 owner marker → `coffer`, old entry refuses
- [ ] 5.6 M5 dry run with writes off
- [ ] 5.7 M6 one ticket, owner-approved
- [ ] 5.8 M7 full allowlist for a week
- [ ] 5.9 M8 remove this workflow's Codex automations and hook entries

## 6. Weekly report (deferred)

- [ ] 6.1 Flow skill design: sources, cursors, periods, revisions, send action
- [ ] 6.2 Dry run producing a local report only; no send

## 7. Close

- [ ] 7.1 `make verify`
- [ ] 7.2 Archive the change in the same PR
