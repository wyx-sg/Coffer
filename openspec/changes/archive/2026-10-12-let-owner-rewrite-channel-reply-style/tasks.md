## 1. Backend

- [x] 1.1 Split the channel append into the channel note and the reply style (`domain/chat/channel_prompt.py`)
- [x] 1.2 Store `*_reply_style` + `*_reply_style_base`, settle a style equal to the default, migrate `*_system_prompt`
- [x] 1.3 Read the style per chat kind through the typed config (`ChannelNoteReader`), and preview the note for a stopped channel
- [x] 1.4 Report `prompts` on the channel status

## 2. Frontend

- [x] 2.1 Show the channel note read-only and the style in force per chat kind, with the default-changed notice
- [x] 2.2 Edit the styles in a dialog starting from the style in force, with Restore default

## 3. Docs and decisions

- [x] 3.1 ADR channel-prompt-fixed-note-and-editable-style
- [x] 3.2 Docs site en + zh: guides/channels, guides/chat, architecture/chat
- [x] 3.3 Data model
