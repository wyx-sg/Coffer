# Channels

A **channel** lets you reach your Coffer agents from a messaging app — **Telegram** or **SeaTalk**. Pair the channel to your own account, then chat with an agent and receive notifications Coffer pushes you, all from inside the IM chat. A channel drives the managed agents (Claude Code, Codex); the conversation it starts is the same one the app's **Chat** page shows.

## Register a channel

Store the bot secret in the credential store first, then register the channel with **references** to it (never the secret itself):

```bash
coffer credentials set tg-bot-token                          # paste the token at the prompt
coffer channel register mybot --type telegram --bot-token-ref tg-bot-token --agent claude-code
coffer channel pair mybot                                    # → an 8-char, single-use pairing code
coffer channel status mybot                                  # adapter state + paired peer
```

- Telegram needs `--bot-token-ref`; SeaTalk needs `--app-id --app-secret-ref`, plus `--signing-secret-ref` on webhook delivery or `--delivery websocket` for the outbound-connection transport. `--agent` (required) names the agent that answers by default; `--agent-config` takes that agent's default settings as JSON.
- **Pairing is the security boundary.** Coffer is single-user: send the code to the bot from your own account to become its sole owner. Anyone else is ignored silently. A code is valid for one hour and works once; issuing a new one and sending it from another account replaces the owner.

The **Channels** page does the same without the terminal: **Add channel** stores the secret and registers the channel in one step, and **Pair** on the channel's page issues the code.

## Telegram

1. Open [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, follow the prompts, and copy the bot token.
2. Store the token and register the channel as above (or **Channels → Add channel → Telegram** and paste it).
3. Run `coffer channel pair <name>` and send the code to your bot. The bot confirms; you are the owner.
4. Send any message. It lands in a conversation with the channel's agent and the reply comes back to Telegram.

Telegram uses long polling — no public URL, no tunnel, nothing to expose.

## SeaTalk

SeaTalk needs an org-approved app on the [SeaTalk Open Platform](https://open.seatalk.io/): create the app, enable the **Bot** capability and set it Online, and request the scopes your admin must approve (at minimum _Send Message to Bot User_). Note the **App ID** and **App Secret**; on webhook delivery also note the Event Callback **Signing Secret**.

SeaTalk delivers events one of two ways, and the platform lets a bot use **only one at a time**. The choice lives both on the channel (`--delivery`) and on the app's event-delivery setting in the Developer Portal, and the two must agree.

### WebSocket delivery

Coffer holds one outbound connection to SeaTalk: no public URL, no tunnel, no listener, no signing secret. It needs SeaTalk's own Python client library, which is distributed from SeaTalk's portal and which Coffer neither bundles nor depends on — unpack it so that `~/.coffer/vendor/seatalk_oapi_sdk/` exists, or point `COFFER_SEATALK_SDK_DIR` at the directory you keep it in.

```bash
coffer credentials set channel/st/app-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret --delivery websocket --agent claude-code
```

Then switch the app's event delivery to **WebSocket** in the Developer Portal. The portal's **Re-verify** passes only while the connection is live, so enable the channel in Coffer first.

`coffer channel status my-seatalk` prints the connection state — `connecting`, `connected`, `kicked`, `sdk_missing` or `error` — plus a verbatim `ws error:` line when there is one; `--json` carries it as `websocket_state` and `websocket_error`, and the channel's page names it in words:

```
inbound:  websocket (connected)
```

- **One connection per SeaTalk app.** If the same app is connected from somewhere else — a second machine, a colleague testing — that connection takes the events and this one reports `kicked` and retries slowly rather than fighting for the socket.
- **Events pause while the connection is down**; there is no public endpoint queuing them for you.
- **Without the library**, that one channel refuses to start and names the directory it searched; the daemon and every other channel keep running.

### Webhook delivery

SeaTalk POSTs each event to a public URL you own.

```bash
coffer credentials set channel/st/app-secret
coffer credentials set channel/st/signing-secret
coffer channel register my-seatalk --type seatalk --app-id <APP_ID> \
  --app-secret-ref channel/st/app-secret \
  --signing-secret-ref channel/st/signing-secret --agent claude-code
```

While a webhook SeaTalk channel is enabled, Coffer runs a local callback listener on `127.0.0.1:8787` (override with `COFFER_CALLBACK_PORT`). It is loopback-only, so something has to carry the internet to it — Coffer never exposes the daemon itself:

- **Run the tunnel yourself**: `cloudflared tunnel --url http://127.0.0.1:8787` or `ngrok http 8787`.
- **Let Coffer supervise one**: create a Cloudflare named tunnel whose ingress points at `http://127.0.0.1:8787`, then on the channel's page (**Edit channel**) paste its connector token and the public base URL it answers on. The token goes into the credential store, and Coffer keeps a `cloudflared` child alive for as long as the channel is enabled, restarting it if it dies.

Set the app's **Event Callback URL** to the one Coffer composes, `<public-url>/seatalk/<channel uid>` — copy it from the `register:` line of `coffer channel status` rather than typing it. The listener answers SeaTalk's verification challenge automatically.

```
inbound:  webhook 127.0.0.1:8787/seatalk/<channel uid> (listener up)
tunnel:   managed (up)
register: https://<public-host>/seatalk/<channel uid>
```

The tunnel line reads `not managed by Coffer` when you front the callback yourself — a choice, not a fault. `--json` carries the same facts as `tunnel_managed` and `tunnel_running`.

### Switching delivery later

Change it on the channel and in the Developer Portal in the same sitting. Coffer drops the fields the other method owns — a websocket channel keeps no signing secret, public URL or tunnel token, and a webhook channel needs its signing secret back. Going to webhook, set the callback URL in the portal; going to websocket, switch the portal to WebSocket and Re-verify while Coffer holds the connection.

Pairing and chatting are identical on both delivery methods. Replies render SeaTalk Markdown.

## Use it

In a paired chat, these in-chat commands control the conversation:

| Command   | What it does                                                        |
| --------- | ------------------------------------------------------------------- |
| `/help`, `/start` | What this bot understands.                                  |
| `/new`    | Start a fresh conversation.                                         |
| `/agent`  | Switch which agent answers in this chat.                            |
| `/model`  | Switch the model that agent runs on.                                |
| `/effort` | Switch the thinking effort.                                         |
| `/stop`   | Interrupt the turn in flight.                                       |
| `/save [collection]` | Save the document you just sent into a knowledge collection (asks which one if you don't name it). |
| `/status` | Which conversation this chat is bound to, and whether a turn is running. |

Channel conversations also appear on the app's **Chat** page.

### Notifications

Push a message to a paired channel any time — no inbound message needed:

```bash
coffer channel notify mybot "deploy finished"                 # to the owner's DM
coffer channel notify mybot "deploy finished" --chat <chat-id> # to another paired chat
```

Naming a chat the channel is not paired to is refused. Over HTTP the same thing is `POST /api/v1/channels/{uid}/notify` with `{"text": "..."}`; routes address a channel by its uid, the CLI by its name. On the channel's page, the **Test delivery** card sends a one-off line to the paired peer — the quickest way to confirm delivery right after pairing.

### Day-to-day

- **Edit** a channel from its page (**Edit channel**): change the default agent, or rotate a secret. A rotated secret is written back to the same credential reference, so binding and pairing are untouched; leave a secret field blank to keep the current value.
- **Disable** a channel on the Channels page to stop its traffic at once (polling halts, events are refused); **enable** to resume.
- **Delete** a channel to remove it; its past conversations stay in Chat history until the retention policy prunes them.

## Moving a channel to another machine

If your vault converges with a sync remote, a channel shows up on every machine — and runs on exactly one of them, the one in its **Runs on** column, because two daemons polling the same bot would each answer half your messages. Registering binds a channel to the machine you registered it from (or the one `--runs-on` names), so this only comes up when you want to move one:

```bash
coffer channel bind mybot                 # run it here
coffer channel bind mybot <machine-id>    # run it there (coffer sync machine list names them)
```

or pick the machine in the **Runs on** column or on the channel's page. No restart: the machine giving the channel up stops within a couple of seconds, and the machine taking it over starts after the next sync round brings the change across. Rebind **from the machine that currently runs the channel** and the handover has no overlap; binding a channel to the machine you are at while another still holds it can leave both answering until that machine's next round.

- A channel bound to a retired machine runs nowhere, and says so. Bind it to a live one.
- **Runs on** is not **Reach**. Reach says which agents a channel may drive and is set on each machine; the binding says which machine runs the adapter and is the same everywhere.

[Sync →](/guide/sync)
