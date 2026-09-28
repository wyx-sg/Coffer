## MODIFIED Requirements

### Requirement: Show reach as a labelled button on every list and detail page
Every list surface of a scoped kind MUST carry a **reach** column — named for what it holds, not
for the on/off flag it replaced: one button labelled with the answer it already
holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a
scope narrowed to nobody — so the reader learns the reach by reading it rather
than by comparing which of three side-by-side segments looks pressed. Every
detail page MUST carry the same button in its header. A kind that declares no
scope — an agent — MUST head the same column **Status** instead, and its
button MUST read "Enabled" or "Disabled", because enabled or disabled is the
whole of what it reports; see "Offer reach as one choice in a panel". A kind whose
resources cannot be disabled — knowledge, memory — MUST carry neither the column,
the button, nor a bulk enable / disable action.

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the knowledge and memory list pages and one collection's and one partition's page
- **WHEN** each renders
- **THEN** no list has a Status or Reach column and no header carries a reach or status button
