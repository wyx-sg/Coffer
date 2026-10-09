## Why

Owners want a channel to carry standing instructions of their own — the language
to answer in, a team's conventions, what every answer must name — without
repeating them in every message. And what suits a private chat with the bot
rarely suits a busy group: a group wants terser answers and tighter manners
than a direct chat does. Today the only system prompt a channel turn carries is
Coffer's built-in channel note, which the owner cannot add to.

## What Changes

- **Two optional system prompts per channel**, stored in the channel's config
  beside its other settings: `direct_system_prompt` (direct chats and the
  threads opened in them) and `group_system_prompt` (a group's main chat and its
  threads). Plain multi-line text, at most 4,000 characters each, trimmed;
  empty by default.
- **Appended after Coffer's channel note**, under its own heading line
  `Instructions from the channel's owner:`, on every turn of a conversation of
  that chat kind. It never replaces the built-in note, and an empty prompt
  appends nothing. The prompt is read from the stored config when each turn's
  system context is composed, so an edit applies from the next turn with no
  restart — also on a resumed Claude Code session or Codex thread, because the
  context is sent with every turn.
- **REST and CLI**: the two fields ride the existing channel config contract
  (`PATCH /api/v1/resources/{uid}`, `coffer channel update`) and are reported in
  the channel's status `settings` with their defaults filled in. A prompt over
  4,000 characters is refused (`422`).
- **Channels page**: a **System prompts** section on the channel's Settings tab
  shows both prompts as written (blank when empty) and edits them through an
  **Edit** button and a dialog with two text areas, a character count, Cancel
  and Save.

## Capabilities

### Modified Capabilities

- `channels` — a new requirement, "Append the owner's system prompt to a channel
  turn"; "Manage channels from the Channels page" notes that the system prompts
  are edited through a dialog rather than saved as they change.

## Impact

- Backend: `domain/channel/config.py` (two fields and their cap),
  `domain/chat/channel_note.py` (`ChannelNote.owner_prompt`),
  `application/channel/prompt_note.py` (picks the prompt by chat kind),
  `infrastructure/chat/adapter_support.py` (appends it after the note).
- Wire: `TelegramChannelConfig` / `SeaTalkChannelConfig` gain the two fields
  (`openspec/specs/channels/contracts/api.openapi.yaml`, frontend generated
  types); `data-model.md`.
- Frontend: the Settings tab's System prompts section and its dialog, en and zh
  strings.
- Docs: the channels guide (English and Chinese).
