## Why

`~/.claude/rules/coffer-memory.md` is loaded into every Claude Code session.
On the maintainer's Mac it had grown to 74 lines from Codex: 23.8 KB, about 6k
tokens. Each line repeated its copy's absolute path and a 200-character
description. Most lines were notes from one Codex task (an IA sheet, a PIC
notice, an appraisal). A dozen restated a preference Codex had already lifted
into its summary. In 14 days, no session opened one of the files behind those
lines. The options are argued in ADR
`the-claude-code-rules-file-lists-only-standing-memories`.

## What Changes

- The rules file lists only the **standing** memories, every one but a bullet
  of a Codex `MEMORY.md` task group, with Codex's User Profile first. Each is
  one line of at most 120 characters of title and description plus its file
  name. The folder is written once.
- Task-group memories are not listed. One line names each task group with its
  count and points at the global folder's `MEMORY.md`. That file's Coffer block
  now lists every global memory under its group, without the 30-line cap.
- The rules file is bounded at 8 KB (was 25 KB). Standing memories that do not
  fit are counted in a line pointing at that `MEMORY.md`.

## Impact

- `infrastructure/memory/writers/claude_code.py`; new
  `infrastructure/memory/codex_identity.py` (the reader's identity format, read
  back); `readers/codex.py` uses its `PROFILE_ANCHOR`.
- Spec `memory` (requirement and data model), edited directly
  (`skip_specs: true`).
- docs-site architecture `memory.md`, guide `memory.md`, reference
  `filesystem.md` (en, zh). No UI change, so no canvas.
