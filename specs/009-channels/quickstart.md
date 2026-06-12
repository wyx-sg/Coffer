# Quickstart: 009 — Channels

> 中文版: [quickstart.zh.md](./quickstart.zh.md)

Talk to your Coffer agents from Telegram or SeaTalk, approve tool calls with
a tap, and let Coffer push notifications to you.

## Telegram

### 1. Create a bot

Open [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, follow
the prompts, and copy the bot token.

### 2. Store the token and register the channel

UI: **Channels → Add channel → Telegram**, paste the token, name the channel
(for example `my-telegram`). The dialog stores the token in the credential
store and registers the channel in one step.

CLI equivalent:

```bash
coffer keychain set channel/my-telegram/bot-token     # paste token at prompt
coffer channel register my-telegram --type telegram \
  --bot-token-ref channel/my-telegram/bot-token
```

### 3. Pair your account

```bash
coffer channel pair my-telegram        # prints an 8-character code
```

(or click **Pair** on the channel's page). Open your bot in Telegram and send
the code as a message. The bot confirms; you are now the channel's owner.
Messages from anyone else are ignored silently.

### 4. Chat

Send any message — it lands in a conversation with the channel's default
agent (the built-in Coffer Assistant unless configured otherwise) and the
reply comes back to Telegram. The same conversation is visible on the Chat
page.

Commands: `/new` fresh conversation · `/stop` interrupt the running turn ·
`/status` what's active · `/help`.

## SeaTalk

### 1. Create the app

On the [SeaTalk Open Platform](https://open.seatalk.io/), create an app,
enable the **Bot** capability and set it Online, and request the scopes your
admin must approve (at minimum *Send Message to Bot User*). Note the
**App ID**, **App Secret**, and the Event Callback **Signing Secret**.

### 2. Register the channel

UI: **Channels → Add channel → SeaTalk**, fill App ID and paste both secrets.

CLI equivalent:

```bash
coffer keychain set channel/st/app-secret
coffer keychain set channel/st/signing-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --signing-secret-ref channel/st/signing-secret
```

### 3. Expose the callback listener

While a SeaTalk channel is enabled, Coffer runs a small callback listener on
`127.0.0.1:8787` (override with `COFFER_CALLBACK_PORT`). Point a tunnel at it:

```bash
cloudflared tunnel --url http://127.0.0.1:8787
# or: ngrok http 8787
```

Copy the public URL and set the app's **Event Callback URL** to
`<public-url>/seatalk/my-seatalk` on the Open Platform. SeaTalk sends a
verification challenge; the listener answers it automatically — the portal
shows the URL as verified. `coffer channel status my-seatalk` shows the
exact port and path at any time.

### 4. Pair and chat

Same as Telegram: `coffer channel pair my-seatalk`, send the code to the bot
in SeaTalk, then just talk. Tool-approval prompts arrive as interactive
cards; replies render SeaTalk Markdown.

## Notifications

Push a message to a paired channel any time — no inbound message needed:

```bash
coffer channel notify my-telegram "nightly build finished ✅"
```

REST: `POST /api/v1/channels/my-telegram/notify {"text": "..."}`.

## Day-to-day

- **Disable** a channel to stop its traffic instantly (polling halts, events
  are refused); **enable** to resume. The adapter state shows in
  `coffer channel status` and on the Channels page.
- **Re-pair** by issuing a new code and sending it from the new account — the
  old binding is replaced.
- **Delete** the channel to remove everything; past conversations remain in
  Chat history.
