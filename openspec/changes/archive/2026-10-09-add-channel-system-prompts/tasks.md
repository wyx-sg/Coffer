## 1. Backend

- [x] 1.1 `direct_system_prompt` / `group_system_prompt` on the common channel config: default empty, trimmed, at most 4,000 characters
- [x] 1.2 `ChannelNote.owner_prompt`; `ChannelNoteReader` picks the prompt by the conversation's chat kind from the stored config on every turn
- [x] 1.3 `channel_system_context` appends it after the note under `Instructions from the channel's owner:`; empty appends nothing
- [x] 1.4 Tests: config cap and trimming; the note text; the reader per chat kind and after an edit; Claude Code resume and Codex `thread/resume` carry the current prompt; REST save, status settings and the 422

## 2. Wire and frontend

- [x] 2.1 Regenerate the REST contract and the frontend types (`make contracts`)
- [x] 2.2 System prompts section on the channel's Settings tab with an Edit button and dialog (two text areas, count, Cancel, Save); en and zh strings
- [x] 2.3 `planChannelEdit` writes a prompt only when it changed; the settings auto-save reports whether a save landed
- [x] 2.4 Tests: shown as written, blank when empty, edited and saved through the dialog, Cancel saves nothing, too long refused, a refused save keeps the dialog open

## 3. Docs and specs

- [x] 3.1 Spec delta for channels; `data-model.md`
- [x] 3.2 Channels guide (English and Chinese)
- [x] 3.3 `make verify`; archive the change
