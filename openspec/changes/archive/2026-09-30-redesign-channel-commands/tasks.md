# Tasks — redesign-channel-commands

## 1. Foundation

- [x] 1.1 One roster of nine commands with Chinese descriptions, group-menu and knowledge flags, the typo guard and the effort vocabulary
- [x] 1.2 Migration 0108: thread `chat_kind` and sticky model/effort/cwd, `channel_thread_history` (back-filled), `channel_outbox`
- [x] 1.3 Thread repo (settings, chat kind, history, locate) and outbox repo
- [x] 1.4 Channel config `directories`; binding carries them; `coffer channel add|edit --dir`, `edit --no-dirs`, `show`
- [x] 1.5 Conversations open with the thread's settings, falling back to the group's defaults; history recorded

## 2. Commands

- [x] 2.1 Dispatch: reserved words only, "Did you mean", everything else to the agent; remove `/agent`, `/effort`, `/threads`, `/save`
- [x] 2.2 `/new [agent]` by user-visible names; sticky settings
- [x] 2.3 `/model [name] [level]`, `/model <level>`, `/model default`, two-step card
- [x] 2.4 `/dir` against the allow-list
- [x] 2.5 `/resume [n]` from this thread's history
- [x] 2.6 `/status` and `/help` cards with command buttons; help after pairing
- [x] 2.7 `/kb` (was `/save`), shown only while knowledge is on
- [x] 2.8 SeaTalk group main: group defaults, `/stop` for the whole group

## 3. Platforms

- [x] 3.1 Telegram `/cmd@bot` normalised and addressed; other bots' commands ignored
- [x] 3.2 Telegram menus per scope, English and `zh`; knowledge switch rebuilds the adapter
- [x] 3.3 SeaTalk main-chat mentions marked `group_main`
- [x] 3.4 Bot-initiated sends verified for SeaTalk DM / DM thread / group thread and Telegram chat / topic

## 4. Mirroring

- [x] 4.1 Chat port + channel `ChannelMirror`: send `(from Coffer) …`, render the answer, keep group main in Coffer
- [x] 4.2 Outbox when the channel cannot send; collected answer; flushed on the reconcile tick
- [x] 4.3 REST `channel_binding.mirror`, `SendMessageAck.mirror`; `make contracts`
- [x] 4.4 Chat page: "Also sends to …" and "not delivered to …" (en + zh)

## 5. Surfaces and docs

- [x] 5.1 Channel settings dialog edits the directories (en + zh)
- [x] 5.2 docs-site channel guides, chat guide and architecture page
- [x] 5.3 Spec deltas archived; citations follow the replaced titles
- [x] 5.4 `make verify`
