## Why

A channel turn carries instructions Coffer writes (where the agent is, what
renders, how to send files and ask with buttons, how a reply should read), and
the owner could add text after them. The owner could not see Coffer's text, and
could not change any of it, only pile on instructions that sometimes
contradicted it. The owner asked for the built-in prompt to be shown by default
and to be editable.

## What Changes

- The channel append is split into a **channel note** (how the channel works,
  generated per channel and chat kind, read-only) and a **reply style** (how a
  reply should read: Coffer's default, or the owner's rewrite per chat kind).
- **BREAKING** (config keys): `direct_system_prompt` / `group_system_prompt`
  become `direct_reply_style` / `group_reply_style` (up to 6,000 characters)
  with `*_reply_style_base`, the fingerprint of the default a rewrite was
  written against. A stored owner prompt migrates on read into the default
  style followed by that prompt, so the agent reads the same instructions.
- The Settings tab's **System prompt** section shows, per chat kind, the channel
  note read-only and the reply style in force (Default / Rewritten), says when
  Coffer's default changed after a rewrite, and edits the styles in a dialog
  with Restore default.
- The channel status reports `prompts`: per chat kind, the channel note, the
  default style and whether the default changed since the owner's rewrite.

ADR: [channel-prompt-fixed-note-and-editable-style](../../../docs/decisions/channel-prompt-fixed-note-and-editable-style.md).

## Impact

- Specs: channels.
- Backend: `domain/chat/channel_prompt.py` (new), `domain/channel/config.py`,
  `application/channel/prompt_note.py`, `infrastructure/chat/adapter_support.py`,
  `surfaces/http/channel_prompt_preview.py` (new), `channel_routes.py`,
  `channel_wiring.py`.
- Frontend: the channel Settings tab's System prompt section and dialog.
- Docs: guides/channels, guides/chat, architecture/chat (en + zh).
