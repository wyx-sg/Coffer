## MODIFIED Requirements

### Requirement: Download the files a fetched thread carries
The images and files carried by a thread's **own** messages MUST be downloadable
with the app token, recursing forwarded records within them, one message at a
time, so the turn attaches those of the messages it folds and the read tool those
of the page it returns, alongside the flattened text ([channels](../spec.md) "Download the media a thread's messages carry").
SeaTalk file links require auth, so a URL alone is useless to the agent. The
thread read itself downloads nothing.

#### Scenario: a file posted earlier in a seatalk thread is attached to the turn
- **GIVEN** a SeaTalk thread whose earlier messages include a file and a forwarded record holding an image
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** both are downloaded with the app token and attached to the turn
- **AND** the flattened thread text is still folded into the turn

### Requirement: Read every page of a thread
A thread read MUST follow `next_cursor` until SeaTalk returns none. The thread
endpoints page oldest-first at no more than 100 messages a page (the read asks
for 100), so reading one page would drop the messages written just before the
@mention — the very ones a turn folds. The read is text only: each message comes
back with its id, its sender, when it was sent and whether a bot sent it
(`sender.sender_type` 2), and nothing is downloaded. The read stops after a fixed
number of pages so a runaway cursor cannot stall the turn. A later page that
fails keeps the pages already read; a read that fails outright says so.

#### Scenario: a thread longer than one page is read to its last message
- **GIVEN** a SeaTalk thread whose first page carries a `next_cursor`
- **WHEN** the adapter fetches the thread
- **THEN** it requests the next page with that cursor and returns the messages
  of both pages in order
