## ADDED Requirements

### Requirement: Draw Mermaid diagrams in every Markdown preview
Every place the UI renders Markdown — a knowledge file, a skill's file, a
memory, an agent's file, and conversation and channel text — MUST draw a fenced
block whose language is `mermaid` as its diagram, for every diagram type the
bundled Mermaid draws, in the palette of the current light or dark theme.
Mermaid MUST be loaded only when a page holds such a block, and MUST run with
its strict security level, so a diagram never runs code, opens a link by
itself or renders HTML labels. A block that cannot be drawn MUST show its
source as a code block, with one line saying the diagram could not be drawn.
Nothing is sent anywhere to draw a diagram. Other fenced blocks are unchanged.

#### Scenario: a mermaid block shows as its diagram
- **GIVEN** a Markdown file holding a ```` ```mermaid ```` flowchart
- **WHEN** it is shown in Preview
- **THEN** the diagram is drawn in place of the block, and Mermaid was set up with its strict security level

#### Scenario: a diagram that cannot be drawn shows its source
- **GIVEN** a ```` ```mermaid ```` block with a syntax error
- **WHEN** it is shown in Preview
- **THEN** its source shows as a code block under a line saying the diagram could not be drawn

#### Scenario: conversation text draws diagrams and keeps Copy on code
- **GIVEN** an agent reply holding a ```` ```mermaid ```` block and a shell block
- **WHEN** the reply is shown
- **THEN** the diagram is drawn, and only the shell block carries a Copy button
