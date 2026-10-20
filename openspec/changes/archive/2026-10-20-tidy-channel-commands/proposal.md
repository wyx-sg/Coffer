## Why

The channel `/help` card squeezed the nine commands onto one line with no word
on what each does, and carried a button per command, paged three ways because
nine buttons do not fit a card. `/status` carried New and Resume, which have
nothing to do with the state it shows. A `/stop` held the messages queued
behind the turn with no way to drop them, and `/status` counted held messages as
waiting. The options are argued in ADRs
`channel-help-is-a-list-and-cards-carry-only-their-own-actions` and
`held-channel-messages-are-continued-or-discarded`.

## What Changes

- **`/help` is a list.** A "Commands" heading, one line per command with its
  arguments and what it does (the same descriptions the Telegram menu shows),
  and no buttons. A group's list has its four commands and says the others work
  in a private chat. The help card and its page kind are gone; pairing ends with
  the list.
- **Roster.** Order new, stop, status, model, dir, resume, thread, del, help;
  descriptions rewritten in English and Chinese.
- **Cards carry their own actions.** `/status`: Stop while a turn runs,
  Continue and Discard while messages are on hold, then Model and Dir. `/model`
  gains a Default option, first on the card.
- **Held messages.** The stopped line says how many are on hold and carries
  Continue and Discard (on the edited line, or as a card after the reply where
  the platform cannot edit). `/status` reads "⏸ n on hold". The orchestrator
  gains `held`, `resume_held` and `drop_held`.

## Impact

- Specs edited directly (`skip_specs: true`): channels — new requirements
  "List the commands with /help" (replacing "Offer the commands as a help card")
  and "Continue or discard the messages a stop held"; "Report the chat's state
  as a status card", "Switch the model from chat", "Answer the conversation
  commands from any paired chat" and their scenarios updated; chat — "Pause the
  pending queue on interrupt" names the channel's Continue and Discard.
- Code: `application/channel` (status card, cards, held queue, stop line),
  `application/chat/turn_orchestrator.py`, `domain/channel/commands.py`.
- Docs: reference channel commands, channel guides, chat architecture, en and zh.
