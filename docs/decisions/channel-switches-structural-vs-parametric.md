# Channel Switches: the Agent Opens a New Conversation, Model and Effort Apply Next Turn

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: spec channels ("Switch the agent with /new", "Switch the model and reasoning effort from chat", "Keep a chat's settings across its conversations", "Choose the working directory from chat", "Drive every managed agent from one bot", "Key conversation identity by channel, chat and thread", "Offer choices and actions as owner-gated cards");
spec chat ("Record the agent on each conversation", "Let the owner set agent, model and reasoning level");
[Channel Conversation Identity and Context](channel-conversation-identity-and-context.md), [Channel Owner Gate](channel-owner-gate.md),
[Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md), [Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md);
PRs #245, #385

## Context

From a phone the owner needs to change what the agent they are talking to is:
**which agent** (Claude Code or Codex), **which working directory**, **which
model**, and **how hard it reasons** (effort). Each has a selection card where
the platform has buttons. The commands are `/new <agent>`, `/dir [path]` and
`/model [name] [level]`.

These dimensions are not the same kind of thing to the turn platform:

- A conversation **records its `agent_key` for life**. Its upstream session —
  a Claude Code session id or a Codex thread id, stored as
  `AgentConfig.session_id` — belongs to that agent's CLI and cannot be resumed
  by the other. The working directory is fixed with it: an agent's session is
  tied to the directory it started in.
- **Model and effort are read fresh every turn.** The provider rebuilds the
  adapter per turn from the conversation's `AgentConfig`; Claude Code takes
  them as `model` and `effort` options on the SDK, Codex as fields of
  `turn/start` ([Driving Agents Through the SDK and
  App-Server](driving-agents-through-sdk-and-app-server.md)). Changing them
  mid-conversation keeps the session.
- **Coffer does not own the model namespace.** Model names and effort levels
  belong to each agent's CLI and change with its releases; Coffer reads the
  catalogue from the agent to offer choices ([Model Catalogue Read From the
  Agent](model-catalogue-read-from-the-agent.md)) but cannot know every name an
  account may run. Both managed agents present model and effort as one choice.
- **A group has several threads**, and the owner may want different agents in
  different threads of the same group.
- **A remote-reachable entrypoint choosing an agent's working directory is a
  boundary**: the agent can read and write there.

## Options Considered

### Option A — Structural vs parametric: agent and directory open a fresh conversation, model and effort apply to the next turn of the same one; every choice sticks per thread (chosen)

- `/new <agent>` validates the name against the agents this channel may drive
  (its scope — [Channel Owner Gate](channel-owner-gate.md)), records it as the
  thread's sticky choice in `channel_thread_conversations.preferred_agent`, and
  opens a fresh conversation for that thread. The old conversation stays in
  history and on the Chat page. Later conversations in that thread (a bare
  `/new`, or one recreated after deletion) use the sticky agent, falling back
  to the channel's default agent (`application/channel/conversation_spec.py`).
- `/model <name>`, `/model <level>` and `/model <name> <level>` write `model`
  and `effort` into the current conversation's `AgentConfig` and reply that
  they apply from the next turn (`application/channel/model_switch.py`). One
  command carries both because both agents present them as one choice; the
  effort levels are a closed vocabulary no model name uses, so a lone word is
  unambiguous. Any model string is accepted; a name the CLI rejects fails the
  next turn with the CLI's own error, relayed to the chat. The card offers the
  agent's catalogue, then that model's levels. `/model default` clears both,
  returning to the agent's own defaults.
- Model, effort and working directory are sticky per thread beside the agent
  (`preferred_model`, `preferred_effort`, `preferred_cwd` on the same row), so a
  bare `/new` keeps them. A model and effort chosen for one agent do not follow
  a switch to a different agent; the directory does.
- `/dir [path]` opens a fresh conversation in another working directory, only
  one on the channel's own allow-list (`directories` in the channel's
  configuration, each admitting what lies beneath it); with none listed `/dir`
  is off (`application/channel/dir_switch.py`).

Pros: the commands' semantics match what the platform can actually do, so
nothing pretends — an agent or directory switch visibly starts over, a model
switch visibly does not. Per-thread stickiness lets one bot run Claude Code in
one thread and Codex in another. Passthrough never lags a CLI release. The
directory boundary is an explicit operator-approved list.

Cons: an agent switch loses the conversation's context — the new agent starts
cold. A typo in `/model` is discovered one turn late. A thread's sticky choices
are per thread, so a new thread starts on the group's or the channel's defaults
again.

Wins because it is the only option that is honest about the agent session and
cheap about the model namespace, and it keeps the directory switch behind an
allow-list.

### Option B — Every switch opens a new conversation

How it works: `/model` behaves like `/new <agent>`.

Pros: one rule for all three; a conversation's settings never change under it.

Cons: throws away the session to change something the session does not
depend on — the owner who wants a stronger model for the next hard question
would lose the context that makes the question answerable.

Loses because it charges the cost of a structural change for a parametric one.

### Option C — Every switch applies in place, including the agent

How it works: `/new <agent>` re-keys the current conversation to the other agent and
carries on.

Pros: one conversation per thread forever; no "switched, starting fresh"
message.

Cons: there is no re-key path — a Claude Code session cannot be resumed by
Codex, so the "same" conversation would silently start a new upstream session
while showing the old history as if the new agent had seen it. The record of
which agent said what would become wrong.

Loses because an in-place agent switch is a fiction the platform cannot back.

### Option D — Validate model names against a curated list

How it works: Coffer keeps (or reads) a list and refuses `/model` for names
not on it.

Pros: a typo is caught immediately.

Cons: the list must track every CLI release and every account's entitlements;
a name the CLI accepts but the list lacks would be refused by Coffer, which is
worse than a late error. A channel-level model allow-list was built and withdrawn:
picking a model is the agent's business, and which agents a channel may drive
is already its scope.

Loses because Coffer would be the wrong authority over a namespace it does not
own.

### Option E — Sticky agent per channel or per peer, not per thread

How it works: `/new <agent>` sets one preference for the whole chat, stored
on the peer row.

Pros: simpler storage; the choice follows the owner everywhere in that chat.

Cons: a group's threads are separate conversations
([Channel Conversation Identity and
Context](channel-conversation-identity-and-context.md)), and a per-chat
preference makes switching in one thread silently change the agent of every
other thread's next conversation. 
Loses because the preference must live at the same grain as the conversation
it chooses for.

### Option F — Switch the working directory by free path, or by a `/cwd` of named workspaces

How it works: `/dir <any path>` (or a `/cwd <name>` over a list of named
workspaces) opens a fresh conversation wherever the owner points it, or a
channel carries no directory control at all and every turn runs in the
Coffer-managed workspace `~/.coffer/content/workspace` (spec chat "Run Claude Code
and Codex as subprocess providers on the type's one agent").

Pros: no control at all is the smallest surface; a free path needs no
configuration.

Cons: a free path from a remote-reachable chat lets whoever holds the paired
account point the agent at any directory the daemon's user can read or write.
No control at all leaves one bot unable to work in more than one repository.
A separate `/cwd` over named workspaces is the same allow-list as Option A with
a second name for the command.

Loses because the allow-list in Option A is the smallest boundary that keeps
the capability: `/dir` accepts only a path on the channel's own list or beneath
it, and is off until the operator lists one.

### Option G — Model and effort as two commands, or one combined token

How it works: either a separate `/effort <level>` beside `/model <name>`, or a
combined `opus:high` token in one argument.

Pros: a separate command makes each field's setter obvious; a combined token is
one word.

Cons: both agents present the two as one choice, so two commands make the owner
pick a model in one command and its level in another, and the card has to
bridge them anyway. A combined token would be syntax Coffer invents in a
namespace it does not own, and could collide with a model id.

Loses because `/model [name] [level]` with a closed effort vocabulary keeps the
fields separate on the wire (both agents take them as separate fields) while
giving the owner one command.

## Decision

The agent is a structural dimension: `/new <agent>` validates against the
channel's scope, stores the choice per `(channel, chat, thread)` in
`channel_thread_conversations.preferred_agent`, and opens a fresh conversation.
The working directory is structural too: `/dir` opens a fresh conversation, but
only in a directory on the channel's own allow-list. Model and effort are
parametric: `/model <name>`, `/model <level>` and `/model <name> <level>` set
the current conversation's `AgentConfig` and take effect on the next turn,
passing any model name through to the agent's CLI unvalidated; `/model default`
clears both. Model, effort and working directory are sticky per thread beside
the agent, so `/new` keeps them.

Rules a future change must respect:

- A dimension the upstream session depends on is structural and opens a new
  conversation; one read per turn is parametric and applies in place.
- Coffer offers model and effort choices from the agent's own catalogue but
  never refuses a value.
- Sticky choices live at the grain of conversation identity.

## Consequences

- The command roster (`domain/channel/commands.py`) describes `/new` and
  `/dir` as opening a fresh conversation and `/model` as "next turn", and the
  platform command menus are generated from that one roster.
- A web user switching agent on the Chat page and a phone user switching with
  `/new <agent>` get the same behaviour, because both go through conversation
  creation.
- Narrowing a channel's scope takes effect on the next conversation: a sticky
  agent outside the scope falls back to the default.
- An unusable model or effort fails a turn with the CLI's message rather than
  being caught earlier; the next `/model` fixes it in place.
