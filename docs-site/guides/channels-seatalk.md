---
title: SeaTalk
description: Set up a SeaTalk channel for Coffer — create a SeaTalk Open Platform app, supply the WebSocket SDK, register and pair the channel, and use it in direct chats, groups and threads.
---

# SeaTalk

This guide sets up a SeaTalk channel: create a bot app on the SeaTalk Open Platform, supply SeaTalk's WebSocket SDK, register the channel in Coffer, switch the app to WebSocket delivery, and pair your account. It then covers groups, threads, quoted messages, cards, limits and troubleshooting. For what every channel shares — commands, scope, security — see [Channels](/guides/channels).

No agent has an official SeaTalk integration, so everything you do with an agent in SeaTalk goes through this channel.

## How SeaTalk connects

Coffer receives SeaTalk events over **one outbound WebSocket connection per channel**. The daemon dials out to SeaTalk, authenticates with the app's ID and secret, and SeaTalk pushes events down that connection. Nothing is exposed: there is no public URL, no listening port, no tunnel and no signature to verify. Replies and notifications go out over HTTPS to `openapi.seatalk.io`.

Two consequences follow:

- **The WebSocket client is SeaTalk's own SDK, and you supply it.** It is distributed from SeaTalk's portal, is not on public PyPI and carries no public licence, so Coffer cannot ship or depend on it. Without it, a SeaTalk channel can send but receives nothing.
- **One connection per SeaTalk app.** A second process registering the same app — another machine, a colleague testing — takes the connection away. Register a SeaTalk app as a channel on one machine only.

## Prerequisites

- A running daemon and at least one registered agent. See [Quickstart](/start/quickstart).
- Access to the [SeaTalk Open Platform](https://open.seatalk.io/) with permission to create an app, and whatever approval your organisation requires for its scopes.

## 1. Create the SeaTalk app

1. On the SeaTalk Open Platform, create an app.
2. Enable the **Bot** capability and set the bot **Online**.
3. Request the scopes the bot needs. At minimum you need *Send Message to Bot User*; your organisation's admin may have to approve them. Add *Get Employee Profile* if you want the channel's owner list to show each owner's SeaTalk picture; without it the list shows their initials.
4. Note the app's **App ID** and **App Secret**.

Leave the event delivery setting for step 4: SeaTalk only verifies WebSocket delivery while Coffer holds the connection.

## 2. Supply the WebSocket SDK

1. Download SeaTalk's Python SDK for WebSocket event callbacks from the SeaTalk Open Platform. The package is `seatalk_oapi_sdk`; see SeaTalk's [WebSocket Event Callback](https://open.seatalk.io/docs/WebSocket-Event-Callback) documentation. The download stays with you, because it sits behind the platform's sign-in.
2. Hand the rest to your agent. Once the channel is registered (step 3), a channel waiting for the SDK reads **SeaTalk's Python SDK isn't installed**, links SeaTalk's download page and offers **Hand off to &lt;Agent&gt;** (its menu copies the prompt; with no Coffer-managed agent available only **Copy prompt** is offered): a prompt that has your agent unpack the archive into Coffer's vendor directory. Press **Retry** once it is in place.

The SDK is loaded by `coffer-seatalk-bridge`, a separate program that sits beside the daemon and has no access to the master key. The daemon never imports the SDK: that directory is one your agent can write to, and code placed there must not run where the key is readable. The daemon starts the bridge when a SeaTalk channel starts, gives it the app ID and app secret on its standard input, and reads the channel's events back from it. It keeps retrying while the SDK is missing. You can add the SDK before or after registering the channel; a channel that is already waiting picks it up without a daemon restart.

To do it by hand instead, unpack the archive so that the package directory sits inside Coffer's vendor directory:

```text
~/.coffer/vendor/seatalk_oapi_sdk/
```

To keep it somewhere else, set `COFFER_SEATALK_SDK_DIR` to the directory that **contains** `seatalk_oapi_sdk/`, in the environment the daemon starts from.

## 3. Register the channel

```text [Web UI]
Channels → Add channel
  1 Platform:       SeaTalk
  2 Connect:
      Name:           my-seatalk
      Default agent:  claude-code
      App ID:         <APP_ID>
      App secret:     <APP_SECRET>
    → Connect
  3 Pair:           Pair later (pair in step 5)
```

The configuration is the App ID and a reference to the App Secret, plus the fields every channel has. The channel is held on this machine only and starts connecting immediately.

Check the connection: the channel's header reads *WebSocket connected* when it is up (its state stays **Not paired** until step 5). Wait for it before the next step.

## 4. Switch the app to WebSocket delivery

1. In SeaTalk's Developer Portal, open the app's event callback settings and set delivery to **WebSocket**. SeaTalk allows one delivery method per bot.
2. Press **Re-verify**. It passes only while Coffer holds the live connection, which is why the channel is registered first.

## 5. Pair your account

1. On the channel's **Overview** choose **Generate pairing code**.
2. In SeaTalk, open a direct chat with the bot and send the eight-character code.
3. The bot confirms and sends the help card once. SeaTalk has no command menu, so this card is how the bot shows what it accepts; send `/help` to see it again.

SeaTalk has no start links, so you type the code. It is single-use, expires after one hour, and is invalidated after 10 wrong guesses.

Send the bot a message. A typing indicator appears at once, the answer arrives as a new message when the turn ends, and the conversation shows up on the web [Conversations](/guides/chat) page with the channel `SeaTalk · DM`.

## Connection states

The channel's header reports the connection: its state word, and the meta line (`SeaTalk app <id> · WebSocket`). Over REST, the fields are `status.inbound.websocket_state` and `status.inbound.websocket_error`.

| State | Shown on the channel's page | Meaning |
| --- | --- | --- |
| `connecting` | **Connecting** — Connecting… (**Reconnecting** — Reconnecting… after a failed attempt) | Registering with SeaTalk. |
| `connected` | **Connected** | Events are flowing. |
| `kicked` | **Kicked** — Another process took the connection | Another process registered the same app. Coffer waits 60 seconds before trying again rather than fighting for the connection. |
| `sdk_missing` | **Can't start** — SeaTalk SDK not found | The bridge could not import `seatalk_oapi_sdk`. The error names the directory searched. |
| `rejected` | **Token rejected** — Connection refused | SeaTalk refused the app at the register handshake: the App ID is wrong, or the App Secret was regenerated on the SeaTalk Open Platform. The banner offers **Replace secret**; `websocket_error` holds SeaTalk's answer verbatim. Coffer keeps retrying, so a secret replaced under the same reference recovers by itself. |
| `error` | **Network problem** — Can't reach the platform — retrying | The last attempt failed on the way (a DNS failure, a timeout, a dropped socket), not because SeaTalk refused the app; `websocket_error` holds the error verbatim. Coffer retries with a backoff from 1 to 30 seconds, and the banner offers **Reconnect now**, never a new secret. |

Before the first attempt there is no connection state: the daemon starts a channel within about two seconds of it being switched on, and until then `status.starting` is true and the page shows **Connecting**, never a failure. Events that SeaTalk sends while the connection is down are not queued anywhere by Coffer.

## How replies look

- **While the turn runs** — SeaTalk has no reactions and cannot edit a text message, so the only sign of work is the typing indicator. It appears at once and is kept alive every 3 seconds until the reply is sent, in direct chats and group threads alike. SeaTalk silently skips group typing in groups of more than 200 members.
- **Direct chats** — the answer arrives as one ordinary new message, so SeaTalk notifies you the way it does for any message. Only what the agent writes after its last tool call is sent; its earlier remarks between steps are not. A long answer is split at paragraph boundaries into several messages, and every message after the first is numbered `(2/3)`, `(3/3)`.
- **Groups** — the finished answer arrives as one interactive card, split into several cards if it is long, and it opens by @mentioning whoever asked. Cards are used because SeaTalk can rewrite a card but cannot delete or edit anything else, and that is what lets the owner withdraw a group reply (see below). Each card carries a 🗑 button.
- **Formatting** — the agent's Markdown is converted to SeaTalk Markdown: bold, italic, inline code, code fences and lists. Headings become bold and links become `label (url)`, since SeaTalk supports neither. A table becomes one bullet per row (a big one also arrives as a `.csv`), and a code block over 30 lines arrives as a file. Messages are split to stay under SeaTalk's 4,096-byte cap.
- **Long sections** — SeaTalk cannot collapse text, so the answer arrives whole, including any section the agent puts under a heading such as `## Details`.
- **Withdrawing a reply.** SeaTalk's Open Platform has no API to delete a bot's message, and only interactive cards can be rewritten, and only by the bot that sent them. So when the owner withdraws a group reply — by tapping its 🗑 button, or by quoting it and sending `/del` — Coffer rewrites each card of that reply into a neutral “🗑 Withdrawn” card with no buttons. The text is gone from the chat, but the card stays. SeaTalk allows rewriting for 7 days; past that the owner is told privately that the reply can no longer be withdrawn. Only the owner's tap or command counts, and `/del` without a quote withdraws the most recent reply in the group or thread. A direct-chat reply is an ordinary message and cannot be withdrawn on SeaTalk. See [Withdrawing a reply](/guides/channels#withdrawing-a-reply).

## Groups and threads

1. Add the bot to the group.
2. @mention it. SeaTalk delivers only @mentions to a bot; other group messages never reach Coffer.
3. The owner's first @mention registers the group as a peer of the channel. A mention from anyone else gets a short "not authorized" reply.

Where the answer goes:

- **@mention in the group's main chat** — the bot starts a thread rooted at your message and answers there. It reads no history: the thread holds only your message.
- **@mention inside a thread** — the bot reads the thread and answers in it. The first time a conversation answers in a thread, its turn carries the thread's 20 most recent messages, with their images and files. Each later turn of that conversation in the thread carries only what others posted since its previous turn there — nothing when nothing is new — because the agent's session already holds the rest. When older messages are left out, a note at the end of the thread block says how many, and the agent can read them page by page with the `coffer__channel_read_thread` tool. `/new` in the thread starts again from the 20 most recent.
- **A thread in a direct chat** — read and answered in the same way. A reply-in-thread under any message in your direct chat stays in the direct chat's conversation, with its context; only a thread opened with `/thread` is a separate conversation. `/thread` makes your own `/thread` message the thread's root: the bot answers inside that thread with a message marked `🧵#N title`, and you keep talking in the same thread. (From a `/thread` button, or sent inside a thread, there is no message to root it at, so the bot posts the marked message itself and you reply under that.)

**What the bot can read of a thread is bounded by SeaTalk, not by Coffer.** SeaTalk returns only replies sent in the **last 7 days**; an older thread comes back as its root message plus whatever is recent, however long it looks in the app. Whisper messages and deleted messages are never returned. Replies sent before the bot joined a group are limited by the group's "Chat history for new members" setting at the time it joined. When a thread is older than that window, Coffer says so in the turn's context, and the read tool says it too, so the agent tells you what it could not see instead of guessing. Forward or quote the missing messages to bring them in.

Each group thread is its own conversation, so you can run Claude Code in one thread and Codex in another. A group answer opens by @mentioning you, so SeaTalk notifies you.

Because a main-chat @mention always roots a new thread, `@bot /new <agent>` in the main chat sets the **group's default agent**, which every new thread in the group starts on, and `@bot /stop` stops every turn running in the group. `/del` withdraws a reply, as described under [How replies look](#how-replies-look). `/model`, `/dir`, `/status`, `/resume` and `/thread` work only in a direct chat; sent in a group they get one private line saying so. Inside a group thread, `/new` and `/stop` apply to that thread. See [Group defaults on SeaTalk](/reference/channel-commands#group-defaults-on-seatalk).

To have the bot leave alone a message that also @mentions another person, turn on **Ignore messages that @mention someone else** on the channel's **Settings** tab under **Receiving messages**. SeaTalk has no **Answer only when @mentioned** switch: it already delivers only @mentions.

The bot never reads recent messages from a group's main chat. SeaTalk does not grant that permission to a self-built app, and the message you address to the bot is meant to carry what it needs.

### Quoted messages

When you reply by quoting a message, Coffer looks the quoted message up with the bot's own secrets and folds it into the turn as `> sender: …` lines above your text, with its images and files attached. SeaTalk gives a message a different id for each app, so only the bot that received the quote can resolve it; the agent's own tools could not. If the lookup fails, the turn runs on your message alone.

### Forwarded chat history

A forwarded chat record is flattened into a `[Forwarded chat record]` block, one line per message. Images inside it, including records forwarded inside other records, are downloaded and attached, so a vision agent sees the pictures rather than links it cannot open.

### Group events

If the bot is removed from a group or the group is disbanded, that group's sessions stop. If a group is converted to an external group — so people from other organisations can read it — the bot posts one warning in the group. The channel keeps working.

## Cards

In a direct chat a bare `/model`, `/dir` or `/resume` answers with an interactive card, and `/status` carries **New**, **Model**, **Resume** and **Dir** buttons (and **Stop** while a turn runs). `/help` carries a button for every command the chat may use (paged), nine in a direct chat and the four group commands in a group; `/new` carries **Agent**, **Model** and **Dir** in a direct chat and only **Agent** in a group. A tap on one of those does exactly what typing the command does. A question the agent asks arrives as a card too, with one button per option on its own line (multi-select options toggle a `✓`, and **Submit** sends); a tap or a typed reply is the answer, and the card is rewritten to `✓ Answered: …` afterwards.

- Buttons are laid out in up to three rows. Short labels share a row; a long one such as "Claude Code" gets its own.
- A card has at most six buttons; longer lists page with **← Prev** and **Next →**.
- After you tap a choice, the card is rewritten so its tick moves. SeaTalk allows this only for interactive cards the same bot sent in the last 7 days. For an older card, the choice still applies; a page turn arrives as a new card instead.
- Titles are cut at 120 characters and descriptions at 1,000.

## Media

Everything SeaTalk can attach drives a turn: images, files and documents, video, and voice or audio. Coffer downloads each one with the app's token, since SeaTalk file links require authentication.

- Documents are extracted to text for the agent.
- Voice is transcribed when speech to text is on (**Settings › General → Speech to text**); otherwise the agent gets the audio file.
- A file keeps its real filename.

The agent sends a file back with a `MEDIA:/absolute/path` line. It arrives as an image or file message in the same chat and thread, with any caption as a following message. See [Channels → Sending files back](/guides/channels#sending-files-back).

## Rotate the app secret

On the channel's page choose **Replace secret** in the banner when SeaTalk rejected the old one, or **Replace key…** under **Settings** → **Connection**; paste the secret in **App secret** and choose **Replace and restart**. Coffer checks the App ID and secret with SeaTalk as you paste, and a secret SeaTalk rejects is named under the field. The secret is written under the channel's existing reference, so the pairing is unchanged. Under **Settings** → **Connection** the App Secret shows as the secret's name, linking to its page, with **Replace key…** beside it; **Use another secret** there points the channel at a different stored secret and restarts the adapter on it. The **App ID** is edited in place under **Settings** → **Connection**.

## Limits

| Limit | Value |
| --- | --- |
| Ordinary message | under 4,096 bytes |
| Card rewrite window | 7 days, interactive cards only |
| Card content | 6 buttons in up to 3 rows; title 120 characters, description 1,000 |
| Thread pages | 100 messages per page, bounded page count |
| Thread history | Replies from the last 7 days only; no whispers or deleted messages |
| Withdrawing a bot message | No delete API; a group reply card is rewritten to “🗑 Withdrawn” within 7 days |
| Connections per app | 1 |

## Troubleshooting

**The state is `sdk_missing`.**
Check that `~/.coffer/vendor/seatalk_oapi_sdk/` exists (or `$COFFER_SEATALK_SDK_DIR/seatalk_oapi_sdk/`), and that `COFFER_SEATALK_SDK_DIR`, if you use it, is set where the daemon starts — not only in your current shell. The bridge reads it from the daemon's environment. Replies and notifications still work meanwhile.

**The state is `kicked`.**
Another process holds this app's connection. Common causes: the same app registered as a channel on a second machine, or a test script using the same App ID. Stop the other one; Coffer reconnects within about a minute. To move the channel between machines, see [Using the bot on another machine](/guides/channels#using-the-bot-on-another-machine).

**Re-verify fails in the Developer Portal.**
The channel is not connected yet. Wait until the channel's header reads *WebSocket connected*, then press **Re-verify** again.

**`connected`, but the bot never answers.**
Check pairing (a channel that shows **Not paired** answers nobody), and that you @mentioned it in a group. Then check that the portal's delivery is set to WebSocket; with another delivery method, SeaTalk sends events somewhere else.

**The bot says it can only see a few messages of a thread.**
SeaTalk returns only the last 7 days of a thread's replies (see [Groups and threads](#groups-and-threads)), so an older discussion is invisible to the bot even though you can scroll to it. Forward or quote the older messages to give the agent that context. Within the window, a turn carries only the thread's latest messages; ask the agent to read further back and it uses `coffer__channel_read_thread`.

## Related

- [Channels](/guides/channels) — commands, scope and security for every channel.
- [Telegram](/guides/channels-telegram)
- [Secret store](/guides/secret-store)
- [Spec: channels/seatalk](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/seatalk/spec.md)
- [SeaTalk Inbound Over WebSocket](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md)
