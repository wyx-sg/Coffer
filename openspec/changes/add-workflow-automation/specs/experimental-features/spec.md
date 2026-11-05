## MODIFIED Requirements

### Requirement: Close the scheduled tasks feature's surfaces
While `scheduled_tasks` is off, `/api/v1/scheduled-tasks` MUST answer 404
`FEATURE_DISABLED` and the kind-agnostic resource routes MUST refuse and leave
out `scheduled_task` resources; the scheduler MUST start no run, Run now
included; `coffer__schedule_task`, `coffer__scheduled_tasks` and
`coffer__cancel_scheduled_task` MUST be absent from every turn; `/status` in a
chat MUST list no task and its Cancel buttons MUST cancel nothing; and the web
UI MUST hide the Scheduled tasks entry and page and the Daily report card on a
channel's Overview. Switching it off MUST keep every task and its history;
switching it on again MUST bring the scheduler's next pass forward with no
daemon restart, and a slot that passed while it was off is caught up once or
skipped and recorded, as any missed slot is ([automation](../automation/spec.md)
"Catch up a missed run once, within its grace").
While it is off, `coffer__automation_action_begin`,
`coffer__automation_action_end` and `coffer__automation_report` MUST also be
absent from every turn; the work-item, action, reconcile and precheck routes
under `/api/v1/scheduled-tasks/{uid}` (`items`, `actions`,
`actions/{key}/reconcile`, `items/{key}/reconcile`, `precheck`) MUST answer 404 `FEATURE_DISABLED` like
the rest; no precheck, recheck or reconcile command MUST run; and every
work-item lease, action of the ledger and recorded model call MUST be kept as
it is, so switching it on again resumes from them.

#### Scenario: scheduled tasks off closes their routes and tools
- **GIVEN** `scheduled_tasks` off
- **WHEN** a route under `/api/v1/scheduled-tasks` is requested, and a channel turn lists its tools
- **THEN** the route answers 404 `FEATURE_DISABLED` naming `scheduled_tasks`
- **AND** the turn is offered none of the three scheduling tools

#### Scenario: scheduled tasks off runs nothing and lists nothing
- **GIVEN** `scheduled_tasks` off and an enabled task whose slot has come
- **WHEN** the scheduler's pass runs, and `/status` is sent in the task's chat
- **THEN** no run starts and `/status` lists no task
- **AND** once `scheduled_tasks` is switched on, the next pass considers the task again

#### Scenario: scheduled tasks off closes the automation tools and keeps the ledger
- **GIVEN** `scheduled_tasks` off, a workflow task with an item that needs reconcile and a recheck due
- **WHEN** `GET /api/v1/scheduled-tasks/{uid}/items` and `POST /api/v1/scheduled-tasks/{uid}/precheck` are requested, the recheck time passes, and a turn lists its tools
- **THEN** both routes answer 404 `FEATURE_DISABLED`, no precheck runs, and the turn is offered none of the three automation tools
- **AND** once `scheduled_tasks` is switched on, the item still needs reconcile with its lease and unknown action unchanged
