## 1. Backend

- [x] 1.1 Schedule union, cron parser, local-time slots; task config, limits, grace
- [x] 1.2 `scheduled_task` kind (machine-local), validation, eager registration
- [x] 1.3 `scheduled_task_runs` table (migration 0155), repo, retention policy
- [x] 1.4 Scheduler worker (wakeable loop), runner through the turn driver
- [x] 1.5 `[SILENT]` replies, run outcomes, pause after three failures
- [x] 1.6 Turn origin registry; the gateway hands turn-scoped tools their turn
- [x] 1.7 `coffer__schedule_task`, `coffer__scheduled_tasks`, `coffer__cancel_scheduled_task`
- [x] 1.8 Daily report template and material (both agents' session tails)
- [x] 1.9 `/status` lists and cancels waiting tasks
- [x] 1.10 Routes `/api/v1/scheduled-tasks`, CLI `coffer task`
- [x] 1.11 Timer loops report to the worker registry (mode `timer`)
- [x] 1.12 Tests for every scenario

## 2. Web UI and contract

- [x] 2.1 `make contracts`
- [x] 2.2 Scheduled tasks page: my tasks, task detail, new/edit dialog, Coffer internal
- [x] 2.3 Channels page: Daily report card
- [x] 2.4 Navigation, en and zh copy, tests

## 3. Docs

- [x] 3.1 Scheduled tasks guide; channels guide (en, zh)
- [x] 3.2 Architecture chat and daemon pages (en, zh); CLI reference and coverage
- [x] 3.3 ADR `scheduled-tasks-are-turns-coffer-starts-in-a-chat`; research note
- [x] 3.4 Data model
- [x] 3.5 Run canvas boards
