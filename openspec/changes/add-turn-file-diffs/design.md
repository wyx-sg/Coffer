## Decisions

### Capture: snapshot before the first write, diff at the end of the reply
Claude Code runs under `bypassPermissions`, so the adapter registers a
`PreToolUse` hook matching `Edit|MultiEdit|Write|NotebookEdit` (hooks run in every
permission mode). The first time a reply touches a path, the hook reads the file
(absent → empty) into the reply's snapshot map; later writes to the same path keep
the first snapshot. When the reply ends — complete, failed or stopped — the
adapter reads each path again and stores `difflib.unified_diff` with 3 lines of
context, and the added / removed counts from that diff. Tool calls that failed
still count if the file actually changed; a path whose content ended identical is
dropped. Codex: each `file_change` change carries a unified diff; diffs for the
same path in one reply are stored in order and counted from their `+` / `-` lines.
*Alternative:* `git diff` at the end of the reply — wrong outside a repo and mixes
in the user's own uncommitted edits.

### Limits
A file over 1 MB or not valid UTF-8 is stored with counts only and
`diff_omitted: "binary" | "too_large"`; the drawer says so. Files changed by Bash
commands are not captured (they never were in Files changed either).

### Storage and API
Table `chat_reply_files(message_id FK → chat_messages ON DELETE CASCADE, seq,
path, added, removed, diff TEXT NULL, diff_omitted TEXT NULL)`. The list route
returns `[{path, added, removed, has_diff}]`; the diff route returns
`{path, added, removed, diff, diff_omitted}`, where `diff` is the unified text and
the frontend parses it into rows (old no., new no., kind, text) and hunk headers.

### Drawer
A Sheet at the right edge, 640 wide, top at the title bar's bottom (44 in the
desktop shell, 0 in a browser), over the thread without dimming the title bar.
Previous / next walk the card's rows that have a diff; Esc and × close; the URL
does not change.

## Risks

- A long reply writing hundreds of files → snapshots are read lazily per path and
  capped at 200 files per reply; beyond that, counts only.
