## 1. Channel backend

- [x] 1.1 Answer a queued message "⏳ Queued (n)"; drop only past ten waiting, with the reason
- [x] 1.2 Answer `/new` with a one-line card (Agent, Model, Dir) and add the agent card
- [x] 1.3 `/status`: title, one settings line, state, parallel threads; Stop only while a turn runs
- [x] 1.4 `/help`: the roster on one line; New, Stop, Model, Status and Resume
- [x] 1.5 `/dir`: paths shown with `~`, the default folded into the card, "/dir is off" with none allowed
- [x] 1.6 Default directory: absolute-path validation, `coffer channel add|edit --default-dir`, `edit --no-default-dir`, shown by `coffer channel show`

## 2. Channels page

- [x] 2.1 Add dialog: any display name, registered as the title with a derived, unique name
- [x] 2.2 Settings in the board's order; Name edits the title
- [x] 2.3 Replies: Long-task ping after, then Show step lines, hints inline
- [x] 2.4 Working directories: Default folder, Allowed for /dir rows with Remove, Add directory…, the default marked
- [x] 2.5 Overview command hint names `/new <agent>`; link reads "Conversations from <name>"; ⋯ menu labels as drawn

## 3. Conversations page

- [x] 3.1 Board alignment (see the `chat` delta)

## 4. Docs and tests

- [x] 4.1 Channels guides and the chat architecture page
- [x] 4.2 Backend, frontend and e2e tests for the new behaviour
