## MODIFIED Requirements

### Requirement: Show a failed turn as one inline banner with Retry
A failed turn MUST replace the in-progress bubble with a single inline error
banner in the flow above the composer — never a floating notice and never two
error surfaces at once — carrying a Retry that re-sends the message that failed
and a dismiss that clears it.

The Retry MUST re-send the failed message whole: its text AND every attachment
it carried, whether the files came from the web composer or a channel. A
persisted message is re-sent with
`POST /api/v1/chat/conversations/{id}/messages/{message_id}/resend`, which
rebuilds it from its row and persists a new user message exactly as a send
does; a message whose row has not landed yet is re-sent as it was sent, with
its files' upload ids. A file the message referenced that the 30-day media
sweep has since deleted MUST refuse the retry with `ATTACHMENT_EXPIRED` (410),
naming the file, and nothing is persisted or queued — a retry is never sent
without a file the original carried. An id naming no user message of the
conversation is `MESSAGE_NOT_FOUND` (404).

A send the daemon refuses before it runs is not a failed turn: its message
stays in the composer, so the banner shows the reason with no Retry.

#### Scenario: a failed turn offers a retry in the thread
- **GIVEN** a turn that fails,
- **WHEN** the thread renders it,
- **THEN** the in-progress bubble is replaced by one inline banner in the flow,
  carrying a Retry that re-sends the failed message and a dismiss.

#### Scenario: a retry re-sends the failed message's attachments
- **GIVEN** a user message sent with an attached file, whose turn failed
- **WHEN** the owner presses Retry
- **THEN** the message is sent again with its text and the same file, and the agent receives that file as it did the first time
- **AND** the new user message shows the same attachment chips as the original

#### Scenario: a retry whose attachment was pruned is refused, never sent without it
- **GIVEN** a user message whose attached file the media sweep has since deleted
- **WHEN** it is resent
- **THEN** the response is 410 `ATTACHMENT_EXPIRED` naming the file
- **AND** no user message is persisted and nothing is queued

### Requirement: Create the conversation on the first send
The draft is not a conversation row. The page opens on a blank draft surface,
and the **first send** is what creates the conversation — so a user who opens
the page and changes their mind leaves nothing behind. Where no managed agent
is available at all, the draft MUST be replaced by a state saying how to get
one rather than by a composer that can only fail.

When the conversation is created but the daemon refuses its first message (for
example `ATTACHMENT_NOT_FOUND`), the message MUST NOT be lost: its text and
attachment chips are put back into the new conversation's composer and the
refusal is shown in the thread's banner, without a Retry.

#### Scenario: the draft creates the conversation on first send
- **GIVEN** the Chat page with no conversation open,
- **WHEN** the first message is sent from the draft surface,
- **THEN** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

#### Scenario: a draft's first message refused after its conversation is created keeps its text and files
- **GIVEN** the draft surface with typed text and an attached file
- **WHEN** the conversation is created and its first message is refused
- **THEN** the refusal is shown in the new conversation's thread with no Retry
- **AND** that conversation's composer holds the text and the file's chip, and sending from it carries the same file
