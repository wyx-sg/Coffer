---
title: Channels
description: Connect a Telegram bot or SeaTalk app to Coffer, pair it to your own account, and drive Claude Code or Codex from the IM app you already use.
---

# Channels

A **channel** connects one Telegram bot or one SeaTalk app to Coffer, so you can talk to your agents from your phone and receive notifications Coffer pushes. This page covers what every channel shares — pairing, the default agent and scope, the machine a channel runs on, commands, media and security. For platform setup, follow [Telegram](/guides/channels-telegram) or [SeaTalk](/guides/channels-seatalk).

## What a channel is

A channel is a registered resource of kind `channel`. It holds:

- the platform type, `telegram` or `seatalk`, and that platform's settings;
- **references** to its secrets in Coffer's [secret store](/guides/secret-store), never the secrets themselves;
- a **default agent** — the agent a new conversation on this channel starts on;
- `runs_on` — the one machine whose daemon runs the channel's adapter.

A message from you becomes a turn in an ordinary Coffer conversation, and the agent's reply goes back to the IM chat. The web [Conversations](/guides/chat) page lists it, with the channel it came from, so you can start a task on your phone and pick it up at your desk: opening the row resumes the agent's session in your terminal (see [Open a conversation in your terminal](/guides/chat#open-in-terminal)). The page is a list; there is no reply box, and nothing you do there is sent into the chat.

One bot drives every managed agent. You switch between Claude Code and Codex from the chat with `/new <agent>`, and different threads of one group can run different agents at the same time.

::: info Coffer-hosted channels only
Coffer manages the channels it hosts. An agent's own official integration — Claude Code's Telegram plugin, a vendor's Slack app, an agent-native gateway — runs on its own and is not managed or proxied by Coffer.
:::

## Register a channel

Registering stores the secret first and registers the channel with a reference to it.

```text
Channels → Add channel
  1 Platform:  SeaTalk | Telegram
  2 Connect:   Name, Default agent, Bot token (or App ID + App secret)
  3 Pair:      the code to send the bot, then "Paired with …"
```

In the web UI, **Add channel** walks three steps. **Platform** lists each platform with its logo, what it needs to connect (**Needs App ID + secret**, **Needs bot token**) and what it supports in a chat. **Connect** (**Add a Telegram channel**, **Add a SeaTalk channel**) asks for a name, the default agent and the credentials — pick a secret Coffer already holds, or paste a new one — then writes a new secret to the secret store and registers the channel in one step. **Connect** is never greyed out: press it with a field empty and the message appears under that field. A pasted Telegram token is checked as you paste it — **Found @your_bot**, and where the channel will run — so a wrong token shows up before you connect; for SeaTalk the form reminds you to set event delivery to WebSocket in the SeaTalk Open Platform *after* connecting, since the portal checks that a connection exists. **Pair** (**Pair Telegram · Personal**) issues a code straight away and waits for your message to the bot (see [Pair your account](#pair-your-account)); when it lands the step says who you paired with and how to try it, and **Done** opens the channel. **Pair later** closes the dialog and leaves the channel unpaired. With no channel yet, the page offers the platforms as a list; choosing one opens **Add channel** at **Connect**. A name is letters, digits, dash and underscore, at most 64 characters.

A registration whose secret reference does not resolve is rejected and nothing is saved. So is one naming a default agent that is not registered in this vault.

A new channel is bound to the machine you register it from and may drive every registered agent. Its adapter starts as soon as it is saved.

## Pair your account

Pairing makes you the channel's owner. Until a channel is paired, it answers nobody.

1. Issue a code: on the channel's **Overview**, **Generate pairing code** (or **Add owner** under **Who can use it** once a channel is paired), which opens the **Add an owner** dialog.

2. From your own account, send the eight characters to the bot as a message. On Telegram you can choose **Open in Telegram** instead, which opens the chat with the code filled in. The dialog shows the code with **Copy**, where to send it, the time left (*Expires in 58 min · single use*) and **Waiting for your message…** until the pairing lands, then names the new owner. **New code** replaces the code. A code that ran out is shown struck through and marked **Expired**, with the reason; **Generate a new code** issues another.
3. The bot confirms and follows up once with the [help](/reference/channel-commands#status-and-help-cards). You are now the channel's sole owner.

A code is eight characters from an alphabet with no `0`, `O`, `1` or `I`. It works once, expires after one hour, and is invalidated after 10 wrong guesses. Codes are held in the daemon's memory only, so restarting the daemon drops an unused code; generate another.

Pairing again from a different account replaces the owner. The previous owner's direct chat and group pairings are removed.

A direct chat paired by an older Coffer, before pairings recorded who the owner is, completes itself: the first message you send there is recognised as yours (in a direct chat the chat id is your own id) and the bot answers as usual. If a message cannot be matched that way, the bot asks you to pair the chat again with a new code.

## Talk to an agent

Send the bot a message. The first message opens a conversation on the channel's default agent, in the Coffer-managed workspace `~/.coffer/content/workspace`, and every later message continues it. You can move a chat to another agent, model or directory with [commands](#commands).

- A reaction (Telegram) or a typing indicator (SeaTalk) says the message was received.
- While the agent works, one status line sits at the top of the live reply, and its clock keeps moving even during a long silent tool:

  ```
  ⏳ Working · 2m 14s · 7 steps
  💬 Checking the deploy logs
  +4 earlier
  ✅ Read · checkout.spec.ts
  ✅ Bash · rerun the 3DS test
  ⏳ Grep · retry in e2e/
  ─
  The failure is the 3DS step: the sandbox answered after 30 s and…
  ```

  The `💬` line is what the agent last said before a tool call; the answer grows under the rule. The final reply keeps everything the agent wrote, one paragraph per stretch of text.

  A step line in a direct chat adds the agent's own one-line description or the file name, never the raw command. In a group it names only the tool (`⏳ Bash`), because everyone there reads it.
- A turn that fails or is stopped ends with a one-line summary: the outcome, tool count, duration and tokens. A turn that succeeds sends no summary; the reply is the signal.

### What the reply looks like

Coffer tells the agent which platform and kind of chat it is in and what renders there, and asks it for a reply shaped for a phone: the outcome in the first sentence (it is what the notification shows), no step-by-step narration, anything long under a `## Details` heading, and diagrams as images. Coffer then fits the reply to the chat:

- **Details** — on Telegram, a `## Details` section arrives collapsed. On SeaTalk, the reply carries the part before it and a card follows with the outcome as its title and **Details** and **As file** buttons: **Details** posts the section as a reply in the card's thread, **As file** sends it as a `.md` file.
- **Tables and logs** — SeaTalk cannot show a table, so each row becomes a bullet (`- **checkout** · failed · 3DS timeout`); a table bigger than 12 rows or 4 columns keeps its first five rows and arrives whole as a `.csv` file. A code block longer than 30 lines keeps its first three lines and arrives whole as a file.
- **Long replies** — are never cut inside a code block, and every message after the first starts with its place, `(2/3)`. On Telegram those continuations arrive silently; only the first one notifies.

### Questions for you

When the agent needs a yes or a choice before it goes on — a change it is about to make, say — it asks, and the turn waits for you. The question arrives as one card: what the agent wants you to see (a summary, a diff as a code block), then `❓` and the question, then up to four buttons, one to a line, with each option's description listed above them when it has one, and "Or reply with your answer." underneath. Tap an option, or just type your answer as the next message in that chat or thread: your text is the answer, it is not sent to the agent as a new message, and no turn starts. Nothing is ever posted in your name.

A question that allows several options shows them as toggles: each tap puts a `✓` on that button, and **Submit** sends the ticked ones (Submit with nothing ticked does nothing). When one ask holds several questions, the next card goes out only after you answer the previous one. In a group, only the channel's owner can answer; anyone else's tap is refused and the question stays open. On a platform without buttons the options are listed in the message and you type the answer.

Questions are answered here, in the chat; the Conversations page has no answer card. Once the question is answered, or the turn is stopped, its card is rewritten in place to `✓ Answered: Yes · 11:42` (`⏹ Stopped` after a stop) and its buttons go away; where the platform cannot rewrite the message, that line is sent as a reply instead.

### When a long turn finishes

A turn that ran longer than the channel's threshold (90 seconds by default) ends with one short line where its answer would not notify you by itself: `✅ Done · 4m 12s — <the answer's first line>`, or `⚠️ Failed · …`, `⏹ Stopped · …`. A turn that is waiting on a question pings `❓ Needs you · 4m 05s — <the question>` before its card. On SeaTalk the answer is the message that opened when the turn began, so finishing it rings nobody — the done line does, in the same thread, @mentioning you in a group. On Telegram the answer is always a new message, so it needs no extra line.

Two per-channel settings shape this, on the channel's **Settings** tab under **Replies**:

- **Show step lines** — turn it off to keep only the status header and the 💬 line, without the step list. Useful in a busy group.
- **Long-task ping after** — the long-turn threshold in seconds, 0 to 3600; 0 turns the done line off.

Messages sent in quick succession are one question. The channel waits for a short pause after each message before it starts the turn: 1.5 seconds after text, 5 seconds after a forwarded chat record or files with no text. Anything you send inside that pause joins the same turn. So you can forward a record and then type "look into this", and the agent answers once, having seen both. Each message is still acknowledged the moment it arrives.

Both pauses are per-channel settings: on the channel's **Settings** tab under **Message batching** (**Wait after a text message** and **Wait after a forward or files**). Each takes 0 to 60 seconds; 0 answers every such message on its own.

Messages you send while a turn is running wait in the conversation's queue and run in order — one queue per conversation, shared by everything that sends to it. A burst sent during a turn joins the queue as one entry. Each message that waits is answered "⏳ Queued (n)", n being how many now wait. Up to 10 may wait; a message sent while 10 already wait is dropped, and the bot says so and why.

### When a chat has been quiet

A conversation that nobody has touched for a day is rarely the one you mean to continue. When your next message reaches a chat whose conversation has been idle longer than the channel's idle period (24 hours by default), Coffer opens a new conversation instead of continuing the old one, and says so in one line before the answer: `🆕 Started a new conversation after 24 h idle.` The old conversation stays in the Conversations list, untouched. The chat's agent, model and directory carry over, as they do after `/new`. The rule applies to each conversation a channel keeps: the direct chat's, and each group thread's or parallel thread's own.

Set the period on the channel's **Settings** tab under **Conversations** (**Start a new conversation after**, in hours; 0 never starts a new one).

A conversation you delete on the Conversations page (or whose session you delete under **Agents › Sessions**) is gone: the next message from its chat opens a new conversation, without a line about it. The same happens when the agent has cleaned up the conversation's session — Claude Code does after `cleanupPeriodDays`, about 30 days by default — except that the conversation then continues as a fresh session, without the earlier context (see [Where the conversation lives](/guides/chat#chat-and-the-agent-s-own-sessions)).

### Parallel conversations

A direct chat is one conversation. To run a second task beside it without mixing contexts, send `/thread [title]`. The bot opens a thread marked `🧵#N title`, and whatever you send inside that thread runs in a conversation of its own. The mark is the thread's name in the chat, the conversation's title on the Conversations page, and the title of `/status` inside it. `/status` in the direct chat lists the parallel threads on one line, each with whether it is running, has messages waiting, or is idle.

How the thread appears depends on the platform. On SeaTalk it is the thread of your own `/thread` message: the bot answers inside it, and you reply there. On Telegram it is a private-chat topic, which needs the bot's Threaded Mode turned on in BotFather. In a group, every thread is already its own conversation, so `/thread` is not needed there.

Each turn tells the agent it is on a chat channel: keep replies concise but quote the key log lines, errors and IDs behind a finding verbatim, and it cannot click dialogs on your computer. Each turn also opens with a `[Message origin]` block naming the platform, the chat, the thread and the sender, so the agent can answer "which group is this?" and aim a platform tool call at the right chat. The turn's system prompt also carries the [memory](/guides/memory#in-channel-turns) index, and the notes your message names are added after it: Coffer delivers both itself, and on a connected agent Coffer's hook stands aside for them inside the turn, while its triggers still guard the turn's commands.

## Commands

Nine words are Coffer's commands. Everything else you type — including other text that starts with `/` — is a message for the agent.

| Command | What it does |
| --- | --- |
| `/new [agent]` | Start a fresh conversation with this chat's settings. With an agent name, switch to that agent. |
| `/stop` | Interrupt the running turn and pause the queue. |
| `/model [name]` | Show or set the model. |
| `/dir [path\|name]` | Show or switch the working directory, in a fresh conversation. |
| `/status` | What this chat is running, as a card with quick actions. |
| `/resume [n]` | Reopen an earlier conversation from this chat. |
| `/thread [title]` | In a direct chat, open a parallel conversation in its own thread. |
| `/del` | Owner only. Withdraw the bot's reply: quote it and send `/del`, or send it bare for the most recent one. |
| `/help` | List the commands, with a button for each, paged. |

In a group only `/new`, `/stop`, `/help` and `/del` work, because they control the group's own conversation and replies. `/model`, `/dir`, `/status`, `/resume` and `/thread` work only in a direct chat with the bot; sent in a group they get one private line, "This command works in a private chat with me.", and nothing else happens. To save something into [knowledge](/guides/knowledge#from-a-chat-ask-your-agent) from a chat, ask the agent.

The full reference, with where each command works, is at [Channel commands](/reference/channel-commands).

## Default agent and scope

Two settings decide which agent answers.

**The default agent** is the agent a new conversation starts on. Set it when you register the channel; change it under **Agents** → **Default agent** on the channel's **Overview**.

**The default model** is the model that agent runs on in new conversations. Pick it under **Agents** → **Default model** on the **Overview**, from the default agent's own model list; **Provider default** leaves the choice to the agent's provider. It belongs to the default agent only: a chat that switched to another agent with `/new <agent>` does not get it (the default directory still applies), a model chosen in the chat with `/model` wins over it, `/model default` returns to it, and changing the default agent clears it.

**The scope** is the channel's reach — the list of agents it **may drive**. For every other resource kind, scope names the agents a resource is delivered *to*; a channel is used by no agent, so its scope is read the other way round. Set it with **Agents it may drive** on the channel's **Overview**: every agent, or only the ones you pick (at least one). To have it drive nothing, switch the channel off.

- An unrestricted scope means every registered agent.
- A restricted scope narrows `/new <agent>` everywhere: the names offered when you type an unknown one, and the check on the name you type.
- The default agent must always be inside the scope. Coffer refuses a scope that excludes the current default agent, and a default agent outside the current scope, naming both by label, so you either widen the scope or change the default first.
- A scope is never empty. A channel that should drive nothing is switched **off**: its adapter does not start, and it can still be edited, for example to fix a wrong token.
- Narrowing the scope drops a thread's sticky agent choice that is no longer allowed; the next conversation uses the default agent.

Like every reach setting, scope and the enabled switch are set per machine and are not synced.

::: warning A channel with nowhere to route does not start
A channel with no default agent, a default agent outside its scope, or a default agent not registered on this machine does not start, and its status says why. Coffer never substitutes another agent.
:::

## The machine a channel runs on

A bot tolerates exactly one consumer: two machines polling one Telegram bot, or holding one SeaTalk app's connection, fight over its messages. So each channel names the one machine that runs it, in `runs_on`. Unlike reach, `runs_on` is part of the channel's configuration and travels with it through [vault sync](/guides/vault-sync), so every machine reads the same answer.

- A channel registered from any Coffer surface is bound to the registering machine.
- Only the named machine starts the adapter. A channel bound to another machine is shown as running elsewhere, not as stopped.
- A channel with no binding, or bound to a machine the registry does not know, runs nowhere and says so on its page.

To move a channel, change **Runs on** on its **Settings** tab, or choose **Run it here…** on a channel another machine runs (it asks first, since both machines may answer until the other syncs).

Rebinding needs no restart. The machine losing the channel stops its adapter within a reconcile tick; the machine gaining it starts one after the next sync round brings the change over. Rebind from the machine that currently runs the channel for a clean handover. Binding a channel to the machine you are on while another machine still runs it can leave both answering until that machine's next sync round.

Your pairing travels with the channel, so moving it does not make you pair again.

## Groups and threads

Add the bot to a group to use it there.

- The bot acts only on a message addressed to it — an @mention, or a reply to the bot. Other group messages are ignored.
- Only the owner can drive it. An addressed message from anyone else gets a short "not authorized" reply and starts no turn; a message from anyone else that is not addressed to the bot (possible when you turned off **Require @mention**) is dropped without a word.
- In the group's main chat, the answer goes into a thread rooted at your message, never into the main chat. Inside a thread, the bot replies in that thread.
- Each thread is its own conversation with its own agent, history and queue, so threads run concurrently.
- A group answer is attached to the message that asked: on Telegram it is sent as a reply to that message; on SeaTalk the thread rooted at that message is the attachment, and the answer @mentions you.
- When you quote a message, the quoted sender and text are folded into the turn as `> sender: …` lines above your text.
- A forwarded chat record is flattened into a `[Forwarded chat record]` block.

Two channel settings tune when the bot answers in a group. They change when the bot answers, never who may drive it.

| Setting | Default | Effect |
| --- | --- | --- |
| `require_mention` | on | The bot stays quiet in a group until someone @mentions it or replies to it. Turned off, it acts on every group message the owner sends. Telegram only: SeaTalk delivers a group message to a bot only when it @mentions the bot. |
| `ignore_other_mentions` | off | A group message that also @mentions another person is left alone, even when it mentions the bot too. |

**Web UI:** on the channel's **Settings** tab, use the switches under **In group chats**: **Answer only when @mentioned** (Telegram channels only) and **Ignore messages that @mention someone else**. They save as you flip them.


### Withdrawing a reply {#withdrawing-a-reply}

A reply the bot has sent can be taken back, by the owner only. Anyone else's tap or command does nothing.

- **`/del`.** Quote one of the bot's messages and send `/del` to withdraw that whole reply, with every part a long reply was split into. Without a quote it withdraws the bot's most recent reply in that chat, or in that thread. It works in direct chats and groups. The `/del` message is itself deleted where the platform allows it (Telegram, if the bot has the right); otherwise it stays.
- **The 🗑 button.** Under every bot reply in a group there is a 🗑 button. Only the owner's tap counts.

How a reply is withdrawn depends on the platform. **Telegram** deletes the message; the platform allows this for 48 hours, and past that the owner is told privately that it can no longer be deleted. **SeaTalk** has no delete API, so group replies are sent as interactive cards, and withdrawing rewrites each card into a neutral “🗑 Withdrawn” card with no buttons; SeaTalk allows rewriting for 7 days, and past that the owner is told privately.

Coffer remembers which platform messages make up each reply, only as long as that window and across daemon restarts, and writes one audit entry per withdrawal: the owner, the channel and the number of messages, never the content.

If the bot is removed from a group, that group's sessions stop. If a SeaTalk group becomes an external group, the bot posts one warning in it.

## Media

Send photos, files, voice messages and other media as you would to a person. Each attachment is downloaded to `~/.coffer/content/channel-media` and handed to the agent in the form it can use:

| You send | The agent receives |
| --- | --- |
| A photo or sticker | Claude Code sees the image. Codex gets the file path. |
| A PDF, office document, epub or rtf | The extracted text, in a `[Document: <name>]` block. If extraction is unavailable, the file path. |
| A voice message or audio | A transcript, when **Speech to text** is on under **Settings › General → Speech to text**. Otherwise the audio file. |
| Any other file | The file path. |
| A location, a contact card | Nothing to download: the bot asks for text, a photo or a file. |

A file larger than the platform lets a bot download is not fetched; the turn text notes it, so the reply acknowledges it. Attachments are stored as references, so a later turn in the same conversation can still reach them. Files in `~/.coffer/content/channel-media` are pruned after the **Attachments** retention window, 30 days after they were last modified by default (see **Settings → Data → Local content**).

::: warning Voice transcription sends audio off your machine
Transcription sends the audio to the transcription provider you configured. It is off until you choose both a transcription provider and a model. A transcription failure never fails the turn; the agent gets the audio file instead.
:::

### Sending files back

The agent sends you a file by writing a line of its own:

```text
MEDIA:/Users/you/reports/q3-chart.png | Q3 revenue by region
```

The line must start with `MEDIA:` followed by an absolute path, optionally with `| caption`. The channel uploads the file into the same chat and thread the turn came from — an image as a photo, anything else as a document — and removes the line from the reply. A path that is missing, relative or over 50 MB is left as text. Ordinary Markdown such as `![chart](chart.png)` is never uploaded. The channel note tells the agent about this syntax, so you can simply ask for the file.

## Notifications

Coffer can push a message to the paired owner with no inbound message, through `POST /api/v1/channels/{uid}/notify`. The request goes to the owner's direct chat unless it names another paired chat, such as a group; a chat the channel is not paired to is refused. On the channel's page, **Send test** sends a test message — editable, **Test message from Coffer** by default — to the owner's direct chat; it starts no turn. Notifying a channel with no paired owner fails and sends nothing.

## Manage channels

The **Channels** page is where a channel is set up and looked after: its setup, connection status and settings. It shows no messages — a channel's conversations are on the [Conversations](/guides/chat) page, and each channel's Overview links there with **Conversations from this channel →**, which opens the list filtered to it (`/conversations?source=<uid>`).

The channel list sits beside the open channel. It groups channels by what they need from you: **Needs attention** (reconnecting, kicked, can't start, not paired, bound to no machine or to one Coffer does not know), **Connected**, **Elsewhere** (run by another machine) and, when there are any, **Off**. **Filter** narrows it by name or platform. A channel is addressed by its uid — `/channels/<uid>` for its **Overview**, `/channels/<uid>/settings` for its **Settings** — so a rename never breaks a link.

The header names the channel, its status and where it runs (`SeaTalk app 8231 · WebSocket · runs on this Mac`), and it looks the same in every state: a **Send test** button and a **⋯** menu holding **Reconnect**. A button that cannot run right now is greyed out, and **Send test** says why when you hover it. Whenever something is wrong, a banner under the header says why and holds the one button that fixes it — **Reconnect now**, **Replace token** or **Replace secret**, **Take it back**, **Retry**, **Open Secrets**, **Run it here**, **Generate pairing code**: lost connection and reconnecting, another process took the SeaTalk connection, the SeaTalk SDK is missing (with **Hand off to &lt;Agent&gt;** to hand the rest over), the platform rejected the token or refused the connection, the channel's secret waiting for your approval (or refused), the status could not be read, the channel is set to run on a Mac outside your sync group, or it is not paired yet. A channel that is off, or that another Mac runs by design, is not a problem, so it gets a quiet grey box instead — **Turn on**, or **Run it here…** (it asks first). Changing the machine, replacing a secret and deleting the channel are in **Settings**. **Reconnect** restarts the channel's adapter: the daemon stops it and its connection, starts them again from the stored configuration and reads the secret as it is now, and a channel that was waiting out a failed start is retried at once. The REST equivalent is `POST /api/v1/channels/{uid}/restart`.

**Overview** is one column, with these sections stacked:

- **Who can use it** — a bordered list of the paired owners, each with when they paired and **Remove**, and **Add owner** below it; an unpaired channel says nobody is paired yet, and the bot ignores every message until you pair.
- **Agents** — **Default agent** and **Default model** (each saved as soon as you pick it) and **Agents it may drive**, the channel's scope (see [Default agent and scope](#default-agent-and-scope)).
- **Conversations from this channel →** — one link to the Conversations page filtered to this channel. The commands the bot answers are not listed here; see [Channel commands](/reference/channel-commands).

**Settings** is one column of sections — **Connection**, **Receiving messages**, **Replies and conversations** and **Working directories** — each setting with its own one-line explanation beneath it, and a **Delete channel** row at the bottom. It saves each change as you make it — a number or a path once you stop typing and it is valid, a switch at once — with no saved line; a save that fails says so in a toast. It holds the channel's title, **In group chats**, **Message batching**, **Replies**, **Conversations**, **Directories** (the folders `/dir` may switch to — each row has **Set as default** and a remove ✕; the default's row reads *default* and has **Unset default**; with no default, new conversations start in Coffer's workspace, shown at the top of the list as *default · Coffer workspace*; a long list scrolls in its box), **Secrets** (the SeaTalk App ID, and the secret or token by its name, linking to its page on the Secrets page, with **Replace key…**), **Runs on** and **Delete…**. Every field starts from the settings the daemon reports for the channel, defaults included. A replaced secret is written under the reference the channel already uses and the daemon notices the new value and restarts the adapter on it by itself — also when you replace it with `coffer secret set` — so rotating a secret changes neither pairing nor binding. Deleting a channel stops the bot and removes its pairing; its conversations stay on the Conversations page.

The channel's page also warns about a setting on the platform that defeats the channel's configuration, such as Telegram privacy mode. To rotate a secret, use **Replace key…** under **Secrets** on the **Settings** tab: **Enter a new value** overwrites the secret the channel already uses, **Use another secret** points the channel at another stored secret (the adapter restarts on it as well).

### A channel that waits for approval

A channel does not start until its bot token or app secret is approved for it (see [Secrets](/guides/secrets#approvals)). That is the normal state after you change which app a channel uses. The channel's banner says its secret **waits for your approval in the Coffer app**, and the Overview lists it the same way; its pairing and settings are kept, and it is not a revoked token, so **Replace secret** is not the fix. Open the **Secrets** page in the Coffer app and approve it; the channel starts on its next attempt, with no restart. If you rejected the approval, the secret stays withheld until the channel's destination changes; the Secrets page keeps no list of refused changes and offers no "Ask again".

## Security

Owner pairing is the security boundary for everything a channel can do.

- **Only the paired owner drives agents.** Coffer checks both the chat and the sender's platform identity — Telegram's user id, SeaTalk's employee code — so another member of a paired group cannot drive a turn.
- **Strangers get silence.** A message from anyone who is not the owner produces no reply and no turn in a direct chat, so the bot does not reveal that it is running. In a group, an addressed message from a non-owner gets a short refusal.
- **A tap is checked like a message.** A button on a selection card never pairs and never switches anything for a non-owner.
- **Group replies are not filtered.** See [Group privacy](#group-privacy).
- **Agents run with full permissions.** There is no approval step for tool calls. Anyone who can pair the bot can make an agent act on your machine, so treat a pairing code like a password and generate it only when you are about to use it.
- **Secrets stay in the vault.** The channel configuration holds only secret references; Coffer refuses a value that looks like a raw secret in a reference field.
- **Nothing is exposed to the network.** Telegram is polled and SeaTalk is an outbound websocket; neither opens a port or needs a public URL.

Pairing codes issued and claimed are written to the audit log, together with the channel's lifecycle changes and each withdrawal of a reply. Messages, notifications and turns are not; the conversation is their record.

### Group privacy {#group-privacy}

In a group turn the agent can still read your memory, knowledge and files, as it can in a direct chat, and everyone in the group reads its reply. On SeaTalk the platform cannot recall a group reply. Coffer does not scan or filter reply content: it looks for no secrets, personal data or overlap with your memory. Your safeguard is deleting a reply you do not want to stay, with `/del` or the 🗑 button.

An agent that is tricked by a group member can still say something private. If you need a stronger guarantee, do not pair the bot with a group that contains people you do not trust.

## How it works

The channel layer meets the agents only at the turn platform's seams — conversation creation and the turn event stream — so a new channel type is one adapter and touches no agent code, and a new agent is reachable from every channel with no channel change. Each adapter declares its capabilities (live text, edits, buttons, reactions, media), and the core chooses how to render a reply from those declarations, never from the platform's name. See [Chat and turns](/architecture/chat).

## Related

- [Telegram setup](/guides/channels-telegram)
- [SeaTalk setup](/guides/channels-seatalk)
- [Conversations](/guides/chat) — the same conversations in the browser.
- [Secret store](/guides/secret-store) — where channel secrets live.
- [Vault sync](/guides/vault-sync) — how a channel's binding and pairing travel between machines.
- [Security model](/architecture/security)
- [Spec: channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md)
- [Channel Adapter Framework](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md), [Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-attachments.md)
