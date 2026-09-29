# Redesign the channel commands and mirror web replies into their channel

## Why

The commands a user types in a SeaTalk or Telegram chat grew one at a time and
it shows: `/new` and `/agent` both open a fresh conversation, `/effort` is half
of the model choice, `/new` forgets the model and effort the user picked while
the agent sticks, there is no way back to an earlier conversation and no way to
change the working directory, `/status` prints a ULID, and every text starting
with `/` is swallowed — a message that opens with a path never reaches the
agent. SeaTalk has no command menu at all, and a Telegram group menu tap
(`/status@bot`) is not recognised. Separately, a reply typed on the Chat page
into a conversation a channel started never reaches the phone.

## What Changes

- Nine commands, one roster: `/new [agent]`, `/stop`, `/model [name] [level]`,
  `/dir [path|name]`, `/status`, `/resume [n]`, `/thread [title]`,
  `/kb [collection]` (was `/save`), `/help` (`/start` hidden alias).
- **BREAKING** `/agent`, `/effort`, `/threads` and `/save` are removed, with no
  pointer. Any unreserved `/word` goes to the agent; a near-typo of a command
  gets "Did you mean /stop?".
- A chat remembers its agent, model, effort and directory; `/new` keeps them.
- `/model` covers the effort (`/model high`, `/model default`, a two-step card).
- `/dir` switches to a directory on the channel's new `directories` allow-list
  (Channels page settings, `coffer channel edit --dir`), in a fresh conversation.
- `/resume` lists and reopens this chat's earlier conversations.
- `/status` and `/help` are cards with Stop / New / Model / Resume / Dir
  buttons, without ids; the help follows pairing.
- SeaTalk group main chat: settings become the group's defaults for new threads;
  `/stop` there stops every turn in the group.
- Telegram: `/cmd@ourbot` is `/cmd`; menus registered per scope (private: all,
  groups: six) in English and Chinese; `/kb` only while knowledge is on.
- A web reply into a channel's conversation is also sent to that chat/thread as
  `(from Coffer) …` and the agent's answer follows; a reply the channel cannot
  send is kept, shown as not delivered, and retried. The conversation's REST
  view says where a reply will also go.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `channels`: the command set, sticky settings, `/dir`, `/resume`, status and
  help cards, slash pass-through, group defaults.
- `channels/telegram`: `@botname` commands, scoped bilingual menus.
- `channels/seatalk`: main-chat mentions are marked.
- `chat`: web replies are mirrored into their channel; the page shows where.

## Impact

- Backend: `application/channel/*` (commands and cards), Telegram/SeaTalk
  adapters, a new `ChannelMirror` behind a chat port, migration 0108
  (`channel_thread_conversations` columns, `channel_thread_history`,
  `channel_outbox`), channel config `directories`.
- REST: `ChannelBindingOut.mirror`, `SendMessageAck.mirror`; regenerated
  contracts and frontend types.
- CLI: `coffer channel add|edit --dir`, `edit --no-dirs`; `show` lists them.
- Web: channel settings edit the directories; the Chat composer shows the
  mirror target and undelivered replies (en + zh).
- Docs: channel guide and channels architecture page.
