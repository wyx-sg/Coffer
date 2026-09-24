# Channel Switches: the Agent Opens a New Conversation, Model and Effort Apply Next Turn

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: spec channels ("Switch the conversation's agent from chat", "Switch the model and reasoning effort from chat", "Drive every managed agent from one bot", "Key conversation identity by channel, chat and thread", "Offer command choices as owner-gated selection cards");
spec chat ("Record the agent on each conversation", "Let the owner set agent, model and reasoning level");
[Channel Conversation Identity and Context](channel-conversation-identity-and-context.md), [Channel Owner Gate](channel-owner-gate.md),
[Driving Agents Through the SDK and App-Server](driving-agents-through-sdk-and-app-server.md), [Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md);
PRs #245, #385

## Context

From a phone the owner needs to change three things about the agent they are
talking to: **which agent** (Claude Code or Codex), **which model**, and **how
hard it reasons** (effort). The commands are `/agent`, `/model` and `/effort`,
each with a selection card where the platform has buttons.

These three dimensions are not the same kind of thing to the turn platform:

- A conversation **records its `agent_key` for life**. Its upstream session —
  a Claude Code session id or a Codex thread id, stored as
  `AgentConfig.session_id` — belongs to that agent's CLI and cannot be resumed
  by the other. The working directory is fixed with it.
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
  account may run.
- **A group has several threads**, and the owner may want different agents in
  different threads of the same group.

## Options Considered

### Option A — Structural vs parametric: `/agent` opens a fresh conversation and sticks per thread; `/model` and `/effort` apply to the next turn of the same conversation, passed through unchecked (chosen)

- `/agent <key>` validates the key against the agents this channel may drive
  (its scope — [Channel Owner Gate](channel-owner-gate.md)), records it as the
  thread's sticky choice in `channel_thread_conversations.preferred_agent`, and
  opens a fresh conversation for that thread. The old conversation stays in
  history and on the Chat page. Later conversations in that thread (`/new`,
  or one recreated after deletion) use the sticky agent, falling back to the
  channel's default agent (`application/channel/conversation_spec.py`).
- `/model <name>` and `/effort <level>` write `model` / `effort` into the
  current conversation's `AgentConfig` and reply that it applies from the next
  turn (`application/channel/model_switch.py`,
  `application/channel/effort_switch.py`). Any string is accepted; a name the
  CLI rejects fails the next turn with the CLI's own error, relayed to the
  chat. The card offers the agent's catalogue and marks the current value.
  There is no "unset" form: `/new` returns to the agent's own defaults.
- Effort is its own command rather than a suffix on the model name because
  both agents take it as a separate field; a combined `opus:high` syntax would
  be invented by Coffer in a namespace it does not own.

Pros: the commands' semantics match what the platform can actually do, so
nothing pretends — an agent switch visibly starts over, a model switch visibly
does not. Per-thread stickiness lets one bot run Claude Code in one thread and
Codex in another. Passthrough never lags a CLI release.

Cons: an agent switch loses the conversation's context — the new agent starts
cold. A typo in `/model` is discovered one turn late. A thread's sticky agent
is per thread, so a new thread starts on the channel default again.

Wins because it is the only option that is honest about the agent session and
cheap about the model namespace.

### Option B — Every switch opens a new conversation

How it works: `/model` and `/effort` behave like `/agent`.

Pros: one rule for all three; a conversation's settings never change under it.

Cons: throws away the session to change something the session does not
depend on — the owner who wants a stronger model for the next hard question
would lose the context that makes the question answerable.

Loses because it charges the cost of a structural change for a parametric one.

### Option C — Every switch applies in place, including the agent

How it works: `/agent` re-keys the current conversation to the other agent and
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
worse than a late error. A channel-level model allow-list existed once and was
removed (migration `0068_drop_channel_model_curation`): picking a model is the
agent's business, and which agents a channel may drive is already its scope.

Loses because Coffer would be the wrong authority over a namespace it does not
own.

### Option E — Sticky agent per channel or per peer, not per thread

How it works: `/agent` sets one preference for the whole chat (the design
first shipped stored it on the peer row, `channel_peers.preferred_agent`).

Pros: simpler storage; the choice follows the owner everywhere in that chat.

Cons: a group's threads are separate conversations
([Channel Conversation Identity and
Context](channel-conversation-identity-and-context.md)), and a per-chat
preference makes switching in one thread silently change the agent of every
other thread's next conversation. Once conversation identity moved to
`(channel, chat, thread)`, the peer column stopped being written, and
migration `0084` dropped it.

Loses because the preference must live at the same grain as the conversation
it chooses for.

### Option F — A `/cwd` switch among operator-approved workspaces

How it works: a channel carries a list of named workspaces and `/cwd <name>`
opens a fresh conversation in another one (structural, like `/agent`).

Pros: one bot could work in several repositories.

Cons: a remote-reachable entrypoint choosing an agent's working directory is a
boundary that needs its own allow-list, validation and UI, for a need that
never materialised. It was built and withdrawn in 2026-06: channel turns run in
the Coffer-managed workspace `~/.coffer/workspace` (spec chat "Ship Claude Code
and Codex subprocess providers").

Loses because the owner can already point an agent at any directory from the
agent itself; the channel does not need to be a second way.

## Decision

The agent is a structural dimension: `/agent` validates against the channel's
scope, stores the choice per `(channel, chat, thread)` in
`channel_thread_conversations.preferred_agent`, and opens a fresh conversation.
Model and effort are parametric: `/model` and `/effort` set the current
conversation's `AgentConfig` and take effect on the next turn, passing any
value through to the agent's CLI unvalidated. There is no `/cwd`.

Rules a future change must respect:

- A dimension the upstream session depends on is structural and opens a new
  conversation; one read per turn is parametric and applies in place.
- Coffer offers model and effort choices from the agent's own catalogue but
  never refuses a value.
- Sticky choices live at the grain of conversation identity.

## Consequences

- The command roster (`domain/channel/commands.py`) describes `/agent` as
  "opens a fresh conversation" and `/model`, `/effort` as "next turn", and the
  platform command menus are generated from that one roster.
- A web user switching agent on the Chat page and a phone user switching with
  `/agent` get the same behaviour, because both go through conversation
  creation.
- Narrowing a channel's scope takes effect on the next conversation: a sticky
  agent outside the scope falls back to the default.
- An unusable model or effort fails a turn with the CLI's message rather than
  being caught earlier; the next `/model` fixes it in place.
