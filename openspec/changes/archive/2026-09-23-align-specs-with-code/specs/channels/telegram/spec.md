## MODIFIED Requirements

### Requirement: Render selection cards as inline keyboards
A selection card ([channels](../spec.md) "Offer command choices as owner-gated selection cards") MUST be rendered as an **inline
keyboard**, and a tap arrives as a callback query carrying the button's opaque
value. Telegram has no title element of its own, so the card's title MUST be
carried in the text: as a **heading** of the rich message when the Bot API
server offers rich messages, and as a **bold first line** on the HTML path
beneath it. Every callback value Coffer emits fits the **64-byte callback
budget** the Bot API allows; a choice whose value would not fit is left off the
card.

#### Scenario: a selection card becomes an inline keyboard with a bold title line
- **GIVEN** a selection card with a title and several choices
- **WHEN** it is rendered for telegram on the HTML path
- **THEN** the message opens with the title as a bold first line and carries an inline keyboard of the choices
- **AND** every button's callback data is at most 64 bytes

#### Scenario: a selection card on a rich-message server takes its title as a heading
- **GIVEN** a Bot API server that offers rich messages
- **WHEN** a selection card with a title is sent
- **THEN** it is sent as one rich message whose markdown opens with the title as a heading
- **AND** it carries the inline keyboard of the choices
