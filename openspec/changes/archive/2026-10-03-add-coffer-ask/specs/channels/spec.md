## ADDED Requirements

### Requirement: Ask the owner in the chat and take the answer back to the agent
A question raised in a channel conversation (spec chat "Pause a turn on a question
for the owner") MUST go out in that chat, one card per question in order: the
context (a diff as a code block), "❓ <question>", the options — with their
descriptions listed in the body when any has one — as up to four equal buttons,
and "Or reply with your answer.". A multi-select question's buttons MUST toggle a
✓ in place and a **Submit** button sends the choice. A tap MUST be owner-gated
like every card tap. The owner's next text message in that chat or thread while
the question is pending MUST be taken as the answer and not start or queue a
turn. Nothing MUST be posted in the owner's name. Once the question is answered —
in the chat or on the Conversations page — or cancelled, every card of it MUST be
rewritten in place to "✓ Answered: <answer> · HH:MM" ("✓ Answered in Coffer:
<answer> · HH:MM" for a web answer, "Stopped" when cancelled); where the platform
cannot rewrite it, that line is sent as a reply. A long turn that is waiting on a
question pings "❓ Needs you · <elapsed> — <question>" on a surface that pings.

#### Scenario: a tap answers the agent without a message from the owner
- **GIVEN** a SeaTalk card "❓ Apply this change to staging?" with Yes and No
- **WHEN** the owner taps Yes
- **THEN** the agent receives "Yes", the card reads "✓ Answered: Yes · 11:42", and no message is sent as the owner

#### Scenario: a text reply answers the pending question
- **GIVEN** a pending question in the owner's Telegram chat
- **WHEN** the owner sends "only the read replica"
- **THEN** the agent receives that text as the answer and no new turn starts

#### Scenario: an answer given in Coffer rewrites the chat card
- **GIVEN** a pending question shown in Telegram
- **WHEN** the owner answers Yes on the Conversations page
- **THEN** the Telegram message reads "✓ Answered in Coffer: Yes · 11:42" and its keyboard is gone

#### Scenario: a multi-select question is answered with Submit in the chat
- **GIVEN** a SeaTalk card for a multi-select question with three options
- **WHEN** the owner taps two options and then Submit
- **THEN** the two buttons showed a ✓ before Submit, and the agent receives both labels

#### Scenario: a question with described options lists them in the card
- **GIVEN** a question whose options "Yes, apply" and "No, keep" each have a description
- **WHEN** its card goes out
- **THEN** the body lists "• Yes, apply — <description>" and "• No, keep — <description>" under the question, with one button per option and "Or reply with your answer."

#### Scenario: several questions go out one card at a time
- **GIVEN** an ask of two questions in a SeaTalk chat
- **WHEN** the owner answers the first
- **THEN** its card reads "✓ Answered: <answer> · HH:MM" and only then does the second question's card go out

#### Scenario: a non-owner's tap is refused
- **GIVEN** a question card in a paired group
- **WHEN** a member who is not the owner taps an option
- **THEN** the group is told only the bot’s owners can use it and the question stays pending

#### Scenario: stopping a turn rewrites the pending card
- **GIVEN** a pending question card in a chat
- **WHEN** the owner stops the turn
- **THEN** the card reads "Stopped" with its buttons gone

#### Scenario: a long turn that waits on the owner pings
- **GIVEN** a long turn on a persisting surface
- **WHEN** it raises a question
- **THEN** a short message reads "❓ Needs you · <elapsed> — <question>" before the card

## MODIFIED Requirements

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal. The agent receives a short system-prompt note naming **where**
it is — the platform, the chat kind (direct chat, group chat, group thread) and
the channel by its current label — and **what renders there**, in the sentence
or two the running transport declares as its `render_notes` (SeaTalk: bold,
italic, inline code, code fences and lists, but no headings, links or tables;
Telegram: its rich Markdown, tables included). It then asks for a reply shaped
for a phone: do not narrate steps (Coffer already shows the working state); the
first line is the outcome in one sentence, because it becomes the notification;
at most about 15 lines, anything longer under a `## Details` heading; code blocks
under 30 lines, longer logs attached as files; diagrams and charts as PNG files,
never as source; and, when the agent needs a yes or a choice before it goes on,
to call `coffer__ask` (see "Ask the owner in the chat and take the answer back
to the agent").
Concise never drops evidence — an investigation's key log lines, error messages
and IDs are quoted verbatim — and the agent is told it cannot click permission
or confirmation dialogs on the user's computer. Web-UI turns are unaffected —
the note rides only on a conversation whose `channel_uid` is set. A channel that
has been deleted, or is not running, still gets the note, saying less.

#### Scenario: the channel-driven agent is told it is on a chat channel
- **GIVEN** a channel-originated conversation
- **WHEN** a turn is driven from the channel
- **THEN** the agent receives a system-prompt note naming the platform, the chat
  kind and the channel, telling it not to narrate its steps, to quote an
  investigation's key evidence verbatim, and that it cannot click the user's OS
  dialogs, while a web-UI conversation gets no such note

#### Scenario: the note lists what renders on the platform the turn is on
- **GIVEN** a SeaTalk group-thread conversation on a running channel
- **WHEN** its turn's note is composed
- **THEN** it says the turn is in a SeaTalk group thread and that headings, links
  and tables do not render there (write one bullet per row)

#### Scenario: the note asks for the answer's shape
- **WHEN** a channel turn's note is composed
- **THEN** it asks for the outcome in one first sentence, long content under
  `## Details`, diagrams as PNG files, and a `coffer__ask` call when the agent
  needs the owner's answer

## REMOVED Requirements

### Requirement: Turn a question for the owner into buttons
**Reason**: The `NEEDS YOU:` last-line sentinel is replaced by `coffer__ask` (and Claude Code's `AskUserQuestion`), which pauses the turn and returns the answer to the agent instead of sending the owner's tap as a message.
**Migration**: Agents are told to call `coffer__ask`; a historical reply ending on `NEEDS YOU:` stays as text.
