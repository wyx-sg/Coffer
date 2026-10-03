## 1. Backend

- [ ] 1.1 Table `chat_reply_files` + migration; repository
- [ ] 1.2 Claude Code adapter: PreToolUse snapshot hook (shared hook registration with add-coffer-ask), diff at reply end
- [ ] 1.3 Codex mapping: collect `file_change` diffs per reply
- [ ] 1.4 Routes: list files, one file's diff; `make contracts`

## 2. Frontend

- [ ] 2.1 FilesChangedCard reads recorded files, falls back to the estimate; clickable rows, highlight
- [ ] 2.2 DiffDrawer (640, under the title bar): header, 1 of N, prev / next, Esc; unified-diff parser with tests

## 3. Docs and tests

- [ ] 3.1 Tests per scenario with acceptance markers
- [ ] 3.2 docs-site guides/chat (en + zh)
