## MODIFIED Requirements

### Requirement: Pair exactly one owner with a single-use code
The daemon MUST issue, per channel, an 8-character single-use pairing code
(unambiguous alphabet, 1-hour TTL, bounded wrong-guess attempts). A message
consisting of the code binds its sender as the channel's sole peer, replacing
any previous peer, and the sender receives a confirmation. All other senders
MUST be ignored silently: a stranger messaging the bot produces zero observable
response and zero turns, while the owner's traffic is unaffected, so the bot
never reveals it is alive to strangers. A code that expires or suffers repeated
wrong guesses is invalidated, and a fresh code must be issued. The pairing code
is held in memory only, per channel, and never persisted. Re-issuing a code and
pairing again rebinds the channel to the new sender.

#### Scenario: issue a pairing code
- **GIVEN** a registered channel
- **WHEN** the user requests a pairing code
- **THEN** an 8-character code with an expiry is returned and audited

#### Scenario: pair by sending the code
- **GIVEN** an issued pairing code
- **WHEN** a sender messages the bot with exactly that code
- **THEN** the sender becomes the channel's peer and receives a confirmation
- **AND** the pairing is audited and the code cannot be reused

#### Scenario: an expired or wrong code does not pair
- **GIVEN** an issued pairing code
- **WHEN** a sender submits a wrong guess repeatedly or the code has expired
- **THEN** pairing fails, the sender gets no reply, and the code is invalidated

#### Scenario: pairing from another account replaces the owner
- **GIVEN** a channel paired to one sender, who has also addressed the bot in a group
- **WHEN** a new code is issued and a different sender messages the bot with it
- **THEN** the previous sender's direct and group pairings are removed, and their direct messages get no response
- **AND** a notification that names no chat goes to the new sender's direct chat
- **AND** in a group, an @mention from the new sender is answered while one from the previous sender is refused
