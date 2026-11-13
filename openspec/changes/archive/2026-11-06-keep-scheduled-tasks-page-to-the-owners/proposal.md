# Keep the Scheduled tasks page to the owner's own tasks

## Why

The Scheduled tasks page also listed the daemon's own background workers
under **Coffer internal**. The owner read them as scheduled tasks and found the
list confusing: the page should hold only tasks the owner (or their agents)
set up. Plain timer loops were taught to report as `timer` workers only so
that section could list them; with the section gone that reporting has no
reader, so it goes too (Coffer stays as lean as it can).

## What Changes

- The Scheduled tasks page no longer has a Coffer internal section or worker
  pages.
- `runtime.workers` lists the wakeable workers only, as before this branch:
  no `timer` mode.

## Impact

- Spec `daemon`: "Show Coffer's own background work beside the owner's tasks"
  removed. "Report each background worker's schedule on the status" is put
  back as it reads on main: its `timer` mode and scenario were added on this
  unmerged branch only, and a MODIFIED delta cannot drop a scenario.
- Spec `web-ui`: the sidebar entry's line for Scheduled tasks no longer names Coffer's own work.
- Web UI, the daemon status contract, docs en/zh, Run canvas.
