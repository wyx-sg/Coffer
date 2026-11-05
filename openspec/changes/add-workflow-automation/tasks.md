## 0. Decisions before code (owner review)

- [x] 0.1 Approve the principle amendment in design §7 (owner, 2026-11-05); edit `docs-site/architecture/principles.md` and `docs-site/zh/architecture/principles.md`
- [x] 0.2 Approve the new capability spec `automation` (AGENTS.md §4: adding a spec pauses for the owner)
- [x] 0.3 Decide where the developer follow-up flow lives (design §8.1): its own flow skill (owner, 2026-11-05)
- [x] 0.4 Accept ADR `automation-runs-flows-skills-define` (status Proposed → Accepted)

## 1. Runtime core (no workflow yet)

- [ ] 1.1 Move `domain/channel/schedule.py`, `scheduled_task.py`, `scheduled_run.py` to `domain/automation/`; move `scheduler.py`, `runner.py`, `kind.py` to `application/automation/`; chat delivery becomes `ChatDeliveryPort`, implemented by the channel package; import-linter contracts as design §6 lists (automation's allowed ports, `automation → channel` forbidden, `channel → automation` domain + ports only, automation added to every other kind's forbidden list)
- [ ] 1.2 Target `chat | workspace`; workspace runs through `TurnOrchestrator.enqueue_message` with a run-recorder sink and `ChatService.create_conversation(channel_uid=None)`
- [ ] 1.3 Schedule `timezone` (zoneinfo) in `next_slot` and `grace_for`; default stays machine-local; a nonexistent local time runs once at the first valid time after it
- [ ] 1.4 Migration on `scheduled_task_runs`: relabel duplicate `(task_uid, due_at)` schedule rows `schedule_duplicate`, then a partial unique index on `(task_uid, due_at)` for `trigger IN (schedule, moved)`; new columns `stage`, `stage_started_at`, `stage_may_write`, `moved_to`, `items` (with lease generation), `precheck_decision`, `usage_status`, `idempotency_key`; new outcomes incl. `moved`; triggers `moved`, `recheck`; new table `automation_rechecks(workflow_id, item_key, due_at, task_uid)` unique on the first three
- [ ] 1.5 Slot claim through the row insert; Run now idempotency key on REST and `coffer task run --idempotency-key`; `latest_slot` counts `schedule` rows only; scheduler scans `automation_rechecks`
- [ ] 1.6 Adapters record `stage_started_at` and `stage_may_write` (true for a chat target) durably once the session is connected and the prompt accepted (Claude Code after `_connect` and the send; Codex after the app-server session and `turn/start`), not at `TurnStarted`; `deferred` before it; stage wall-clock timeout; `close_interrupted` reads both columns (`unknown` for a writing or chat-target run, else `failed`)
- [ ] 1.7 `automation_model_calls` from `TurnDone` (new optional `cost`, filled from Claude Code `ResultMessage.total_cost_usd`) and from proxy records carrying the turn's correlation header (turn token → run, stage) read through usage's port; `unknown` when neither reports
- [ ] 1.8 Delivery policy: workspace result local; optional notify to a paired chat by outcome
- [ ] 1.9 Pause rule in `automation`: three `failed` / `unknown` / non-policy `deferred` with one reason; policy deferrals neither count nor reset; calendar not covered raises an attention item; the channel only tells the chat
- [ ] 1.10 Move the existing markers from `channels` to `automation` (scenario names unchanged): "a task in a paired chat is created", "a task in a chat the channel never paired is refused", "a schedule closer than 15 minutes is refused", "a daily task runs at its time", "a one-off follow-up is removed after it runs", "a slot whose previous run is still going is skipped", "a daily task missed this morning runs late, once", "a follow-up missed past its grace is skipped", "a week of missed daily slots runs once", "a run's history row says how it ended", "a run's conversation opens from its history"
- [ ] 1.11 Rename the marker on `test_a_run_left_open_is_closed_on_start` (`backend/tests/integration/channel/test_scheduled_tasks.py`) from channels "a run interrupted by a stop is closed on the next start" to automation "a writing run interrupted by a stop is closed unknown on the next start", and change its assertion from `failed` to `unknown`
- [ ] 1.12 Tests, acceptance(automation, …): "a workspace task needs no chat", "an unknown timezone is refused", "a task in another timezone runs at that zone's time", "a time skipped by daylight saving runs once at the next valid time", "a slot reached twice opens one run", "a repeated Run now returns the same run", "an agent that is not installed defers the run", "an agent that fails to connect defers the run", "usage the agent does not report is unknown", "a workspace run posts nothing by default", "a listed outcome notifies the named chat", "a workspace task that keeps failing is paused", "policy deferrals never pause a task"
- [ ] 1.13 Tests, acceptance(channels, …): "a repeating task that keeps failing is paused" updated for `deferred` and the automation pause rule; "a follow-up answers in its thread and mentions the asker" and "a fresh task opens a new conversation on its own agent" re-run unchanged

## 2. Workflow contract

- [ ] 2.1 Read `automation.yaml` (skill-manager read model, never scanning); validate params; workflow id from the project manifest
- [ ] 2.2 Precheck and reconcile through the controlled command entry (argv, skill folder, `requires:`, per-secret grants), JSON in/out, schema-validated, timeout; per-item `recheck_after` books `automation_rechecks`
- [ ] 2.3 Policy: windows, calendar file (verified years, fail closed), skip / next-working with merge into the next real slot; checks at slot, precheck, stage start and action begin
- [ ] 2.4 `automation_work_items` with leases (`acquired / busy / reconcile`), TTL ≥ stage timeout + margin, heartbeat renewal while the turn runs, generation fencing (`stale_owner`), no takeover while any action is `started` or `unknown`, version dedup
- [ ] 2.5 `automation_actions` and the tools `coffer__automation_action_begin` / `_end` (states per design §4.7: new attempt after `failed`, `in_progress` on `waiting_external`); synthetic `stage:<run>:<stage>:<item>` action for a writing stage without a report; reconcile by command, by owner per action or per item (`--item`), with evidence; audit
- [ ] 2.6 `coffer__automation_report`: first valid report per (run, stage, item) wins, `already_reported`, refused after the stage ended or for a stale generation; commit to `runs.db` first, then the checkpoint file idempotently by generation; startup rewrite of checkpoints behind `runs.db`; milestones
- [ ] 2.7 Per-stage executors (Codex `network: on | off`); session continuation only within one agent kind and one item
- [ ] 2.8 Unattended mode for every scheduled run, chat or workspace: Claude Code `dontAsk` with the user's setting sources and Coffer's automation tools in `allowedTools`, permission denial → `needs_approval` naming the tool; Codex `approvalPolicy: never`, sandbox `workspace-write`, network from the executor, a detectable denial recorded as the stage's reason; refuse an adapter without such a mode; person-sent chat turns keep full permissions
- [ ] 2.9 Generic fixture flow `sample-counter` (local tracker, local outbox) in `backend/tests/fixtures/`
- [ ] 2.10 Tests, acceptance(automation, …): "no change starts no model", "a failing precheck defers the run", "a recheck runs beside the task's slots", "two tasks on one project never own one item", "an expired lease over an unknown write is not taken over", "a stale owner's write is refused", "a writing stage cut by a daemon stop is unknown", "a writing stage that ends without a report leaves one unknown action per item", "an unknown action is refused after an agent switch", "a failed write is begun again as a new attempt", "reconcile with evidence releases the item", "a report revision is sent once", "a hand-over between agents carries the checkpoint, not the session", "a merged artefact does not complete the item", "a second report for an item is answered already reported", "a checkpoint behind the run record is rewritten at startup", "a tool Claude Code is not allowed ends the stage needs approval", "no scheduled turn runs with full permissions", "a slot on a public holiday is skipped", "a weekly slot on a holiday moves to the next working day", "a moved slot that reaches the next slot runs once", "a write after the window closes is refused", "an uncovered calendar year defers the run", "a task binds a declared flow", "a skill without a contract cannot be bound", "an unknown action is resolved from the command line"

## 3. Surfaces, contract, docs, canvas

- [ ] 3.1 REST: task fields; `/scheduled-tasks/{uid}/items`, `/actions`, `/actions/{key}/reconcile`, `/items/{key}/reconcile`, `/precheck` (dry); `make contracts`
- [ ] 3.2 CLI: `coffer task items|actions|reconcile [--item]|precheck`; registry entries; `scripts/cli_coverage.py --check`
- [ ] 3.3 Web UI: task dialog (target, workflow, policy, executors), run detail (stages, usage, actions), work items; the page requirement stays in `channels`
- [ ] 3.4 `experimental-features`: the `scheduled_tasks` switch withdraws the three automation tools, closes the items/actions/reconcile/precheck routes, runs no precheck, recheck or reconcile, keeps leases and ledger; tests acceptance(experimental-features, …): "scheduled tasks off closes the automation tools and keeps the ledger", and "scheduled tasks off closes their routes and tools", "scheduled tasks off runs nothing and lists nothing" re-run
- [ ] 3.5 `openspec/specs/automation/data-model.md`, `contracts/`; `channels/data-model.md` trimmed; citations of the moved requirements in `channels/data-model.md` and `chat/spec.md` repointed to `automation` (`scripts/check_spec_citations.py` lists them)
- [ ] 3.6 `chat` spec: scope "both run with full permissions" to turns a person sends (MODIFIED delta in this change before the adapter work lands); note in ADR `managed-agents-run-with-full-permissions` that scheduled runs are unattended
- [ ] 3.7 Docs (en, zh): scheduled-tasks guide, new workflow-automation guide, architecture daemon/chat pages, CLI reference
- [ ] 3.8 ADR accepted; research note links
- [ ] 3.9 Run canvas boards redrawn (task dialog, run detail, work items)

## 4. Real-run verification (receipts outside the repo)

- [ ] 4.1 R1 `sample-counter` on Claude Code, real model
- [ ] 4.2 R2 `sample-counter` on Codex, real model; verify whether a sandbox/policy denial is detectable in the event stream
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
