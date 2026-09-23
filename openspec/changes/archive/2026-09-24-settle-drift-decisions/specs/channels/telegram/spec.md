## MODIFIED Requirements

### Requirement: Download every Telegram media type without leaking the token
Every type Telegram can attach to a message — **photos, documents, voice, audio,
video, animations, stickers, round video notes** — MUST be downloaded and become
an `Attachment` ([channels](../spec.md) "Hand inbound photos and files to the agent", [channels](../spec.md) "Drive a turn from every inbound media type or say why not"). A file over the cap
the Bot API places on what a bot may download — known from the `file_size` the
update carries — MUST be noted in the turn text exactly once, so the reply
acknowledges it, and MUST never be requested: no `getFile` is made for it. A
download that fails after `getFile` succeeded — the platform answers the
file endpoint with an error status, or the connection fails — is noted in the
turn text as `[attachment '<name>' could not be downloaded]` and the turn still
runs on whatever text and other attachments arrived. **The Telegram file URL
embeds the bot token**, so this path MUST log only the failure's class, or the
method and HTTP status — never the request URL, and never a traceback that
quotes it; no log record produced by any download path contains the bot token.

#### Scenario: a failed telegram download never puts the bot token in the log
- **GIVEN** a Telegram message with a photo whose file download fails after
  `getFile` succeeds,
- **WHEN** the adapter handles the message,
- **THEN** the turn runs with a note that the attachment could not be
  downloaded, and no log record contains the bot token

#### Scenario: an oversized file is reported once and never requested
- **GIVEN** a Telegram message carrying a document whose `file_size` is over the
  Bot API's download cap,
- **WHEN** the adapter downloads the message's attachments,
- **THEN** no `getFile` call is made and no attachment is produced
- **AND** exactly one note names the file and the cap
