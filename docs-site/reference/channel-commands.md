---
title: Channel commands
description: The nine channel commands, how each behaves in direct chats, threads and groups, how settings stick to a chat, and the command menus and selection cards.
---

# Channel commands

Nine words are Coffer's commands. Everything else you type — including other text that starts with `/` — is a message for the agent.

The table lists the nine words. How each reads, where it works and the cards it answers with follow below. To pair and start chatting, see [Channels](/guides/channels).

| Command | What it does |
| --- | --- |
| `/new [agent]` | Start a fresh conversation with this chat's settings. With an agent name, switch to that agent. |
| `/stop` | Interrupt the running turn and pause the queue. |
| `/model [name] [level]` | Show or set the model and the reasoning effort. |
| `/dir [path\|name]` | Show or switch the working directory, in a fresh conversation. |
| `/status` | What this chat is running, as a card with quick actions. |
| `/resume [n]` | Reopen an earlier conversation from this chat. |
| `/thread [title]` | In a direct chat, open a parallel conversation in its own thread. |
| `/kb [collection]` | Save the document you just sent into a [knowledge](/guides/knowledge) collection. |
| `/help` | List the commands, with New, Stop, Model, Status and Resume buttons. |

`/start`, which a Telegram start link sends, answers like `/help`. `/new` and `/stop` take effect even while a turn is running. A command first releases any messages still waiting out their pause, so they run before it; `/stop` discards them instead.

## How the commands read

Every command that holds a setting follows one grammar:

- **Bare** shows what is in effect, and on a platform with buttons offers a card to change it: `/model`, `/dir`, `/resume`, `/kb`.
- **An argument sets it**: `/model opus`, `/dir coffer`, `/resume 2`.
- **`default` resets it**: `/model default`, `/dir default`.

Names are the ones you see, never internal ids. An agent is its display name or its lowercase hyphenated name (`claude-code`, `codex`); case, `-`, `_` and spaces do not matter. A model is its id or the name its button shows.

## Where each command works

| Command | Direct chat | Parallel thread | Group thread | SeaTalk group main chat |
| --- | --- | --- | --- | --- |
| `/new [agent]` | ✓ | ✓ | ✓ | Sets the group's default agent; bare shows the group's defaults |
| `/stop` | ✓ | ✓ | ✓ | Stops every turn running in the group |
| `/model` | ✓ | ✓ | ✓ | Sets the group's default |
| `/dir` | ✓ | ✓ | ✓ | Sets the group's default |
| `/status` | ✓, with the parallel threads | ✓ | ✓ | The group's defaults and its running threads |
| `/resume` | ✓ | ✓ | ✓ | Asks you to reply inside a thread |
| `/thread` | ✓ | ✓ | Answers that every group thread is already its own conversation | Same answer |
| `/kb` | ✓ | ✓ | ✓ | ✓ |
| `/help` | ✓ | ✓ | ✓ | ✓ |

In a group, the answers to `/model`, `/dir`, `/status`, `/resume` and `/help`, and any "Did you mean" correction, are delivered privately to you where the platform supports it. `/new`, `/stop`, `/thread` and `/kb` change or point at something the whole room shares, so they stay visible.

## Other slash text goes to the agent

Only the nine words above are taken out of the conversation. `/compact`, a skill such as `/review`, or a message that opens with a path such as `/Users/me/app crashes on start` reaches the agent like any other message, so the agent's own slash commands keep working from your phone.

A word that is one slip away from a command — `/stpo`, `/stat`, `/threads` — is answered with one line such as `Did you mean /stop?`, and nothing runs. Short commands (four letters or fewer) tolerate one wrong letter, longer ones two; a swap of two neighbouring letters counts as one.

## Settings stick to the chat

Each chat, and each thread in it, remembers four settings: the agent, the model, the reasoning effort and the working directory. Every fresh conversation opened there — by `/new`, by `/dir`, or because the old conversation was deleted — starts with them.

This is why `/new` is safe to use often: it clears the context, not your choices. What a chat has not set falls back to its group's defaults (in a group thread), then to the channel's default agent and configuration.

- `/new <agent>` switches the agent and remembers it. A model and effort chosen for the previous agent do not follow it, because one agent's model means nothing to another; the directory does follow.
- An existing conversation cannot change its agent or directory — an agent session is tied to both — so switching either opens a fresh conversation. The old one stays one `/resume` away.
- The model and effort are re-read on every turn, so `/model` applies to the next turn of the same conversation.

## Model and effort

- `/model <name>` sets the model. A name the agent's catalogue does not list is passed to the agent's CLI as is, so you can use a model the picker does not show; a name the agent cannot run comes back as the CLI's own error on the next turn.
- `/model <level>` sets only the effort. The levels are `minimal`, `low`, `medium`, `high`, `xhigh` and `max`; no model is named after one.
- `/model <name> <level>` sets both, and `/model default` clears both, returning to the agent's own defaults.
- Bare `/model` shows the model and effort in effect. On a platform with buttons it is a two-step card: tap a model, and when that model has reasoning levels the same card turns into the level choice, with a button to keep the current effort.

## Working directory

A conversation normally runs in the Coffer-managed workspace `~/.coffer/content/workspace`. `/dir` moves the chat to another directory, but only to one the channel allows. The allow-list exists because anyone holding your phone — or a slip of the thumb — should not be able to point an agent with full permissions at an arbitrary folder on your machine; you decide the places in advance, at the computer.

Both live on the channel's **Settings** tab under **Working directories**. **Default** is where new conversations start (none means the Coffer workspace); **Allowed for /dir** lists the folders `/dir` may switch into — add one with **Add directory…**, take one out with **Remove**, and the default's row is marked *default*. With none allowed, `/dir` is off. Or from the CLI:

```sh
coffer channel edit my-telegram --default-dir ~/src/coffer              # where new conversations start
coffer channel edit my-telegram --dir ~/src/coffer --dir ~/src/notes   # replaces the list
coffer channel edit my-telegram --no-dirs                              # allows none
```

`--dir` is repeatable. Paths must be absolute (`~` is expanded by the shell); a relative one is refused and nothing is saved. Each allowed directory also admits the directories beneath it.

- `/dir <path>` accepts an allowed path or one beneath it; `/dir <name>` accepts the base name of one allowed path (`/dir coffer`). The directory must exist.
- Switching opens a fresh conversation there and remembers the directory for the chat.
- `/dir default` returns to the channel's default directory.
- Bare `/dir` shows the directory in effect and offers the allowed ones as a **Working directory** card, each by its path (`~/…` under your home folder), plus **Default** when the default is not one of them. A switch answers "📁 Now in `<path>` — started a fresh conversation".
- A directory outside the list is refused, naming the allowed ones. A channel with no allowed directory answers how to add one.

## Resume an earlier conversation

Every conversation a chat opens is remembered for that chat. `/resume` lists its last 20, newest first, each with its title, agent and age, and ticks the one in effect. `/resume 2`, or a tap on the card, makes that conversation the chat's active one again, so your next message continues it.

Only conversations this chat opened are offered — never one from the web page or from another chat — and a conversation deleted since is left out.

## Status and help cards

`/status` answers in words, not ids, under the title **Status**: the conversation's title (or its `🧵#N` mark); one line with the agent, the model, the effort and the directory; then **Running**, **Running · 2 waiting** or **Idle**. In a direct chat it also lists the parallel threads on one line, each with whether it is running, waiting or idle.

`/help` lists the commands on one line and says that anything else is a message to the agent.

`/new` answers with one line — "🆕 New conversation · Codex · Default model · ~/src/coffer" — and, on a platform with buttons, **Agent**, **Model** and **Dir** buttons. **Agent** offers the agents this channel may drive; a tap starts a fresh conversation on it, as `/new <agent>` does.

On a platform with buttons, `/status` is a card with **New**, **Model**, **Resume** and **Dir** buttons, and **Stop** while a turn runs; `/help` is a card with **New**, **Stop**, **Model**, **Status** and **Resume**. A tap does exactly what typing the command in that chat does, so remembering `/status` is enough to reach every action. The help also arrives once, right after you pair, which is how a platform with no command menu (SeaTalk) shows you what the bot accepts.

## Group defaults on SeaTalk

On SeaTalk every @mention in a group's main chat roots a fresh thread, so a setting sent there would configure a thread nobody continues. Instead, a command sent in the main chat configures the group:

- `@bot /new <agent>`, `@bot /model …` and `@bot /dir …` set the group's defaults, and the answer says "default for new threads in this group". Every new thread in the group starts on them; a thread's own settings still win inside it.
- `@bot /status` shows the group's defaults and what its threads are running.
- `@bot /stop` interrupts every turn running in the group and lists what it stopped.

A Telegram group's main chat is itself one conversation, so commands there apply to that conversation as usual.

## Command menus

Telegram shows a command menu; Coffer registers it from the same list the help and the typo check use, so the three never disagree. Private chats get all nine commands; groups get `/new`, `/stop`, `/model`, `/status`, `/resume` and `/help`, the ones useful to tap in front of other people. Each menu is registered in English and Chinese. In a group, a menu tap arrives as `/status@your_bot`, which Coffer treats as `/status`. SeaTalk has no command menu; the help card after pairing takes its place.

## Selection cards

On a platform with buttons, a bare `/model`, `/dir`, `/resume` and a `/kb` with no collection answer with a selection card. A card carries at most six buttons; a longer list is paged, four choices at a time with **← Prev** and **Next →**. Paging changes nothing — only tapping a choice does. After a tap, the card is rewritten in place so the tick moves to your new choice.

A button tap is checked exactly like a message: only the owner's taps count. If the platform refuses a card, the command answers in plain text instead.
