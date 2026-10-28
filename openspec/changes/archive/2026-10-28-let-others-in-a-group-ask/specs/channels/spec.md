## ADDED Requirements

### Requirement: Let others in a group ask the bot
A channel MUST let someone who is not one of its owners ask the bot in a group,
read-only, while its **Let others in the group ask** setting (`others_can_ask`)
is on, which it is by default. The group must be one an owner has already
addressed the bot in (it has a peer row), the message must be addressed to the
bot, and its sender must be named by the transport; anywhere else the refusal of
"Act in a group only on an addressed message from the owner" stands.

Such a message drives a turn in the group's conversation like an owner's, and
its origin block carries the line `asker: not an owner (read-only)`. The channel
note of a group where others may ask tells the agent what that line allows: it
answers their questions and runs read-only checks for them, and changes nothing
and starts no work — no deploy, publish, data change, ticket, message or task —
on their word; asked for one, it says an owner has to ask for it, and an owner's
later message in the same thread can. A command from them (a message starting
with `/`) is answered with "🚫 Commands are for <bot>’s owners." and runs
nothing; their taps on the bot's buttons stay refused. The setting sits on the
channel's Settings tab under **Receiving messages**, with the other group
switches, and turning it off restores the owner-only gate from the next message.

The read-only limit is an instruction to the agent, not a sandbox: the agent
keeps the permissions the owner gave it. See [Others in a Group May Ask the Bot,
Read-Only](../../../docs/decisions/others-in-a-group-may-ask-read-only.md).

#### Scenario: someone else in a registered group is answered read-only
- **GIVEN** a channel whose owner has addressed the bot in a group, with others allowed to ask
- **WHEN** Sam, who is not an owner, @mentions the bot there
- **THEN** a turn runs whose origin names Sam and carries `asker: not an owner
  (read-only)`, and no refusal is sent

#### Scenario: an owner's own turn carries no read-only mark
- **GIVEN** a channel whose owner has addressed the bot in a group
- **WHEN** the owner's turn runs
- **THEN** its origin block has no `not an owner` line

#### Scenario: someone else's command in a group is refused
- **GIVEN** a registered group with others allowed to ask
- **WHEN** someone who is not an owner sends `/new codex` there
- **THEN** the bot answers "🚫 Commands are for <bot>’s owners." and no
  conversation is created or switched

#### Scenario: others cannot ask once the switch is off
- **GIVEN** a registered group on a channel with **Let others in the group ask** off
- **WHEN** someone who is not an owner @mentions the bot
- **THEN** the bot replies "🚫 Only <bot>’s owners can use it here." and no turn starts

#### Scenario: a group note says what someone else's turn allows
- **WHEN** the channel note of a group where others may ask is composed
- **THEN** it names the `asker: not an owner` line, allows answers and read-only
  checks, and says an owner has to ask for a change, before the reply style;
  a note where others may not ask says none of it

## MODIFIED Requirements

### Requirement: Act in a group only on an addressed message from the owner
The bot MUST act in a group ONLY on an addressed message (an @mention of the
bot). Un-addressed group messages are ignored. An addressed message from a
non-owner — including one whose `sender_id` the transport could not supply — is
refused with the short reply "🚫 Only <bot>’s owners can use it here." and starts no turn,
unless "Let others in a group ask the bot" admits it as a read-only question. A non-owner
message that is **not** addressed — which reaches the gate only when the channel
is set to answer without a mention — is dropped silently: the refusal is spoken
to someone who spoke to the bot, never to the room's chatter.

#### Scenario: an un-addressed group message is ignored
- **GIVEN** a paired channel and a group chat the bot is a member of
- **WHEN** a group message arrives with no @mention of the bot
- **THEN** no reply is sent and no turn or peer row is created for the group

#### Scenario: a non-owner @mention in a group is refused
- **GIVEN** a paired channel with a known owner
- **WHEN** someone other than the owner @mentions the bot in a group chat the
  owner has not addressed it in
- **THEN** the bot replies "🚫 Only <bot>’s owners can use it here." and no turn is
  started

#### Scenario: a non-owner's un-addressed group message is dropped silently
- **GIVEN** a paired channel set to answer in groups without a mention, and a group chat
- **WHEN** someone other than the owner sends a group message that does not address the bot
- **THEN** no reply is sent, no turn is started and no peer row is created

#### Scenario: an empty sender_id in a group cannot bypass the owner gate
- **GIVEN** a paired channel with a known owner and a group chat
- **WHEN** an addressed group message arrives with no resolvable `sender_id`
  (the transport failed to supply one)
- **THEN** the bot refuses it exactly like a non-owner sender — no turn is
  started and no peer row is created

### Requirement: Gate inbound traffic on sender identity
The owner gate MUST verify sender identity, not only chat identity. Every
inbound envelope carries a `sender_id`, whose platform meaning each child spec
names; pairing records it on the peer, and an inbound message is accepted only
when its `chat_id` matches and its sender matches the peer's stored
`sender_id`. A message that names no sender is refused, in a direct chat as in a
group: ownership that cannot be proven is not ownership. Pairing refuses the
same way — a code sent in a message that names no sender binds nobody and burns
no attempt.

The peer is a `ChannelPeer`: `(resource, chat_id)`, display name, paired-at and
the paired sender's identity (`sender_id`) — one row per (channel, chat): the
paired owner plus one row per group the owner has addressed the bot in. The
conversation a chat is in the middle of, and its sticky preferences (the chosen
agent, model and directory), are not on the peer: they live in the
thread conversation rows keyed by (channel, chat, thread).

The core never sees platform payloads: every adapter produces and consumes
the normalized `InboundMessage`, `InboundCallback` and `OutboundMessage`
envelopes, and inbound carries the sender's identity for this gate.

Someone other than an owner never drives a turn as an owner: where "Let others in
a group ask the bot" admits them, their turn says they are not an owner.

#### Scenario: a group member who is not the paired sender is ignored
- **GIVEN** a peer paired with a stored sender identity
- **WHEN** a message arrives with the same chat id but a different sender id
- **THEN** no reply is sent and no turn is started

#### Scenario: a direct message that names no sender is ignored
- **GIVEN** a paired channel
- **WHEN** a message arrives in the owner's chat but the transport supplied no sender id
- **THEN** no reply is sent and no turn is started

#### Scenario: a pairing code sent with no sender binds nobody
- **GIVEN** a channel with a pending pairing code
- **WHEN** the right code arrives in a message that names no sender
- **THEN** nobody is paired and the code is still valid

#### Scenario: ignore messages from strangers
- **GIVEN** a paired channel
- **WHEN** a different account messages the bot
- **THEN** no reply is sent and no turn or conversation is created

### Requirement: Configure when the bot answers in a group
Per-group inbound gating MUST be configurable. A channel may set
require-mention (default on for groups — the bot answers only when @mentioned or
replied-to) and ignore-messages-that-@-someone-else (opt-in — a group message
that @mentions any non-bot user is dropped silently, even when it also mentions
the bot) — so a bot sitting in a busy group answers only when it should. Both
are plain config bools; the channel stays owner-gated regardless, so this is
about *when* to answer, not *who* may drive turns. Who else may ask is "Let
others in a group ask the bot".

#### Scenario: require_mention on drops an un-addressed group message
- **GIVEN** a paired channel with `require_mention` on (the default)
- **WHEN** an un-addressed group message arrives (no @mention/reply-to-bot),
  even from the owner
- **THEN** it is dropped at the mention gate — no reply, no turn, and no peer row

#### Scenario: require_mention off admits an un-addressed owner group message
- **GIVEN** a paired channel with `require_mention` off
- **WHEN** an un-addressed group message arrives from the owner
- **THEN** it passes the mention gate and drives a turn (still owner-gated: a
  non-owner would be refused by the sender checks below the gate)

#### Scenario: ignore_other_mentions drops a message that also @mentions a human
- **GIVEN** a paired channel with `ignore_other_mentions` on
- **WHEN** a group message @mentions the bot but also @mentions another user
- **THEN** it is dropped silently — no reply and no turn — so the bot does not
  butt into human-aimed traffic

#### Scenario: ignore_other_mentions off still answers when @mentioned alongside a human
- **GIVEN** a paired channel with `ignore_other_mentions` off (the default)
- **WHEN** a group message @mentions the bot alongside another user
- **THEN** the turn still runs — the extra human @mention does not suppress it
