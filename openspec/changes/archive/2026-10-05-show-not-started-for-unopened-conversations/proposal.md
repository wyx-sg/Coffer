## Why

A channel conversation on which no turn has run (a fresh `/new` or thread) has no
native session, so the Conversations page showed its **Open in <terminal>** split
button disabled. The owner read the disabled button as a bug.

## What Changes

- A row with no native session shows a muted **Not started** in place of the
  split button. Its tooltip says no turn has run yet, so there is no session to
  open, and that it can be opened once its first message is answered.
- No Copy command is offered for it, as before. The row stays listed: it is the
  conversation the chat's next message goes to.

## Impact

- Frontend: `SessionOpenButton`, copy in `en.json` / `zh.json`. Same on Agent ›
  Sessions, which uses the same row.
- Specs: chat ("Open a conversation in the terminal").
- Design canvas: the Run canvas's Conversations board.
