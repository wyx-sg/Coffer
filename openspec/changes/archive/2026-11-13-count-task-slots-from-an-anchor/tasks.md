## 1. Scheduling

- [x] 1.1 Count slots from a per-task anchor kept in `local/scheduled-task-anchors.json`; resume and schedule edits start nothing
- [x] 1.2 Catch up the most recent missed slot within seven days; remove the grace formulas
- [x] 1.3 Refuse resuming a one-off whose time has passed; close an interrupted run as `stopped`; keep the running mark correct when a run cannot be recorded
- [x] 1.4 Remove the upgrade code for old task files and the prompt length limit

## 2. Tasks and surfaces

- [x] 2.1 Require the prompt at creation; remove the created-paused and empty-prompt rules
- [x] 2.2 Optional `cwd` in the config; a named folder that is gone fails the run
- [x] 2.3 Remove the file-tree routes and `coffer task files`; regenerate contracts and the CLI reference
- [x] 2.4 Page: prompt and folder in New task, two tabs, prompt on Overview, History limited to the latest 200
- [x] 2.5 Overview "Needs you" lists a task paused after three failed runs

## 3. Docs

- [x] 3.1 Move the requirements to `openspec/specs/scheduled-tasks/spec.md` and update them; data model
- [x] 3.2 ADR, docs-site guide and architecture (en and zh)
- [x] 3.3 Design canvases
