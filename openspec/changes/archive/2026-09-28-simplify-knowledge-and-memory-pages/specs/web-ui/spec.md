## MODIFIED Requirements

### Requirement: Show reach as a labelled button on every list and detail page
Every list surface of a scoped kind MUST carry a **reach** column — named for what it holds, not
for the on/off flag it replaced: one button labelled with the answer it already
holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a
scope narrowed to nobody — so the reader learns the reach by reading it rather
than by comparing which of three side-by-side segments looks pressed. Every
detail page MUST carry the same button in its header. A kind that declares no
scope — an agent, a knowledge collection, a memory partition — MUST carry neither
the column, the button, nor a bulk reach action; see "Offer reach as one choice in a panel".

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the knowledge and memory list pages and one collection's and one partition's page
- **WHEN** each renders
- **THEN** no list has a Status or Reach column and no header carries a reach or status button

### Requirement: Offer reach as one choice in a panel
The button MUST open a panel where "who does this reach?" is a single choice
between Disabled, Every agent and Only selected agents, the last over the
scope's list of agents.

#### Scenario: the reach panel offers the reach states as one choice
- **GIVEN** a resource of a scoped kind
- **WHEN** its reach panel is opened
- **THEN** it offers Disabled, Every agent and Only selected agents with its current state chosen
- **AND** choosing Only selected agents shows the list of agents to pick from

### Requirement: Filter lists by the same reach states
For a scoped kind, the list's reach filter MUST offer the same states the panel
does, rather than a bare enabled / disabled pair, and the column, the filter and
the button MUST all use the word *reach*, because they are all asking the one
question.

#### Scenario: the reach filter offers the panel's states under the reach name
- **GIVEN** a list surface of a scoped kind
- **WHEN** its reach filter is built
- **THEN** it offers Disabled, Every agent and Only selected agents, labelled as the reach button labels them
- **AND** the filter is headed Reach, the word the column and the button use
