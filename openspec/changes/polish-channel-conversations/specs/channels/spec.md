## ADDED Requirements

### Requirement: Show a turn's working state as one status line
While a turn runs, its live surface MUST open with one status block the reader
can take in at a glance: a header saying that the turn is working, for how long,
and how many steps it has taken (`⏳ Working · 2m 14s · 7 steps`, with the
failed count when there is one); the agent's latest narration as a `💬` line;
and the newest three step lines, older ones collapsed into `+N earlier`. The
answer written so far follows under a rule. The header MUST keep ticking while
nothing else happens — a long silent tool still shows time passing — on the
cadence the live surfaces already keep alive at, so the tick costs no extra
traffic.

Text the agent writes before a tool call is narration ("Let me check the
logs"): once the tool call arrives it moves up into the `💬` line and the answer
tail shows only text written after the last tool call. The final reply keeps
every segment the agent wrote, with a paragraph break between the text either
side of a tool call, so two sentences never run together.

A channel setting `show_steps` (default on) hides the step lines and keeps the
header and narration — useful in a busy group. It is edited on the Channels
page and with `coffer channel add|edit --show-steps/--hide-steps`.

A transport that must shorten a snapshot to its own limit clips the answer's
oldest words and keeps the status block whole; only a limit too small for the
block drops the step lines, then the header.

#### Scenario: a long turn shows elapsed time and step count in one status line
- **GIVEN** a turn that has run for 2 minutes 14 seconds and called eight tools,
  one of which failed
- **WHEN** its status block is drawn
- **THEN** the header reads `⏳ Working · 2m 14s · 8 steps (1 failed)`, followed by
  `+5 earlier` and the newest three step lines

#### Scenario: narration between tool calls moves to the status line
- **GIVEN** a turn whose agent writes a sentence and then calls a tool
- **WHEN** the tool call arrives and the agent then writes its answer
- **THEN** the sentence appears as the status block's `💬` line and the answer
  alone grows under the rule

#### Scenario: the status line keeps ticking during a silent tool
- **GIVEN** a turn whose tool runs for minutes without producing an event
- **WHEN** the live surface is next redrawn on its cadence
- **THEN** the header shows the new elapsed time

#### Scenario: the final reply keeps every paragraph the agent wrote
- **GIVEN** a turn whose agent wrote text, called a tool, then wrote more text
- **WHEN** the reply is delivered
- **THEN** it holds both texts with a paragraph break between them

#### Scenario: hiding steps keeps only the header
- **GIVEN** a channel with `show_steps` off
- **WHEN** a turn calls a tool
- **THEN** the status block shows the header and narration but no step line

#### Scenario: the step lines are hidden from the command line
- **WHEN** the owner runs `coffer channel edit <name> --hide-steps`, then `--show-steps`
- **THEN** the channel's `show_steps` setting is off, then on again

## MODIFIED Requirements

### Requirement: Grow a reply in place on one live surface
A reply MUST grow in place, by whatever live-text mechanism the platform has —
chosen from the adapter's declared capabilities, never its type — so the answer
never arrives as a run of fragments. The capability the core asks about is
`supports_live_text` ("is there a surface I can keep updating while this turn
runs?"), NOT `supports_edit` ("can a delivered message be rewritten?"). The two
flags are set independently, because a transport can have a live surface while
being unable to rewrite a delivered message at all; keying the strategy on
`supports_edit` silently denied such a transport the live experience it does
support, and its replies arrived as several chunked messages at the end of the
turn.

A turn keeps exactly ONE live surface. WHEN it opens depends on whether that
surface becomes the reply or is scaffolding thrown away at the end, which the
adapter declares as `live_text_persists`. Where it persists, the surface opens
the moment the turn starts and says so — its status line (see "Show a turn's
working state as one status line") is an acknowledgement the user can see,
because the wait between a message and an answer is otherwise the whole of what
they get, and on a long turn it reads as the bot having missed them. That
acknowledgement costs no extra message: the reply is the same one, rewritten in
place. Where the surface is scaffolding, it opens only once the turn has run
past the update interval — either tool activity opens it or the reply text does
— so a reply that finishes sooner opens none, avoiding a create → delete →
resend flicker. A turn still thinking in silence opens it on the status line's
first tick.

The cadence of updates belongs to the TRANSPORT, which alone knows its own
limits: the core offers every snapshot and each surface buffers to what it can
sustain. A throttle added by the core on top hides that buffer completely and
makes a stream arrive a paragraph at a time. Interim snapshots are clipped to
the platform's per-message limit and their formatting characters are ESCAPED, so
a long or half-written-markdown preview never breaks a platform parser or
exceeds the cap. They are escaped rather than sent as plain text because the
message has to be able to carry an @mention from the moment it is created (see
"Mention the asker in a group answer"), and a mention is only a name in rich
text.

How a surface *ends* is the transport's business, and each child spec states its
own. A transport with no live surface at all posts no interim traffic; its final
reply is the whole signal. All best-effort — a failed update, close, or
heartbeat never breaks the turn.

#### Scenario: the streamed reply preview is clipped to the platform limit
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** the accumulating reply text grows past the platform's per-message limit
- **THEN** each interim edit is clipped to that limit (keeping the most recent
  text behind a leading ellipsis) so the edit never fails, while the final reply
  carries the full text

#### Scenario: a transport with no live-text surface posts no interim status message
- **GIVEN** a paired channel on an adapter that can neither edit nor stream and
  declares no typing signal either, in a group/thread
- **WHEN** a turn runs
- **THEN** no interim signal is posted at all — only the final chunked reply
  lands in the originating group/thread

#### Scenario: a reply grows in place on a transport that streams but cannot edit
- **GIVEN** a paired channel on an adapter that cannot edit or delete a message
  but can stream one, in a group/thread
- **WHEN** a turn runs tools and then writes its reply
- **THEN** exactly ONE message reaches the chat and grows in place — tool
  progress first, then the accumulating reply — and it finishes carrying the
  final reply, so nothing is sent twice and the answer never arrives as
  fragments

### Requirement: Acknowledge receipt and completion by capability
Receipt and progress MUST be acknowledged, capability-gated (never by transport
type). On a `supports_reactions` transport the owner's own message carries one
reaction that follows the turn: a **received** mark the moment it arrives (a
message queued behind a running turn keeps it), a **working** mark when its turn
starts, and one of **done** (a clean finish, including one that ends on a
question for the owner), **failed** (an error or the tool-iteration limit) or
**stopped** (interrupted) when it ends. Which emoji each stage uses is the
transport's declared `reactions` set, because a platform may accept only a fixed
list — each child spec names its own. A reaction replaces the previous one, so
the message shows where the turn is now. A transport without reactions uses its
typing/working signal as the receipt-and-progress cue instead. All best-effort —
a failed mark never breaks the turn.

#### Scenario: receipt and completion are acked with reactions where supported
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner sends a message that drives a clean turn
- **THEN** the received mark is set on the owner's own message immediately on
  receipt, the working mark when the turn starts, and the done mark on
  completion, all targeting that inbound message id

#### Scenario: a transport without reaction support attempts no reaction
- **GIVEN** a paired channel on an adapter that does not support reactions,
  whose receipt-and-progress cue is the typing signal
- **WHEN** the owner sends a message that drives a turn
- **THEN** no reaction is attempted, while the turn still runs and replies normally

#### Scenario: a failed reaction never breaks the turn
- **GIVEN** a paired channel on a reaction-supporting adapter whose set_reaction fails
- **WHEN** the owner sends a message that drives a turn
- **THEN** the reply is still delivered — the best-effort reaction is suppressed

#### Scenario: a failed turn ends on the failed mark
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner's message drives a turn that errors
- **THEN** the message's marks are received, working, then failed — never done

#### Scenario: a turn's marks follow it from receipt to its end
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner's message drives a turn that is interrupted
- **THEN** the message's marks are received, working, then stopped
