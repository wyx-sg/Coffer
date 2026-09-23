## MODIFIED Requirements

### Requirement: Route the owner's messages into a turn-platform conversation
Inbound text from the paired peer MUST route to the peer's active conversation,
creating one on first use via the turn platform's standard
conversation-creation path (default agent validated by the agent registry). The
channel layer MUST reach agents only through the turn platform's seams:
conversation service, turn orchestrator (spec `chat`). The conversation is an
ordinary one, recorded in the vault with full history. When the active
conversation has been deleted, the peer's next message creates a fresh
conversation with the thread's agent — its sticky `/agent` choice while that
agent is still inside the channel's scope, else the channel's default agent; when the daemon restarts mid-turn, the turn
platform's startup sweep marks the orphaned turn failed and the channel
conversation simply continues on the next message.

#### Scenario: a paired message gets an agent reply
- **GIVEN** a paired channel whose default agent is available
- **WHEN** the peer sends a text message
- **THEN** a turn runs in the peer's conversation and the reply is delivered
  to the IM chat

#### Scenario: the channel conversation is a normal chat conversation
- **GIVEN** a channel conversation created by first contact
- **WHEN** the user opens the turn platform's conversation APIs
- **THEN** the conversation and its messages are listed like any other

### Requirement: Answer the conversation commands from any paired chat
Commands `/new`, `/stop`, `/status`, `/help` MUST work from any paired chat.
`/new` starts a fresh conversation with the thread's current agent (its sticky
`/agent` choice while that agent is still inside the channel's scope, else the
channel's default agent), `/stop`
interrupts the running turn, `/status` reports the active conversation, agent,
and turn state, and `/help` lists the commands. `/stop` and `/new` take effect
even while a turn is running; other messages join the conversation's pending
queue (spec `chat` — the one the web shows; the channel refuses past 10 waiting
and tells the peer the channel is busy) and run in order. A message arriving
exactly when the previous turn finishes joins the queue rather than racing it:
turns for one conversation never overlap.

These are the commands that need nothing of the conversation; the ones that
configure the conversation the chat is bound to — `/agent`, `/model`, `/effort`
— are specified in "Switch the conversation's agent from chat" and "Switch the
model and reasoning effort from chat", and `/save` in "Save a sent document into
a collection". All of them live on one roster (see "Register the bot's command
menu and profile from one roster"), so none of the lists derived from it can go
stale.

#### Scenario: /new starts a fresh conversation
- **GIVEN** a paired channel with an active conversation
- **WHEN** the peer sends `/new`
- **THEN** a new conversation with the thread's current agent (the default
  agent when none was chosen, or when the chosen one has since left the
  channel's scope) becomes active and the old one remains in history

#### Scenario: /stop interrupts a running turn
- **GIVEN** a turn in progress
- **WHEN** the peer sends `/stop`
- **THEN** the turn ends as interrupted and the chat is responsive again

#### Scenario: messages during a turn are queued in order
- **GIVEN** a turn in progress
- **WHEN** the peer sends two more messages
- **THEN** they run as consecutive turns in arrival order after the first ends

#### Scenario: the queue is bounded and overflow is reported
- **GIVEN** a full message queue
- **WHEN** the peer sends another message
- **THEN** the message is dropped and the peer is told the channel is busy

### Requirement: Manage channels from the Channels page and the CLI
The Channels page MUST list channels, register new ones (storing secrets
through the credential store), show each row's paired peer and health, set each
channel's reach (enable/disable and scope), bind each channel to the machine
that runs it (see "Bind each channel to the one machine that runs it"), and
delete a channel from its row. A channel's detail page MUST show its status
(adapter running, paired peer, ingress facts the channel's type has to report),
issue pairing codes, edit the channel, send a test notification to its paired
owner (see "Notify the paired owner on demand"), and delete it.

Editing changes the channel's default agent and its type's plain settings (a
SeaTalk app id, delivery transport and public base URL). Rotating an existing
secret happens **in place**: the new value MUST be written to the credential
store under the ref the channel already cites before the configuration is
saved, and that ref MUST stay in the saved configuration, so a rotation moves
no secret and leaves the channel's machine binding and pairing untouched. A
secret field left blank rotates nothing. A SeaTalk secret the channel does not
yet cite — a signing secret after switching back to webhook delivery, or a
first tunnel token — is written under a newly minted ref that the saved
configuration then cites. Switching a SeaTalk channel to websocket delivery
drops its signing-secret ref, tunnel-token ref and public base URL from the
configuration, since websocket delivery refuses webhook fields; the stored
credential values stay in the credential store.

The CLI MUST offer these operations across three command groups:
`coffer channel list / register / bind / pair / status / notify` for the
channel-specific ones; the kind-agnostic `coffer resource show / enable /
disable / rename / delete channel <name>` and `coffer scope show / set channel
<name>` for its lifecycle and reach; and `coffer credentials set <ref>` for
rotating a secret under a ref that `coffer resource show` reports. Editing a
channel's default agent or type settings is served by the detail page and
`PATCH /api/v1/resources/{uid}`.

#### Scenario: register and list channels from the command line
- **GIVEN** a running daemon and a stored credential
- **WHEN** the user runs `coffer channel register` and `coffer channel list`
- **THEN** the channel is created and appears in the listing

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and CLI
- **THEN** adapter run state, paired peer, and the channel type's own ingress
  facts are reported accurately

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  credential ref
- **WHEN** the owner enters a new bot token in the channel detail page's edit
  dialog and saves
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves
