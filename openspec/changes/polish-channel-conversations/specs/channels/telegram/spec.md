## ADDED Requirements

### Requirement: Mark a turn's progress with reactions from Telegram's list
Telegram's `setMessageReaction` accepts only the fixed emoji list under
`ReactionTypeEmoji` in the Bot API; any other emoji is refused. The Telegram
transport MUST declare its progress marks from that list — 👀 received, 👨‍💻
working, 👌 done, 😢 failed, 🤷 stopped — and MUST refuse an emoji outside it
before calling the platform, so a mark can never fail invisibly the way ✅ did.

#### Scenario: every mark is on the Bot API's reaction list
- **GIVEN** the Telegram transport's declared reaction set
- **WHEN** it is compared with the Bot API's allowed reaction emoji
- **THEN** every mark is on the list, and an emoji that is not (✅, ❌) is refused
  before any call is made

### Requirement: Mention the asker by name in a group answer
Every Telegram group answer MUST open with a real mention of the asker: an
inline mention link `[<name>](tg://user?id=<from.id>)`, which rich messages and
the HTML subset both render as a mention that notifies — it works for a member
with no username. The id is the sender's `from.id`; the name is their display
name. A direct answer carries none, and the silent status message carries none
(it is deleted before the answer).

#### Scenario: a group answer mentions the asker by name
- **GIVEN** a Telegram group message from a member named Alex with id 4242
- **WHEN** the turn's answer is delivered
- **THEN** it opens with `[Alex](tg://user?id=4242)`, and the HTML fallback renders
  that as a `tg://user?id=4242` link named Alex
