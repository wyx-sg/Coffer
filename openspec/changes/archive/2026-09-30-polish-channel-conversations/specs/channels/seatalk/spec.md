## ADDED Requirements

### Requirement: Ping a long turn's end into its thread
SeaTalk's answer is the stream opened when the turn began, so finishing it
notifies nobody. A turn past the channel's ping threshold ([channels](../spec.md)
"Ping the asker when a long turn ends") MUST therefore end with the one short
ping as a new text message in the same chat and thread, and in a group it MUST
open with the asker's `<mention-tag>` — a mention decides its notification when
the message is created, and this message is created now.

#### Scenario: a group ping mentions the asker
- **GIVEN** a long SeaTalk group-thread turn from a member with a SeaTalk id
- **WHEN** it ends
- **THEN** a new message in that thread opens with the member's mention tag and
  reads `✅ Done · <elapsed> — <first line>`

### Requirement: Number the messages after the stream
A SeaTalk reply longer than one stream finishes the stream at its budget and
MUST send the rest itself, as ordinary text messages into the same chat and
thread, each opening with its place counting the stream as part one — `(2/3)`,
`(3/3)`. An ordinary send cut into several messages is numbered the same way.

#### Scenario: continuations after the stream are numbered
- **GIVEN** a SeaTalk stream whose final reply is past the stream budget
- **WHEN** the stream closes
- **THEN** the remainder goes out as messages headed `(2/N)` … `(N/N)` and nothing
  is handed back for the ordinary send

### Requirement: Post a reply's details into the card's thread
A SeaTalk thread's id is its root message's id and any message can root one, so
the Details button of a summary card ([channels](../spec.md) "Offer a reply's
details behind a summary card") MUST post the details as a reply in the thread
the card sits in — or, in a direct chat, the thread the card itself roots — and
rewrite the card (inside SeaTalk's update window) to say they were posted.

#### Scenario: the details button posts them as a thread reply
- **GIVEN** a SeaTalk summary card `m7` in a direct chat
- **WHEN** the owner taps Details
- **THEN** the details are sent into thread `m7` and the card reads `Details posted
  in the thread.`
