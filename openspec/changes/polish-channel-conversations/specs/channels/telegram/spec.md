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
