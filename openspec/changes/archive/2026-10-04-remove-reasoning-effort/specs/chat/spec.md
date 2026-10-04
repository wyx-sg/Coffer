## ADDED Requirements

### Requirement: Let the owner set agent and model
The page MUST let the owner choose the agent a conversation runs on, on the
draft surface — once the conversation exists its agent is fixed and shown as a
label, because its upstream session and working directory belong to that one
agent (see "Record the agent on each conversation"). The page MUST let the owner
read and set the conversation's model over
`GET|PATCH .../agent-config`, persisting it while
preserving the conversation's working directory and upstream session id, and
reverting to the agent's own default when it is cleared. The model picker MUST
be offered on the **draft** surface as well as in an open
conversation, because the first turn is the one a user most wants to pitch, and
by the time the conversation exists that turn is already running. The page
offers no reasoning-effort control: the agent runs at the effort its own
configuration names.

A missing Coffer LLM connection MUST NOT block the page: with none configured
the draft surface still accepts a message and the turn runs on the agent's own
built-in model and login, because a Coffer connection is an optional override,
not a prerequisite ([provider-switching](../provider-switching/spec.md), and
[Provider Connections Projected Into Agent Config](../../../docs/decisions/provider-connections-projected-into-agent-config.md)).

#### Scenario: chat runs on the built-in model when no connection
- **GIVEN** a running daemon with no Coffer LLM connection configured for the
  agent,
- **WHEN** the Conversations page is opened,
- **THEN** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.

## MODIFIED Requirements

### Requirement: Open an archived conversation read-only
An archived conversation MUST open **read-only**: its history reads normally,
the composer and the model control is disabled, and a restore
control is offered in their place. Archived is a state the owner leaves
deliberately, not a thread that silently accepts a turn and unarchives itself.

#### Scenario: an archived conversation opens read-only
- **GIVEN** an archived conversation,
- **WHEN** it is opened on the Conversations page,
- **THEN** its history reads normally, the composer and the model
  control is disabled, and a restore control is offered.

### Requirement: Create the conversation on the first send
The draft is not a conversation row. **New conversation** opens a blank draft surface,
and the **first send** is what creates the conversation — so a user who opens
the page and changes their mind leaves nothing behind. Where no managed agent
is available at all, the draft MUST be replaced by a state saying how to get
one rather than by a composer that can only fail. That state says "No agent
connected", names Claude Code and Codex, and offers one **Open Agents** link to the
Agents page, where connecting an agent is Coffer's own action; it carries no install
prompt and no install command (handing an install to an assistant belongs to the
Agents page). The draft's title bar says "New conversation", and with an agent its
centre says which agent will run in which folder; the folder picker, agent and model
sit in the reply box's toolbar, and a draft opened from Ask an agent
says under the box that nothing is sent until Send.

When the conversation is created but the daemon refuses its first message (for
example `ATTACHMENT_NOT_FOUND`), the message MUST NOT be lost: its text and
attachment chips are put back into the new conversation's composer and the
refusal is shown in the thread's banner, without a Retry.

#### Scenario: the draft creates the conversation on first send
- **GIVEN** the Conversations page's New conversation draft,
- **WHEN** the first message is sent from the draft surface,
- **THEN** the conversation is created by that send and the turn runs in it;
  opening the draft and leaving creates nothing. With no managed agent
  available, the draft is replaced by a state saying how to get one.

#### Scenario: with no managed agent the draft links to the Agents page
- **GIVEN** no managed agent is available
- **WHEN** the user opens the New conversation draft
- **THEN** it says no agent is connected and offers Open Agents, which links to the Agents page, with no composer, no Copy prompt and no install command

#### Scenario: a draft's first message refused after its conversation is created keeps its text and files
- **GIVEN** the draft surface with typed text and an attached file
- **WHEN** the conversation is created and its first message is refused
- **THEN** the refusal is shown in the new conversation's thread with no Retry
- **AND** that conversation's composer holds the text and the file's chip, and sending from it carries the same file

## REMOVED Requirements

### Requirement: Let the owner set agent, model and reasoning level
**Reason**: Renamed: the owner no longer sets a reasoning level, so the title says agent and model.
**Migration**: Read "Let the owner set agent and model".

