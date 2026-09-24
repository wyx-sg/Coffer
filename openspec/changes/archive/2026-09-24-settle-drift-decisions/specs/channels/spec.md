## MODIFIED Requirements

### Requirement: Drive a turn from every inbound media type or say why not
Every inbound media type MUST drive a turn, or say why it cannot. Whatever the
platform can attach to a message is downloaded and becomes an `Attachment` (see
"Hand inbound photos and files to the agent"). Where a platform caps what a bot
may download, a file over that cap MUST be noted in the turn text — exactly
once — so the agent's reply acknowledges it, not a silent no-op: the failure
mode being fixed is a user who sent a file and got an answer that never mentions
it. A file the platform already reports as over the cap is never requested. A
download that fails after the platform handed over a fetchable reference is
noted in the turn text and the turn still runs on whatever text and other
attachments arrived.

#### Scenario: an oversized inbound file tells the user
- **GIVEN** a message carrying a file larger than the platform lets a bot
  download,
- **WHEN** the message drives a turn,
- **THEN** the turn text carries a note naming the file as one that did not
  reach the agent, so the reply acknowledges it rather than the file being
  silently dropped
- **AND** the turn still runs on the message's text
