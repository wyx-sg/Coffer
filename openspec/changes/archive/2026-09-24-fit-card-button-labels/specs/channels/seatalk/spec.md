## MODIFIED Requirements

### Requirement: Build cards in SeaTalk's published element shape
The card payload MUST follow SeaTalk's published shape: **one flat `elements`
array in which a button is itself an element**
(`{"element_type": "button", "button": {...}}`) — not a `buttons` array beside
it. The published per-element limits are a card of at most **3 titles, 5
descriptions, 5 buttons, 3 button groups and 3 images**, with a title of at most
120 characters and a description of at most 1000. Buttons are therefore laid out
in **button groups** (an element holding up to three buttons on one line) rather
than one element each: the parent's six-button bound ([channels](../spec.md) "Offer command choices as owner-gated selection cards")
always fits in the three group slots and reads as rows rather than a six-high
stack. A row splits the card's width evenly, so how many buttons share a row
depends on their labels: a row takes the next button only while every label in
it fits the width a row of that size leaves, and a long label gets a row of its
own. When that would need more than three rows, the buttons are spread evenly
over three. Title and description text are clamped to their documented lengths,
so a long body degrades to a truncated card instead of a refused one.

#### Scenario: a six-button card is laid out as two button groups with clamped text
- **GIVEN** a selection card with six short-labelled buttons, a title over 120 characters and a body over 1000 characters
- **WHEN** it is built as a SeaTalk interactive card
- **THEN** the payload is one flat `elements` array whose buttons sit in two button-group elements of three
- **AND** the title is truncated to 120 characters and the description to 1000

#### Scenario: a long button label gets a row of its own
- **GIVEN** a selection card whose buttons include a label too wide to share a row, such as "Claude Code" beside "Codex"
- **WHEN** it is built as a SeaTalk interactive card
- **THEN** that button sits alone in its button group, while short labels still share one
