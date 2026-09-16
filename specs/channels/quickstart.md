# Quickstart: Channels

Talk to your Coffer agents from Telegram or SeaTalk, and let Coffer push
notifications to you. What each platform can and cannot do is specified in its
own child spec ([`channels/telegram`](./telegram/spec.md),
[`channels/seatalk`](./seatalk/spec.md)); this page is the one set of steps
that gets either of them working.

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
coffer credentials set channel/my-telegram/bot-token     # paste token at prompt
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
agent (a Coffer-managed agent such as Claude Code or Codex) and the
reply comes back to Telegram. The same conversation is visible on the Chat
page (spec `chat`).

> Per [Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md),
> channels route to managed agents only; the built-in "Coffer Assistant" is no
> longer a chat target.

Commands: `/new` fresh conversation · `/stop` interrupt the running turn ·
`/status` what's active · `/agent` switch agent · `/model` switch model ·
`/effort` switch reasoning level · `/save` file the document you just sent into
a knowledge collection · `/help`. `/help` is rendered from the same roster the
bot registers its menu from, so it can never fall behind.

## SeaTalk

SeaTalk can deliver events to a bot two ways, and the platform lets each bot use
**one at a time**. Decide which before you register the channel — the choice
lives both on the channel (`delivery`) and on the app in SeaTalk's Developer
Portal, and the two must agree.

- **WebSocket** — Coffer opens one outbound connection to SeaTalk and events
  arrive on it. Nothing is exposed: no public URL, no tunnel, no signing secret.
  It needs SeaTalk's own client library on this machine (step 2a), which Coffer
  does not ship.
- **Webhook** — SeaTalk POSTs each event to a public URL you own, which means a
  signing secret plus something that carries the public internet to Coffer's
  local listener: a tunnel you run, or one Coffer runs for you (step 2b).

### 1. Create the app

On the [SeaTalk Open Platform](https://open.seatalk.io/), create an app,
enable the **Bot** capability and set it Online, and request the scopes your
admin must approve (at minimum _Send Message to Bot User_). Note the
**App ID** and **App Secret**. If you are taking the webhook path, note the
Event Callback **Signing Secret** too; on the websocket path there is none.

### 2a. WebSocket delivery

Put SeaTalk's official Python SDK where Coffer looks for it. It is distributed
from SeaTalk's own portal and is not on PyPI, so Coffer never bundles or depends
on it — you supply it:

```bash
mkdir -p ~/.coffer/vendor
# unpack the official SDK so that ~/.coffer/vendor/seatalk_oapi_sdk/ exists
# keep it elsewhere? point COFFER_SEATALK_SDK_DIR at that directory instead
```

Register the channel — no signing secret, no public URL, no tunnel token:

```bash
coffer credentials set channel/st/app-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret --delivery websocket
```

UI: **Channels → Add channel → SeaTalk**, choose **WebSocket**, fill App ID and
paste the app secret.

Then switch the app's event delivery to **WebSocket** in the Developer Portal.
Enable the channel in Coffer first: the portal's **Re-verify** only passes while
the connection is actually live, so verify once the channel is up.

Where to read the connection's state: every surface says it. The channel's page
in the web UI names it in words — `connecting`, `connected`, `kicked`,
`sdk_missing`, or `error` with the last error text — `coffer channel status
my-seatalk --json` carries the same two fields, `websocket_state` and
`websocket_error`, and the plain-text `coffer channel status my-seatalk` prints

```
inbound:  websocket (connected)
```

with a verbatim `ws error:` line when there is one. On a websocket channel it
prints no listener port, no path and no tunnel line: those are the webhook
path's facts, and spec channels/seatalk FR-005 requires the absent ones to read
as absent rather than as a zero rendered like an address.

Two things to know about this path. **One connection per SeaTalk app**: if the
same app is registered from somewhere else — a second machine, a colleague
testing — that registration takes the events and this one is kicked. Coffer
reports `kicked` and retries slowly rather than fighting for the socket, so stop
the other holder if it was not deliberate. And **events pause while the
connection is down**: there is no public endpoint queuing them up for you.

If the SDK is missing, the channel does not start and says so — naming the
directory it searched — while the daemon and every other channel keep running.

### 2b. Webhook delivery

Register the channel with the signing secret:

```bash
coffer credentials set channel/st/app-secret
coffer credentials set channel/st/signing-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --signing-secret-ref channel/st/signing-secret
```

UI: **Channels → Add channel → SeaTalk**, leave delivery on **Webhook**, fill
App ID and paste both secrets.

While a webhook-delivery SeaTalk channel is enabled, Coffer runs a small callback
listener on `127.0.0.1:8787` (override with `COFFER_CALLBACK_PORT`). The listener
is loopback-only, so something must bridge the internet to it. Either run the
tunnel yourself:

```bash
cloudflared tunnel --url http://127.0.0.1:8787
# or: ngrok http 8787
```

…or let Coffer supervise one for you: create a Cloudflare **named tunnel**, then
on **Channels → my-seatalk → Edit channel** paste its connector token and the
public base URL the tunnel answers on (`https://seatalk.example.com`). The token
goes into the credential store and the channel records only the reference, and
Coffer then keeps a `cloudflared` child alive for exactly as long as the channel
is enabled, restarting it if it dies. The channel's status card shows whether the
managed tunnel is up.

Either way, set the app's **Event Callback URL** to
`<public-url>/seatalk/my-seatalk` on the Open Platform. SeaTalk sends a
verification challenge; the listener answers it automatically — the portal shows
the URL as verified. `coffer channel status my-seatalk` prints the whole chain:

```
inbound:  webhook 127.0.0.1:8790/seatalk/my-seatalk (listener up)
tunnel:   managed (up)
register: https://<public-host>/seatalk/my-seatalk
```

The tunnel line reads `not managed by Coffer` when you front the callback
yourself, which is a choice rather than a fault. The same facts are on the
channel's page and in `--json` as `tunnel_managed` and `tunnel_running`.

### 3. Pair and chat

Same as Telegram, and identical on both delivery methods:
`coffer channel pair my-seatalk`, send the code to the bot in SeaTalk, then just
talk. Replies render SeaTalk Markdown.

### Switching delivery later

Change it in both places, in the same sitting. Coffer drops the fields the other
method owns when you switch — a websocket channel keeps no signing secret, public
URL or tunnel token, and a webhook channel needs its signing secret back — so the
switch is never a one-sided edit. Going to webhook, set the callback URL in the
portal; going to websocket, switch the portal to WebSocket and Re-verify while
Coffer holds the connection.

## Notifications

Push a message to a paired channel any time — no inbound message needed:

```bash
coffer channel notify my-telegram "nightly build finished ✅"
```

REST: `POST /api/v1/channels/my-telegram/notify {"text": "..."}`.

UI: the channel detail page has a **Send test message** card — type a line and
push it to the paired peer (the natural way to confirm delivery right after
pairing). It stays disabled until the channel is paired.

## Day-to-day

- **Edit** a channel from its detail page (**Edit channel**): change the bound
  agent, or rotate a secret (Telegram bot token / SeaTalk app secret +
  signing secret). A rotated secret is written back to the same credential
  reference, so the binding and pairing are untouched; leave a secret field
  blank to keep the current value.
- **Disable** a channel to stop its traffic instantly (polling halts, events
  are refused); **enable** to resume. The adapter state shows in
  `coffer channel status` and on the Channels page.
- **Re-pair** by issuing a new code and sending it from the new account — the
  old binding is replaced.
- **Delete** the channel to remove everything; past conversations stay in Chat
  history until the retention policy prunes them.

## Moving a channel to another machine

If your vault converges with a sync remote, a channel shows up on every machine
— and runs on exactly one of them, the one named in its **Runs on** column.
Registering a channel binds it to the machine you registered it from, so this
only comes up when you want to move one.

```bash
coffer channel bind my-telegram              # run it here
coffer channel bind my-telegram <machine-id> # run it there (coffer sync machine list names them)
```

or pick the machine in the **Runs on** column, or on the channel's page.

No restart. The machine giving the channel up stops within a couple of seconds;
the machine taking it over starts after the next sync round brings the change
across. Do the rebind **from the machine that currently runs the channel** and
the handover has no overlap — bind a channel to the machine you are sitting at
while another still holds it and both may answer until that machine's next
round.

Two things to know:

- A channel bound to a machine that has been retired runs nowhere, and says so.
  Bind it to a live one.
- **Runs on** is not **Reach**. Reach says which agents a channel may drive and
  is set separately on each machine; the binding says which machine runs the
  adapter, and is the same everywhere.
