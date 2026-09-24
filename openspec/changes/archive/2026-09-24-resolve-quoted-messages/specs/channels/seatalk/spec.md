## RENAMED Requirements

- FROM: `### Requirement: Keep the quoted message id as a handle`
- TO: `### Requirement: Resolve a quoted message with the bot's own token`

## MODIFIED Requirements

### Requirement: Resolve a quoted message with the bot's own token
Both SeaTalk inbound message events carry a **`quoted_message_id`** when the user
replied by quoting. The envelope MUST keep it, and the transport MUST resolve it
through `GET /messaging/v2/get_message_by_message_id` with the app's own token
([channels](../spec.md) "Ground a turn in the message it quotes"). SeaTalk gives
one message a different id per app, so only the app that received the event
can resolve this one. The response has a thread message's shape, so it is
flattened, and its images and files downloaded, the same way. Any error or
non-zero `code` resolves to nothing, and the turn runs on the message alone.

#### Scenario: a quoting seatalk message keeps the quoted id on the envelope
- **GIVEN** a SeaTalk direct message and a SeaTalk group message that each quote an earlier message
- **WHEN** the transport normalizes them
- **THEN** each envelope carries the event's `quoted_message_id`

#### Scenario: a quoted seatalk message is resolved by its id
- **GIVEN** a quoted message id this app received
- **WHEN** the transport resolves it
- **THEN** it calls `get_message_by_message_id` with that id and returns the
  message's sender and text
- **AND** a failed or refused lookup returns nothing rather than failing the turn

## ADDED Requirements

### Requirement: Read every page of a thread
A thread read MUST follow `next_cursor` until SeaTalk returns none. The thread
endpoints page oldest-first at no more than 100 messages a page, so reading one
page would drop the messages written just before the @mention. The read stops
after a fixed number of pages so a runaway cursor cannot stall the turn. A
later page that fails keeps the pages already read.

#### Scenario: a thread longer than one page is read to its last message
- **GIVEN** a SeaTalk thread whose first page carries a `next_cursor`
- **WHEN** the adapter fetches the thread
- **THEN** it requests the next page with that cursor and returns the messages
  of both pages in order
