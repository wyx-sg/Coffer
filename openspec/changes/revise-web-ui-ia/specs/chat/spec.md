## RENAMED Requirements

- FROM: `### Requirement: Show every conversation on the Chat page`
- TO: `### Requirement: Show every conversation on the Conversations page`

## MODIFIED Requirements

### Requirement: Show every conversation on the Conversations page
The web UI MUST carry a **Conversations** page (`/conversations`; the old `/chat` and `/chat/:id`
redirect to it): the conversation list on the left and the selected conversation on the right. It
is the page this spec's other requirements call the Chat page. The list MUST show every
conversation Coffer runs, whatever opened it — a conversation an IM channel (SeaTalk, Telegram)
opened, and one opened from Coffer's own UI, which is modelled as a built-in source named
**Coffer** — each row carrying a **source badge** naming its channel or Coffer, with filters by
source and by agent. A channel's badge MUST also name where in the channel the conversation
lives — a direct chat or a group (by its name when Coffer knows it), a thread or topic rather than
the chat's main timeline, and a parallel thread's `🧵#N` mark — and every row MUST show the latest
message's words on one line and whether a turn is running in it. A conversation carrying an `owner` belongs to that surface, is left out of the
list, and stays readable by id. A conversation's page MUST show the full exchange and a reply box
that continues it, whichever source opened it; **New conversation** is a secondary action, and the
page opens on the list rather than on a welcome or suggestions page, which it does not have. The
composer carries no voice input: a voice message reaches an agent only through a channel, which
transcribes it (see "Transcribe audio attachments when transcription is configured"). There is no
web-only conversation kind: the page and the channel are two windows onto one timeline, driven by
one owner, and an agent cannot tell which window a turn arrived through.

#### Scenario: a channel's conversation is listed beside the web's with a badge
- **GIVEN** one conversation started from Coffer's own UI and one opened by an IM channel
- **WHEN** the Conversations page's list renders
- **THEN** both conversations are listed, the first with a Coffer badge and the second with a badge naming its channel
- **AND** filtering by that channel lists only the second

#### Scenario: a row names the chat and thread it came from
- **GIVEN** a conversation a SeaTalk direct chat opened, one a group thread opened, and one a `/thread` parallel conversation opened, whose turn is running
- **WHEN** the Conversations page's list renders
- **THEN** the first row's badge names SeaTalk and the direct chat, the second the group and its thread, and the third its `🧵#N` mark
- **AND** each row shows its latest message's line, and the third is marked running

#### Scenario: a channel's conversation is continued from the page
- **GIVEN** a conversation a SeaTalk channel opened
- **WHEN** the user opens it on the Conversations page and sends a reply
- **THEN** the page shows the full exchange and the reply starts a turn in that same conversation

#### Scenario: the page opens on the list with no welcome page
- **GIVEN** conversations from two sources
- **WHEN** the user opens `/conversations`, and then an old `/chat` link
- **THEN** each opens the Conversations list with New conversation as a secondary action, with no welcome or suggestions page and no voice-input control in the composer

### Requirement: Put the open conversation in the URL
The open conversation MUST be part of the URL (`/conversations/:id`, with the old `/chat/:id` redirecting there), so a refresh, a
deep link and a second tab all reopen the same thread. A link to a conversation
that no longer exists MUST say so explicitly, with a way back to a new draft —
never drop silently into the draft surface as though the link had been to
nothing.

#### Scenario: a stale conversation link says so
- **GIVEN** a link to a conversation that has been deleted,
- **WHEN** it is opened,
- **THEN** the page says the conversation is gone and offers a way to start a
  new one, rather than silently showing the draft surface.

### Requirement: Create the conversation on the first send
The draft is not a conversation row. **New conversation** opens a blank draft surface,
and the **first send** is what creates the conversation — so a user who opens
the page and changes their mind leaves nothing behind. Where no managed agent
is available at all, the draft MUST be replaced by a state saying how to get
one rather than by a composer that can only fail.

When the conversation is created but the daemon refuses its first message (for
example `ATTACHMENT_NOT_FOUND`), the message MUST NOT be lost: its text and
attachment chips are put back into the new conversation's composer and the
refusal is shown in the thread's banner, without a Retry.

#### Scenario: the draft creates the conversation on first send
- **GIVEN** the Conversations page's New conversation draft,
- **WHEN** the first message is sent from the draft surface,
- **THEN** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

#### Scenario: a draft's first message refused after its conversation is created keeps its text and files
- **GIVEN** the draft surface with typed text and an attached file
- **WHEN** the conversation is created and its first message is refused
- **THEN** the refusal is shown in the new conversation's thread with no Retry
- **AND** that conversation's composer holds the text and the file's chip, and sending from it carries the same file
