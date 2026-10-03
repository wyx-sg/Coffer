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

## REMOVED Requirements

### Requirement: Turn a question for the owner into buttons
**Reason**: The `NEEDS YOU:` last-line sentinel is replaced by `coffer__ask` (and Claude Code's `AskUserQuestion`), which pauses the turn and returns the answer to the agent instead of sending the owner's tap as a message.
**Migration**: Agents are told to call `coffer__ask`; a historical reply ending on `NEEDS YOU:` stays as text.
