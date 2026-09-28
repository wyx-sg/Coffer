## MODIFIED Requirements

### Requirement: Take a burst of messages as one turn
Messages that arrive in quick succession in one chat and thread MUST become one
turn, not one turn each. A person who forwards a chat record and then types
"look into this" asked one question. The channel waits for a short quiet
window after each message before it starts the turn, and a message arriving
inside the window restarts it. The window is 1.5 seconds after a text message.
It is 5 seconds after a message that is rarely the whole ask: a forwarded chat
record, or files with no text. Both windows are the channel's own settings,
`wait_after_text_seconds` and `wait_after_forward_seconds`, each from 0 to 60
seconds and edited on the Channels page or with `coffer channel set
--wait-after-text/--wait-after-forward`; 0 runs every such message as its own
turn.

The coalesced turn carries:
- every message's text, in arrival order;
- every attachment;
- one origin block, taken from the last message, which is also what the reply
  attaches to and mentions.

Every message is still acknowledged when it arrives (see "Acknowledge receipt
and completion by capability"), never only when the window closes. Messages
sent while a turn is running are coalesced the same way before they join the
conversation's pending queue.

A slash command is never held. It first releases what its chat and thread are
holding, so the turn it follows still runs first. `/stop` is the exception:
it drops the held messages instead, since they had not started.

#### Scenario: a forwarded record and its follow-up become one turn
- **GIVEN** a paired direct chat
- **WHEN** the owner forwards a chat record and, two seconds later, sends "look into this"
- **THEN** one turn runs, and its text holds the forwarded record followed by "look into this"
- **AND** both messages were acknowledged when they arrived

#### Scenario: messages further apart than the window are separate turns
- **GIVEN** a paired direct chat
- **WHEN** the owner sends a text message and sends another one after the window has closed
- **THEN** each message drives its own turn, in arrival order

#### Scenario: /stop drops messages still being held
- **GIVEN** a message waiting in its quiet window
- **WHEN** the owner sends `/stop` before the window closes
- **THEN** the waiting message never becomes a turn

#### Scenario: a channel's quiet windows come from its settings
- **GIVEN** a channel whose config sets no windows
- **WHEN** its config is read
- **THEN** it waits 1.5 seconds after text and 5 seconds after a forward
- **AND** a config may set either window anywhere from 0 to 60 seconds, and a value outside that range is refused

#### Scenario: the quiet windows are edited from the command line
- **GIVEN** a registered channel
- **WHEN** the owner runs `coffer channel set <name> --wait-after-text 0 --wait-after-forward 8`
- **THEN** the channel's config holds those two windows and every other setting is unchanged

#### Scenario: the quiet windows are edited on the Channels page
- **GIVEN** a channel open in the Edit channel dialog
- **WHEN** the owner changes the wait after a text message and saves
- **THEN** the channel's config holds the new window and the other settings are unchanged
