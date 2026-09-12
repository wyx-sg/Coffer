# Channels

A **channel** lets you reach your Coffer agents from a messaging app — **Telegram** or **SeaTalk**. Pair the channel to your own account, then chat with an agent and receive notifications Coffer pushes you, all from inside the IM chat.

## Register a channel

Store the bot secret in the credential store first, then register the channel with **references** to it (never the secret itself):

```bash
coffer credentials set tg-bot-token                          # paste the token at the prompt
coffer channel register mybot --type telegram --bot-token-ref tg-bot-token
coffer channel pair mybot                                    # → an 8-char, single-use pairing code
coffer channel status mybot                                  # adapter state + paired peer
```

- Telegram needs `--bot-token-ref`; SeaTalk needs `--app-id --app-secret-ref`, plus `--signing-secret-ref` on webhook delivery or `--delivery websocket` for the outbound-connection transport. `--agent` (default `claude_code`) chooses which agent answers.
- **Pairing is the security boundary.** Coffer is single-user: send the code to the bot from your own account to become its sole owner. Anyone else is ignored.

## Telegram vs SeaTalk

- **Telegram** uses long polling — no public ingress, nothing to expose.
- **SeaTalk** delivers events one of two ways, and the platform lets a bot use only one at a time — so each channel picks its transport.
  - On **webhook** delivery, SeaTalk POSTs to a public URL. Coffer runs a local callback listener (loopback `127.0.0.1:8787` by default) **only while a webhook SeaTalk channel is enabled**, and you register `<public-url>/seatalk/<channel>` on the Open Platform. The listener is loopback-only, so something has to carry the internet to it: run the tunnel yourself (cloudflared / ngrok), or record a Cloudflare connector token on the channel and Coffer supervises a `cloudflared` child for it for as long as the channel is enabled. Coffer never exposes the daemon itself.
  - On **websocket** delivery, Coffer instead holds one outbound connection to SeaTalk: no public URL, no tunnel, no listener, no signing secret. It needs SeaTalk's own client library, which Coffer neither bundles nor depends on — put it in `~/.coffer/vendor` (or point `COFFER_SEATALK_SDK_DIR` at wherever you keep it). Without it, that one channel refuses to start and says what is missing; everything else keeps running.
  - Either way SeaTalk needs an org-approved Open Platform app with the Bot capability, and the channel's transport must match the app's event delivery setting in the Developer Portal.

## Use it

```bash
coffer channel notify mybot "deploy finished"        # push a message to your paired account
```

In a paired chat, the in-chat commands `/new`, `/stop`, `/status`, and `/help` control the conversation. Channel conversations also appear on the app's **Chat** page.

The **Channels** page in the app does the same without the terminal: add a channel (store its secret and register in one step), pair, toggle it on or off, and send a test message from the channel detail page.

[Export and import →](/guide/sync)
