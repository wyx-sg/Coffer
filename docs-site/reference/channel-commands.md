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
| `/stop` | Interrupt the running turn and pause the queue. “⏹ Stopping…” is edited into “⏹ Stopped after 12s.” where the platform can edit a message, and followed by a second message where it cannot. A question waiting on you is cancelled and its card reads “⏹ Stopped”. |
| `/model [name]` | Show or set the model. |
| `/dir [path\|name]` | Show or switch the working directory, in a fresh conversation. |
| `/status` | What this chat is running, as a card with quick actions. |
| `/resume [n]` | Reopen an earlier conversation from this chat. |
| `/thread [title]` | In a direct chat, open a parallel conversation in its own thread. |
| `/del` | Owner only. Withdraw the bot's reply: quote one of its messages and send `/del` to withdraw that whole reply, or send it bare to withdraw the bot's most recent reply in this chat or thread. |
| `/help` | List the commands, with New, Stop, Model, Status and Resume buttons (New and Stop in a group), under the title **Commands**. |

In a group only `/new`, `/stop`, `/help` and `/del` work; the other five work only in a direct chat (see [Where each command works](#where-each-command-works)). `/start`, which a Telegram start link sends, answers like `/help`. `/new` and `/stop` take effect even while a turn is running. A command first releases any messages still waiting out their pause, so they run before it; `/stop` discards them instead.

## How the commands read

Every command that holds a setting follows one grammar:

- **Bare** shows what is in effect, and on a platform with buttons offers a card to change it: `/model`, `/dir`, `/resume`.
- **An argument sets it**: `/model opus`, `/dir coffer`, `/resume 2`.
- **`default` resets it**: `/model default`, `/dir default`.

Names are the ones you see, never internal ids. An agent is its display name or its lowercase hyphenated name (`claude-code`, `codex`); case, `-`, `_` and spaces do not matter. A model is its id or the name its button shows.

## Where each command works

`/new`, `/stop`, `/help` and `/del` control the group's own conversation and its replies, so they work in a group. `/model`, `/dir`, `/status`, `/resume` and `/thread` configure or inspect your own chat with the bot, so they work only in a direct chat.

| Command | Direct chat | Parallel thread | Group thread | Group main chat |
| --- | --- | --- | --- | --- |
| `/new [agent]` | ✓ | ✓ | ✓ | SeaTalk: sets the group's default agent; bare shows it |
| `/stop` | ✓ | ✓ | ✓ | SeaTalk: stops every turn running in the group |
| `/model` | ✓ | ✓ | Direct chat only | Direct chat only |
| `/dir` | ✓ | ✓ | Direct chat only | Direct chat only |
| `/status` | ✓, with the parallel threads | ✓ | Direct chat only | Direct chat only |
| `/resume` | ✓ | ✓ | Direct chat only | Direct chat only |
| `/thread` | ✓ | ✓ | Direct chat only | Direct chat only |
| `/del` | ✓ | ✓ | ✓ | ✓ |
| `/help` | ✓, all nine | ✓ | ✓, the four group commands | ✓, the four group commands |

Sent in a group by the owner, a direct-chat-only command is answered privately to the sender where the platform supports private delivery, with one line, “This command works in a private chat with me.”, and does nothing else: it is not passed to the agent and sets nothing. `/help`, that notice and any "Did you mean" correction are the only private answers in a group; `/new` and `/stop` change something the whole room shares, so they stay visible.

## Withdrawing a reply with /del {#withdrawing-a-reply-with-del}

`/del` is for the owner only; anyone else's `/del` does nothing. Quote one of the bot's messages and send `/del`, and the whole reply that message belongs to is withdrawn, including every part a long reply was split into. Sent without a quote, `/del` withdraws the bot's most recent reply in that chat, or in that thread when you send it inside one. It works in direct chats and in groups.

The `/del` message itself is deleted where the platform allows it: on Telegram when the bot has the right to delete messages in that chat, otherwise it stays. How a reply is withdrawn, and how long it can be, differs by platform; see [Withdrawing a reply](/guides/channels#withdrawing-a-reply). In a group, every reply also carries a 🗑 button that does the same for the owner.

## Other slash text goes to the agent

Only the nine words above are taken out of the conversation. `/compact`, a skill such as `/review`, or a message that opens with a path such as `/Users/me/app crashes on start` reaches the agent like any other message, so the agent's own slash commands keep working from your phone.

A word that is one slip away from a command — `/stpo`, `/stat`, `/threads` — is answered with one line, `Unknown command /stpo. Did you mean /stop? Send /help for all commands.`, and nothing runs. Short commands (four letters or fewer) tolerate one wrong letter, longer ones two; a swap of two neighbouring letters counts as one.

## Settings stick to the chat

Each chat, and each thread in it, remembers three settings: the agent, the model and the working directory. Every fresh conversation opened there — by `/new`, by `/dir`, or because the old conversation was deleted — starts with them.

This is why `/new` is safe to use often: it clears the context, not your choices. What a chat has not set falls back to its group's defaults (in a group thread), then to the channel's default agent and configuration.

- `/new <agent>` switches the agent and remembers it. A model chosen for the previous agent does not follow it, because one agent's model means nothing to another; the directory does follow.
- An existing conversation cannot change its agent or directory — an agent session is tied to both — so switching either opens a fresh conversation. The old one stays one `/resume` away.
- The model is re-read on every turn, so `/model` applies to the next turn of the same conversation.

## Model

- `/model <name>` sets the model. A name the agent's catalogue does not list is passed to the agent's CLI as is, so you can use a model the picker does not show; a name the agent cannot run comes back as the CLI's own error on the next turn.
- Whatever word follows `/model` is a model name, `high` or `max` included; the only reserved word is `default`. `/model default` clears the model, returning to the agent's own default. Coffer has no reasoning-effort setting.
- Bare `/model` shows the model in effect. On a platform with buttons it is a card: tap a model. The answer is one line, “Model: Claude Sonnet 5.5 — from your next message”.

## Working directory

A conversation normally runs in the Coffer-managed workspace `~/.coffer/content/workspace`. `/dir` moves the chat to another directory, but only to one the channel allows. The allow-list exists because anyone holding your phone — or a slip of the thumb — should not be able to point an agent with full permissions at an arbitrary folder on your machine; you decide the places in advance, at the computer.

Both live on the channel's **Settings** tab under **Working directories**. **Default** is where new conversations start (none means the Coffer workspace); **Allowed for /dir** lists the folders `/dir` may switch into — add one with **Add directory…**, take one out with **Remove**, and the default's row is marked *default*. With none allowed, `/dir` is off.

Paths must be absolute; a relative one is refused and nothing is saved. Each allowed directory also admits the directories beneath it.

- `/dir <path>` accepts an allowed path or one beneath it; `/dir <name>` accepts the base name of one allowed path (`/dir coffer`). The directory must exist.
- Switching opens a fresh conversation there and remembers the directory for the chat.
- `/dir default` returns to the channel's default directory.
- Bare `/dir` shows the directory in effect and offers the allowed ones as a **Working directory** card, each by its path (`~/…` under your home folder), plus **Default** when the default is not one of them. The card says “A new directory starts a new conversation.” A switch answers “📁 Now in `<path>` — started a fresh conversation.”
- A directory outside the list is refused, naming the allowed ones. A channel with no allowed directory answers how to add one.

## Resume an earlier conversation

Every conversation a chat opens is remembered for that chat. `/resume` lists its last 20, newest first, each as “1 · title — Agent · 2h ago”, with numbered buttons, and ticks the one in effect. `/resume 2`, or a tap on the card, makes that conversation the chat's active one again (“↩️ Resumed “title” with Codex.”), so your next message continues it.

Only conversations this chat opened are offered — never one from the web page or from another chat — and a conversation deleted since is left out.

## Status and help cards

`/status` answers in words, not ids, under the title **Status**: the conversation's title (or its `🧵#N` mark); one line with the agent, the model and the directory; then **Running**, **Running · 2 waiting** or **Idle**. In a direct chat it also lists the parallel threads on one line, each with whether it is running, waiting or idle.

In a direct chat `/help` lists the commands on one line, `/new [agent] · /stop · /model [name] [level] · /dir · /status · /resume [n] · /thread · /del · /help`, and says that anything else is a message to the agent. In a group it lists only `/new [agent] · /stop · /del · /help`.

`/new` answers with one line — "🆕 New conversation · Codex · Default model · ~/src/coffer" — and, on a platform with buttons, **Agent**, **Model** and **Dir** buttons in a direct chat and only the **Agent** button in a group. **Agent** offers the agents this channel may drive; a tap starts a fresh conversation on it, as `/new <agent>` does.

On a platform with buttons, `/status` is a card with **New**, **Model**, **Resume** and **Dir** buttons, and **Stop** while a turn runs; `/help` is a card with **New**, **Stop**, **Model**, **Status** and **Resume** in a direct chat, and with **New** and **Stop** only in a group. A tap does exactly what typing the command in that chat does, so remembering `/status` is enough to reach every action. On a platform with no command menu (SeaTalk), `/help` is how you see what the bot accepts.

## Group defaults on SeaTalk

On SeaTalk every @mention in a group's main chat roots a fresh thread, so a setting sent there would configure a thread nobody continues. Instead, the two commands a group may send in the main chat configure the group:

- `@bot /new <agent>` sets the group's default agent, and the answer says "default for new threads in this group". Every new thread in the group starts on it; a thread's own settings still win inside it.
- `@bot /stop` interrupts every turn running in the group and lists what it stopped.

`/model`, `/dir`, `/status` and `/resume` no longer set group defaults there; they are direct-chat commands and get the private notice. A Telegram group's main chat is itself one conversation, so `/new` and `/stop` there apply to that conversation as usual.

## Command menus

Telegram shows a command menu; Coffer registers it from the same list the help and the typo check use, so the three never disagree. Private chats get all nine commands; groups get only `/new`, `/stop`, `/del` and `/help`, the ones that control the group's own conversation. Each menu is registered in English and Chinese. In a group, a menu tap arrives as `/status@your_bot`, which Coffer treats as `/status`. SeaTalk has no command menu, so it has a single surface: send `/help`, and a command that is only for a direct chat answers with the one-line private notice.

The English descriptions are:

| Command | Menu description |
| --- | --- |
| `/new` | Start a fresh conversation [agent] |
| `/stop` | Stop what’s running |
| `/model` | Pick a model |
| `/dir` | Pick the working directory |
| `/status` | What is running, threads |
| `/resume` | Go back to a conversation |
| `/thread` | Open a parallel thread |
| `/del` | Withdraw a reply |
| `/help` | Commands |

## Selection cards

On a platform with buttons, a bare `/model`, `/dir` and `/resume` in a direct chat answer with a selection card. A card carries at most six buttons; a longer list is paged, four choices at a time with **← Prev** and **Next →**, shown inactive at either end. Paging changes nothing — only tapping a choice does. The choice in effect carries a ✓ in front. After a tap, the card is rewritten in place so the tick moves to your new choice.

A button tap is checked exactly like a message: only the owner's taps count. If the platform refuses a card, the command answers in plain text instead.
