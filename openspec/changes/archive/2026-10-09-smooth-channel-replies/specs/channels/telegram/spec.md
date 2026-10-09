## MODIFIED Requirements

### Requirement: Use a deleted status message as the live scaffolding
Telegram's live surface MUST be **scaffolding**, not the reply: a status message
that is edited as the turn runs and **deleted** before the real answer is sent
([channels](../spec.md) "Show a turn's progress on one live surface"). It opens
only once the turn has run past the update interval — either tool activity opens it or the reply
text does — so a reply that finishes sooner opens none and there is no create →
delete → resend flicker; the 👀 receipt reaction ([channels](../spec.md) "Acknowledge receipt and completion by capability") has
already said the message was heard. When the turn ends, the status message is
deleted and the final reply is sent HTML-rendered and paragraph-chunked.

#### Scenario: reply text streams into the editable status message as it arrives
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** the agent's reply text arrives in deltas during a turn
- **THEN** the single status message shows tool-progress lines first, then is
  edited in place with the accumulating reply text (plain, not HTML) so the user
  watches the answer materialize; on finish the status message is deleted and the
  final reply is sent once (HTML-rendered and paragraph-chunked)

#### Scenario: a slow text-only reply streams into a status message
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** a text-only turn (no tool calls) keeps producing reply text past the
  transport's update interval
- **THEN** a status message is opened with the streaming reply text and edited in
  place as the answer grows, then deleted on finish while the final reply is sent
  once

#### Scenario: a fast text-only reply opens no status message
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** a text-only turn completes within the transport's update interval
- **THEN** no status message is opened (no create → delete → resend flicker) — only
  the single final reply is sent
