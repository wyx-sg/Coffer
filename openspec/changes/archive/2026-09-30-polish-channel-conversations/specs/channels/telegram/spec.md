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

### Requirement: Collapse a reply's details
A Telegram reply's `## Details` section MUST arrive collapsed. A rich message
wraps it in `<details><summary>Details</summary>…</details>`, the rich format's
disclosure block, which holds lists, tables and code (an expandable quotation
holds inline text only). The HTML fallback, which has no such element, sends it
as expandable quotations under a bold `Details` line. Every message after a
reply's first is sent silently and opens with `(2/3)`.

#### Scenario: a details section arrives collapsed
- **GIVEN** a reply whose last section is headed `## Details`
- **WHEN** it is delivered as a rich message
- **THEN** that section is inside a `<details>` block summarised `Details`, and on
  the HTML fallback it is an expandable quotation in a numbered, silent message

### Requirement: Show the working status in a direct chat's thinking block
Where the Bot API offers `sendRichMessageDraft` (10.1; private chats only), a
direct chat's draft MUST be a rich draft: the status header ([channels](../spec.md)
"Show a turn's working state as one status line") in the draft-only
`<tg-thinking>` block, the narration and step lines under it as a list, and the
answer written so far as rich markdown. A server that does not know the method
latches it off (see "Read the bot's identity from getMe and latch off
unsupported surfaces") and the same snapshot goes out as the plain
`sendMessageDraft`; a server without rich messages is not asked. Groups have no
draft and keep the silent status message.

#### Scenario: a direct chat's draft shows the status in its thinking block
- **GIVEN** a Telegram server that offers rich drafts, and a direct chat's turn
- **WHEN** its live snapshot is the status block and an answer
- **THEN** one `sendRichMessageDraft` carries the header in `<tg-thinking>`, the
  steps as a list and the answer as markdown, with the stop control, and no
  plain draft is sent
