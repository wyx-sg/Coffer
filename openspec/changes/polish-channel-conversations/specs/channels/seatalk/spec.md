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
