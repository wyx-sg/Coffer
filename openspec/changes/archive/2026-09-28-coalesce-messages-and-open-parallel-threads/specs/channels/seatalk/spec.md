## ADDED Requirements

### Requirement: Hand a chat's events to the channel in arrival order
The websocket MUST hand one chat's events to the channel in the order they
arrived, each only after the one before it has been handed over. Events of
different chats (a DM's employee code, a group's id) still run concurrently.
Ingesting an event awaits work whose length varies: downloading a forwarded
record's files, resolving a quote. Without this ordering, a message sent second
could reach its conversation first, and its turn would run without the message
it follows.

#### Scenario: a slow forwarded record still precedes the text sent after it
- **GIVEN** a paired SeaTalk direct chat
- **WHEN** a forwarded record whose file download is slow arrives, followed by a text message
- **THEN** the channel receives the forwarded record first and the text second

### Requirement: Open a parallel thread by posting its root message
On SeaTalk a thread's id is its root message's id (see "Identify a thread by its
root message"), so `/thread` MUST open a parallel thread by posting its mark as a
new direct-chat message. That message's id is the thread's id, and the owner's
replies under it drive the parallel conversation. A direct-chat reply-in-thread
under any other message is a casual reply and stays in the direct chat's
conversation ([channels](../spec.md) "Key conversation identity by channel, chat and thread").

#### Scenario: /thread posts the root message the thread hangs from
- **GIVEN** a paired SeaTalk direct chat
- **WHEN** the owner sends `/thread`
- **THEN** the bot posts a direct-chat message opening with `🧵#1 Task`
- **AND** a reply under that message is keyed to the new parallel conversation
