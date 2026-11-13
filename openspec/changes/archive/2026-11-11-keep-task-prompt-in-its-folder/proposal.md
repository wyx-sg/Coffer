## Why

Using the first real scheduled task (a daily report of the owner's SeaTalk
bot), the owner asked for the prompt to read and edit like a file, for reports
that are files they can open later and not only a DM, and for a detail page
in tabs with the run history as a searchable, filterable table
(ADR a-scheduled-task-s-prompt-is-a-file-in-its-own-folder).

## What Changes

- Every task has its own folder, `~/.coffer/content/workspace/scheduled-tasks/<uid>/`.
  Its prompt is `PROMPT.md` there, never in the config; a config carrying a
  prompt is refused, and one written before 2026-11-11 is moved into the file
  at startup. A run reads the file when it starts; a missing or empty file
  fails the run.
- A task that names no directory runs in its folder, so what it writes stays
  there.
- `PUT /scheduled-tasks/{uid}/prompt` (`coffer task prompt`), and the folder
  read-only through `GET /scheduled-tasks/{uid}/files` (`coffer task files`)
  and `/files/content`; a task's `prompt` and `folder` are in its read.
- `POST /channels/{uid}/notify` (`coffer channel notify`) takes `files`, sent
  after the text the way a reply's files are.
- The detail page has four tabs: Overview, Prompt (`PROMPT.md` as a Markdown
  file, editable), History (a table: search, filter by outcome and trigger,
  sort) and Files. The Edit dialog no longer carries the prompt.

The main spec (channels) was edited directly: a scenario is renamed ("a task
that names no directory runs in its own folder"), which a MODIFIED delta
cannot do.
