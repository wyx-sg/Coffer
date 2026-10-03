## Why

"Files changed" under a reply says which files the agent wrote and how many lines
moved, but not what changed. To review a turn the owner has to leave Coffer and
run `git diff`, which also mixes in every other turn. The Run canvas (3.1.09)
opens a changed file in a drawer with that reply's diff.

## What Changes

- The daemon records, for each assistant reply, a unified diff per file the reply
  wrote: Claude Code's file contents are captured before the reply's first write
  to each path and compared when the reply ends; Codex's `file_change` items
  already carry their diffs. Stored with the reply; deleted with it.
- `GET /chat/conversations/{id}/messages/{message_id}/files` lists the reply's
  files with added / removed counts; `…/files/diff?path=` returns one file's diff.
- "Files changed" reads the recorded list when there is one (older replies keep
  the tool-call estimate, without a diff). A file row with a diff opens a 640px
  drawer on the right, starting under the title bar: the path, +/− counts,
  "1 of N" with previous / next file and close (Esc); the diff with old and new
  line numbers, hunk headers and added / removed line backgrounds. The open
  file's row is highlighted in the card.

## Capabilities

### Modified Capabilities
- `chat`: per-reply file diffs and the diff drawer; "Summarise the files a reply changed" reads the recorded files.

## Impact

Claude Code adapter (PreToolUse hook on write tools, shared with add-coffer-ask),
Codex mapping, a new table + migration, two routes, the contract, FilesChangedCard
and a new DiffDrawer; docs-site chat guide (en + zh).
