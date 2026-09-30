## MODIFIED Requirements

### Requirement: Degrade card rewrites outside SeaTalk's update window
A card rewrite ([channels](../spec.md) "Switch the agent with /new", [channels](../spec.md) "Offer choices and actions as owner-gated cards") reaches only
**interactive cards, only within 7 days, only for the sending bot**. Outside that
window the platform refuses the update, and the card MUST degrade exactly as the
parent requires: a cosmetic rewrite after a choice is dropped, while a page turn
the user asked for is posted as a fresh card, or as plain text if that is refused
too.

#### Scenario: a refused card update drops a choice rewrite but reposts a page turn
- **GIVEN** a SeaTalk card whose in-place update the platform refuses
- **WHEN** the owner applies a choice on it, and separately asks for its next page
- **THEN** the choice is applied with no replacement card posted
- **AND** the requested page arrives as a fresh card
