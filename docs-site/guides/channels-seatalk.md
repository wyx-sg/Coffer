---
title: SeaTalk
description: Set up a SeaTalk channel for Coffer — create a SeaTalk Open Platform app, supply the WebSocket SDK, register and pair the channel, and use it in direct chats, groups and threads.
---

# SeaTalk

This guide sets up a SeaTalk channel: create a bot app on the SeaTalk Open Platform, supply SeaTalk's WebSocket SDK, register the channel in Coffer, switch the app to WebSocket delivery, and pair your account. It then covers groups, threads, quoted messages, cards, limits and troubleshooting. For what every channel shares — commands, scope, machine binding, security — see [Channels](/guides/channels).

No agent has an official SeaTalk integration, so everything you do with an agent in SeaTalk goes through this channel.

## How SeaTalk connects

Coffer receives SeaTalk events over **one outbound WebSocket connection per channel**. The daemon dials out to SeaTalk, authenticates with the app's ID and secret, and SeaTalk pushes events down that connection. Nothing is exposed: there is no public URL, no listening port, no tunnel and no signature to verify. Replies and notifications go out over HTTPS to `openapi.seatalk.io`.

Two consequences follow:

- **The WebSocket client is SeaTalk's own SDK, and you supply it.** It is distributed from SeaTalk's portal, is not on public PyPI and carries no public licence, so Coffer cannot ship or depend on it. Without it, a SeaTalk channel can send but receives nothing.
- **One connection per SeaTalk app.** A second process registering the same app — another machine, a colleague testing — takes the connection away. Bind each channel to one machine.

## Prerequisites

- A running daemon and at least one registered agent. See [Quickstart](/start/quickstart).
- Access to the [SeaTalk Open Platform](https://open.seatalk.io/) with permission to create an app, and whatever approval your organisation requires for its scopes.

## 1. Create the SeaTalk app

1. On the SeaTalk Open Platform, create an app.
2. Enable the **Bot** capability and set the bot **Online**.
3. Request the scopes the bot needs. At minimum you need *Send Message to Bot User*; your organisation's admin may have to approve them.
4. Note the app's **App ID** and **App Secret**.

Leave the event delivery setting for step 4: SeaTalk only verifies WebSocket delivery while Coffer holds the connection.

## 2. Supply the WebSocket SDK

1. Download SeaTalk's Python SDK for WebSocket event callbacks from the SeaTalk Open Platform. The package is `seatalk_oapi_sdk`; see SeaTalk's [WebSocket Event Callback](https://open.seatalk.io/docs/WebSocket-Event-Callback) documentation.
2. Unpack it so that the package directory sits inside Coffer's vendor directory:

   ```text
   ~/.coffer/vendor/seatalk_oapi_sdk/
   ```

   To keep it somewhere else, set `COFFER_SEATALK_SDK_DIR` to the directory that **contains** `seatalk_oapi_sdk/`, in the environment the daemon starts from.

Coffer imports the SDK only when a SeaTalk channel starts, never at daemon start, and keeps retrying while it is missing. You can add the SDK before or after registering the channel; a channel that is already waiting picks it up without a daemon restart.

## 3. Register the channel

::: code-group

```sh [CLI]
# Paste the App Secret at the prompt; it is read from stdin
coffer credentials set channel/st/app-secret

coffer channel register my-seatalk --type seatalk \
  --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --agent claude-code
```

```text [Web UI]
Channels → Add channel
  Type:           SeaTalk
  Name:           my-seatalk
  App ID:         <APP_ID>
  App secret:     <APP_SECRET>
  Default agent:  claude-code
→ Create
```

:::

The configuration is the App ID and a reference to the App Secret, plus the fields every channel has. The channel is bound to this machine and starts connecting immediately.

Check the connection:

```sh
coffer channel status my-seatalk
```

```text
channel:  my-seatalk (seatalk)
enabled:  True    running: True
runs on:  3f9c… (this machine)
pairing:  no pending code
peer:     not paired
inbound:  websocket (connected)
```

Wait for `connected` before the next step. The channel's page shows the same state on its **SeaTalk connection** card.

## 4. Switch the app to WebSocket delivery

1. In SeaTalk's Developer Portal, open the app's event callback settings and set delivery to **WebSocket**. SeaTalk allows one delivery method per bot.
2. Press **Re-verify**. It passes only while Coffer holds the live connection, which is why the channel is registered first.

## 5. Pair your account

1. On the channel's page choose **Pairing → Generate pairing code**, or run `coffer channel pair my-seatalk`.
2. In SeaTalk, open a direct chat with the bot and send the eight-character code.
3. The bot confirms. You are the channel's owner.

SeaTalk has no start links, so you type the code. It is single-use, expires after one hour, and is invalidated after 10 wrong guesses.

Send the bot a message. A typing indicator appears at once, the reply streams into a single message, and the conversation shows up on the web [Chat](/guides/chat) page marked `via my-seatalk`.

## Connection states

`coffer channel status` and the **SeaTalk connection** card report the connection as the channel's inbound state. With `--json`, the fields are `inbound.websocket_state` and `inbound.websocket_error`.

| State | Card label | Meaning |
| --- | --- | --- |
| `connecting` | Connecting… | Registering with SeaTalk. |
| `connected` | Connected | Events are flowing. |
| `kicked` | Kicked — another process holds this bot's connection | Another process registered the same app. Coffer waits 60 seconds before trying again rather than fighting for the connection. |
| `sdk_missing` | SDK not found | `seatalk_oapi_sdk` could not be imported. The error names the directory searched. |
| `error` | Error | The last attempt failed; the error is shown verbatim. Coffer retries with a backoff from 1 to 30 seconds. |

No state is shown before the first attempt. Events that SeaTalk sends while the connection is down are not queued anywhere by Coffer.

## How replies look

- **Streaming** — the reply is one message that grows while the agent writes, starting the moment the turn begins. Each update carries the full text so far. Coffer re-sends the latest text every 10 seconds on a long tool call, because SeaTalk ends a stream that goes 30 seconds without an update. SeaTalk clients older than 3.67 show the finished message when the stream closes.
- **Long replies** — one stream carries at most 4,096 characters. A longer reply finishes the stream at a paragraph boundary and the rest arrives as ordinary messages.
- **Formatting** — the agent's Markdown is converted to SeaTalk Markdown: bold, italic, inline code, code fences and lists. Headings become bold and links become `label (url)`, since SeaTalk supports neither. Messages are split to stay under SeaTalk's 4,096-byte cap.
- **Receipt** — SeaTalk has no reactions, so a typing indicator is kept alive every 3 seconds while the turn runs, in direct chats and group threads alike. SeaTalk silently skips group typing in groups of more than 200 members.

The keep-alive gives up after about 10 minutes with no new content, so a turn that stays silent that long lets its stream lapse. If a stream is ended by SeaTalk — an error or a gap past 30 seconds — Coffer does not reuse it. The partial message stays in the chat and the full reply is sent as ordinary messages.

## Groups and threads

1. Add the bot to the group.
2. @mention it. SeaTalk delivers only @mentions to a bot; other group messages never reach Coffer.
3. The owner's first @mention registers the group as a peer of the channel. A mention from anyone else gets a short "not authorized" reply.

Where the answer goes:

- **@mention in the group's main chat** — the bot starts a thread rooted at your message and answers there. It reads no history: the thread holds only your message.
- **@mention inside a thread** — the bot reads the whole thread, every page of it, oldest first, downloads the images and files earlier messages carry, and answers in that thread.
- **A thread in a direct chat** — read and answered in the same way.

Each thread is its own conversation, so you can run Claude Code in one thread and Codex in another. A group answer opens by @mentioning you, so SeaTalk notifies you.

To have the bot leave alone a message that also @mentions another person, turn on **Ignore messages that @mention someone else** under **Edit** → **In group chats**, or run `coffer channel set my-seatalk --ignore-other-mentions`. SeaTalk has no **Answer only when @mentioned** switch: it already delivers only @mentions.

The bot never reads recent messages from a group's main chat. SeaTalk does not grant that permission to a self-built app, and the message you address to the bot is meant to carry what it needs.

### Quoted messages

When you reply by quoting a message, Coffer looks the quoted message up with the bot's own credentials and folds it into the turn as `> sender: …` lines above your text, with its images and files attached. SeaTalk gives a message a different id for each app, so only the bot that received the quote can resolve it; the agent's own tools could not. If the lookup fails, the turn runs on your message alone.

### Forwarded chat history

A forwarded chat record is flattened into a `[Forwarded chat record]` block, one line per message. Images inside it, including records forwarded inside other records, are downloaded and attached, so a vision agent sees the pictures rather than links it cannot open.

### Group events

If the bot is removed from a group or the group is disbanded, that group's sessions stop. If a group is converted to an external group — so people from other organisations can read it — the bot posts one warning in the group. The channel keeps working.

## Cards

`/agent`, `/model`, `/effort` and `/save` without an argument answer with an interactive card.

- Buttons are laid out in up to three rows. Short labels share a row; a long one such as "Claude Code" gets its own.
- A card has at most six buttons; longer lists page with **← Prev** and **Next →**.
- After you tap a choice, the card is rewritten so its tick moves. SeaTalk allows this only for interactive cards the same bot sent in the last 7 days. For an older card, the choice still applies; a page turn arrives as a new card instead.
- Titles are cut at 120 characters and descriptions at 1,000.

## Media

Everything SeaTalk can attach drives a turn: images, files and documents, video, and voice or audio. Coffer downloads each one with the app's token, since SeaTalk file links require authentication.

- Documents are extracted to text for the agent.
- Voice is transcribed when speech to text is on (**Settings → Coffer's model**); otherwise the agent gets the audio file.
- A file keeps its real filename.

The agent sends a file back with a `MEDIA:/absolute/path` line. It arrives as an image or file message in the same chat and thread, with any caption as a following message. See [Channels → Sending files back](/guides/channels#sending-files-back).

## Rotate the app secret

On the channel's page choose **Edit**, enter **New app secret** and **Save changes**. The secret is written under the channel's existing reference, so pairing and machine binding are unchanged. The **App ID** can be changed in the same dialog.

## Limits

| Limit | Value |
| --- | --- |
| Streamed reply | 4,096 characters per stream; the rest as ordinary messages |
| Ordinary message | under 4,096 bytes |
| Stream idle limit | 30 seconds (Coffer re-sends every 10) |
| Card rewrite window | 7 days, interactive cards only |
| Card content | 6 buttons in up to 3 rows; title 120 characters, description 1,000 |
| Thread pages | 100 messages per page, bounded page count |
| Connections per app | 1 |

## Troubleshooting

**The state is `sdk_missing`.**
Check that `~/.coffer/vendor/seatalk_oapi_sdk/` exists (or `$COFFER_SEATALK_SDK_DIR/seatalk_oapi_sdk/`), and that `COFFER_SEATALK_SDK_DIR`, if you use it, is set where the daemon starts — not only in your current shell. Replies and notifications still work meanwhile.

**The state is `kicked`.**
Another process holds this app's connection. Common causes: the same app registered as a channel on a second machine, or a test script using the same App ID. Stop the other one; Coffer reconnects within about a minute. To move the channel between machines, use `coffer channel bind` from the machine that currently runs it.

**Re-verify fails in the Developer Portal.**
The channel is not connected yet. Wait until `coffer channel status` shows `connected`, then press **Re-verify** again.

**`connected`, but the bot never answers.**
Check pairing (`peer: not paired` means the bot answers nobody), and that you @mentioned it in a group. Then check that the portal's delivery is set to WebSocket; with another delivery method, SeaTalk sends events somewhere else.

**The streamed reply stops midway and the answer arrives again below it.**
SeaTalk ended the stream. The full answer is the one sent below.

## Related

- [Channels](/guides/channels) — commands, scope, machine binding and security for every channel.
- [Telegram](/guides/channels-telegram)
- [Credentials](/guides/credentials)
- [Spec: channels/seatalk](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/seatalk/spec.md)
- [SeaTalk Inbound Over WebSocket](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md)
