## ADDED Requirements

### Requirement: Upload a file for a web message
The web Chat page MUST be able to hand the daemon a file before sending the
message that carries it. `POST /api/v1/chat/attachments` takes one file per
call, stores its bytes under `~/.coffer/chat-media` — never in the chat
database — and answers with an opaque id, the file's display name (its last
path segment), the type it is stored under and its size. The local path MUST
NOT appear in the response. The upload is not tied to a conversation, so a
draft can attach files before its conversation exists. It is bounded: a file
over 20 MB MUST be refused with `ATTACHMENT_TOO_LARGE` (413) whose message
names the limit, and a file that is not an image, audio, a document (PDF, Word,
PowerPoint, Excel, RTF, EPUB, CSV) or UTF-8 text MUST be refused with
`ATTACHMENT_TYPE_UNSUPPORTED` (415). Nothing is stored for a refused upload.
See [Chat Attachment Uploads](../../../docs/decisions/chat-attachment-uploads.md).

#### Scenario: an uploaded file is stored and named by an opaque id
- **GIVEN** a running daemon
- **WHEN** a PNG is uploaded to `POST /api/v1/chat/attachments`
- **THEN** the response is 201 with an id, the file's name, `image/png` and its size
- **AND** the bytes are stored under `~/.coffer/chat-media`, and no local path appears in the response

#### Scenario: an oversized upload is refused naming the limit
- **GIVEN** a file larger than 20 MB
- **WHEN** it is uploaded
- **THEN** the response is 413 `ATTACHMENT_TOO_LARGE` whose message names the 20 MB limit
- **AND** nothing is stored

#### Scenario: an upload of a type no agent can use is refused
- **GIVEN** a binary file that is not an image, audio, a document or text, such as a video
- **WHEN** it is uploaded
- **THEN** the response is 415 `ATTACHMENT_TYPE_UNSUPPORTED`
- **AND** nothing is stored

### Requirement: Send uploaded files with a web message
`POST /api/v1/chat/conversations/{id}/messages` MUST accept `attachment_ids`,
at most ten, naming uploads in the order they were attached. Each MUST reach
the turn exactly as a channel's downloaded media does: persisted on the user
message as an attachment reference after its text, re-materialised from
history by the turn task ("Re-materialise attachments from persisted
history"), and materialised by each agent adapter in its own shape — an image
inlined for a vision agent and handed as a path to a path-native one, a
document extracted to text ("Extract document attachments to text"), audio
transcribed when transcription is configured ("Transcribe audio attachments
when transcription is configured"). A message MUST carry text, at least one
attachment, or both; one that carries files and no text is persisted with a
short stand-in text naming them, the same one a channel's uncaptioned photo
gets, and a conversation it opens is named after the files. An id that names
no stored upload — never uploaded, or pruned — MUST be refused with
`ATTACHMENT_NOT_FOUND` (422), and nothing is persisted or queued for that
message.

#### Scenario: a web message carries its uploaded files as references
- **GIVEN** a conversation and a file uploaded through `POST /api/v1/chat/attachments`
- **WHEN** a message is sent with its text and that file's id
- **THEN** the persisted user message holds the text followed by an attachment reference
- **AND** reading the conversation's messages shows an `attachment` block with the file's name and type and no path

#### Scenario: a web-attached image reaches the agent the way a channel's does
- **GIVEN** an image uploaded from the web composer
- **WHEN** a message carrying it starts a turn
- **THEN** the agent adapter receives it as an attachment with the stored file's path, type and name, re-materialised from history

#### Scenario: a message with files and no text is persisted with a stand-in
- **GIVEN** an uploaded file
- **WHEN** a message is sent with that file's id and no text
- **THEN** it is accepted and the persisted user message's text names the file
- **AND** a message with neither text nor attachments is refused

#### Scenario: a message naming an unknown attachment is refused
- **GIVEN** a conversation
- **WHEN** a message is sent naming an attachment id no upload stored
- **THEN** the response is 422 `ATTACHMENT_NOT_FOUND`
- **AND** no user message is persisted and nothing is queued

### Requirement: Prune uploaded chat media on the retention cadence
The web composer's uploads MUST NOT accumulate without bound. On the retention
cadence, `~/.coffer/chat-media` MUST be swept by the same rule as the channel
media directory: a file whose mtime is more than 30 days old is deleted, with
no size cap and no reference check. A full prune reports the count under
`chat_media`, beside `channel_media`. A reference whose file is gone degrades
to a note that the file could not be read, and sending its id again is refused
as unknown.

#### Scenario: the chat-media prune deletes stale uploads and keeps fresh ones
- **GIVEN** `~/.coffer/chat-media` holding one upload older than 30 days and one recent one
- **WHEN** a full retention prune runs
- **THEN** the stale upload is deleted and the recent one is kept
- **AND** the prune result reports one deleted file under `chat_media`

### Requirement: Attach files from the Chat page composer
The Chat page's composer MUST let the owner attach files three ways: an attach
button that opens the file picker, dropping files onto the composer, and
pasting an image. Each attached file MUST show as a chip with its name, its
size and a control that removes it, and it MUST be uploaded at once, the chip
saying so while it uploads. A failed upload MUST stay on its chip with the
reason — the size limit, an unsupported type — and is never sent. Send MUST be
disabled while any upload is in flight or failed, so a message never leaves
without a file its owner attached; a message with only attachments may be
sent. Sending clears the chips, and the files travel with the message by the
ids their uploads returned.

#### Scenario: attaching a file shows a chip and sends it with the message
- **GIVEN** an open conversation on the Chat page
- **WHEN** the owner attaches a file with the attach button and sends a message
- **THEN** a chip with the file's name and size appears, and the message is sent with that file's upload id
- **AND** the chips are cleared after the send

#### Scenario: send waits for uploads in flight
- **GIVEN** a file whose upload has not finished
- **WHEN** the owner looks at the composer
- **THEN** its chip says it is uploading and Send is disabled until the upload finishes

#### Scenario: a failed upload says why and is not sent
- **GIVEN** a file the daemon refuses
- **WHEN** its upload fails
- **THEN** its chip shows the reason and Send is disabled
- **AND** removing the chip enables Send again

#### Scenario: a pasted image is attached
- **GIVEN** the composer has focus
- **WHEN** the owner pastes an image
- **THEN** it is attached and uploaded like a picked file

### Requirement: Show a message's attachments in the thread
A user message's attachments MUST be shown in the thread as chips naming each
file and its type, under the message's text — including the just-sent echo of
a message before its row lands. Because they are read from the persisted
references, a reload, a second tab and a message sent from a channel show the
same chips. The path is never shown.

#### Scenario: an attached file is shown in the thread after a reload
- **GIVEN** a message sent from the Chat page with an attached file
- **WHEN** the conversation is reloaded
- **THEN** the message shows a chip naming the file under its text
