## Why

A review of scheduled tasks found three scheduling bugs and several rules that cost more than they gave. Resuming a paused task ran it at once, and so did moving its time earlier, because slots were counted from the last run or the task's `updated_at`. A daily 23:00 task on a Mac that slept overnight never caught up, because a repeating slot's grace ended at midnight. A run the daemon's stop interrupted counted as a failure towards the three that pause a task. The owner then simplified the page: a task is given its prompt when it is created, the Files tab is gone, and a task may pick the folder its runs work in.

## What Changes

- Slots are counted from a per-task anchor the scheduler keeps in `local/scheduled-task-anchors.json`: the last slot it ran or skipped, or the moment it first saw the task enabled with its current schedule. Resuming a task or editing its schedule starts nothing.
- The most recent missed slot runs once if it was due within seven days, for every schedule. The two grace formulas are gone.
- A paused one-off whose time has passed is refused on Resume.
- A run a stopped daemon left running is closed `stopped`, not `failed`.
- A repeating task paused after three failed runs is an item in the Overview page's "Needs you".
- **BREAKING** `POST /api/v1/scheduled-tasks` requires `prompt`; a task is created enabled. The created-paused and empty-prompt rules are gone, and so is the 8,000-character limit.
- **BREAKING** Removed: the task page's Files tab, `GET /api/v1/scheduled-tasks/{uid}/files` and `/files/content`, and `coffer task files`. The prompt is shown and edited on the Overview tab.
- A task's config may carry `cwd`, the folder its runs work in (an absolute path); without it runs work in the task's own folder. A named folder that is gone fails the run.
- The History tab shows the latest 200 runs and says so.
- Removed: the upgrade code for task files written before 2026-11-06 and 2026-11-11 (retired follow-ups, prompts and `cwd` in the config, old config keys). A one-off or manual schedule no longer accepts a `timezone`.
- The requirements moved from `openspec/specs/channels/spec.md` to a capability of their own, `openspec/specs/scheduled-tasks/spec.md`, and were edited there directly, so this change carries no delta.

## Capabilities

### New Capabilities

- `scheduled-tasks`: the scheduled-task requirements, moved out of `channels`.

### Modified Capabilities

- `channels`: no longer holds the scheduled-task requirements; its data model describes the anchors file and the `cwd` key.
- `chat`: the link to the run-history requirement points at `scheduled-tasks`.

## Impact

Backend scheduled-task domain, scheduler, runner, routes, CLI and attention sources; frontend Scheduled tasks page and Overview kinds; contracts; docs-site guide and architecture (en and zh); ADR `docs/decisions/a-missed-run-is-caught-up-within-seven-days.md` (new) and History entries in the two scheduled-task ADRs.
