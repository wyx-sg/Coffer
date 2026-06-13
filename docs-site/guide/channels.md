# Channels

A **channel** lets you reach your Coffer agents from a messaging app — **Telegram** or **SeaTalk**. Pair the channel to your own account, then chat with an agent, approve its tool calls with a tap, and receive notifications Coffer pushes you, all from inside the IM chat.

## Register a channel

Store the bot secret in the credential store first, then register the channel with **references** to it (never the secret itself):

```bash
coffer credentials set tg-bot-token                          # paste the token at the prompt
coffer channel register mybot --type telegram --bot-token-ref tg-bot-token
coffer channel pair mybot                                    # → an 8-char, single-use pairing code
coffer channel status mybot                                  # adapter state + paired peer
```

- Telegram needs `--bot-token-ref`; SeaTalk needs `--app-id --app-secret-ref --signing-secret-ref`. `--agent` (default `builtin`) chooses which agent answers.
- **Pairing is the security boundary.** Coffer is single-user: send the code to the bot from your own account to become its sole owner. Anyone else is ignored.

## Telegram vs SeaTalk

- **Telegram** uses long polling — no public ingress, nothing to expose.
- **SeaTalk** is webhook-only. Coffer runs a local callback listener (loopback `127.0.0.1:8787` by default) **only while a SeaTalk channel is enabled**. Point a tunnel (cloudflared / ngrok) at it and register `<public-url>/seatalk/<channel>`. Coffer never exposes the daemon itself and does not manage the tunnel. SeaTalk also needs an org-approved Open Platform app with the Bot capability.

## Use it

```bash
coffer channel notify mybot "deploy finished"        # push a message to your paired account
```

In a paired chat, the in-chat commands `/new`, `/stop`, `/status`, and `/help` control the conversation. Channel conversations also appear on the app's **Chat** page.

The **Channels** page in the app does the same without the terminal: add a channel (store its secret and register in one step), pair, toggle it on or off, and send a test message from the channel detail page.

[Multi-machine sync →](/guide/sync)
