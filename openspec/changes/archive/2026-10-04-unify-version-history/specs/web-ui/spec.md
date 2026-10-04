## ADDED Requirements

### Requirement: Show every version history as one split
Every page that lists the versions of a file or folder with what each changed — a skill's History tab
and a knowledge document's History tab — MUST lay it out the same way: one bordered card split in two
by a divider, the versions on the left (newest first, the newest marked **Current**, each with its
writer and when) and, on the right, the chosen version's diff file by file, each file under its path,
operation and line counts. The divider MUST move both ways: the list narrows to 160 px and widens to
half the card, and the width is remembered per page. Every diff in the web UI that shows a file's
changed lines — these histories, a knowledge change or pass, a stale-save compare, a skill restore,
copy or update review, and a change preview — MUST be drawn by one renderer: old and new line
numbers, a sign, additions and deletions on their colour, hunk headers muted, and a long line wrapped
at a word boundary with a ↳ on its continuation rows, never cut off.

#### Scenario: a history list narrows below its starting width
- **GIVEN** a skill with two versions, its History tab open
- **WHEN** the user moves the divider left
- **THEN** the version list narrows below the width it opened at, down to 160 px, and the chosen version's diff stays on the right with long lines wrapped

## MODIFIED Requirements

### Requirement: Show a knowledge document's history on its History tab
A knowledge document's pane MUST carry two tabs, **Document** (the default) and **History**, neither
with a count. History is the version-history split of "Show every version history as one split": the
document's versions on the left, newest first — who wrote each (the user, Coffer's curation naming the
agent whose item it curated, or sync), when, and its added and removed line counts — and the chosen
version on the right, the newest chosen when the tab opens. The right side MUST carry a switch between
**Changes in this version** (against the one before) and **Compare with current**, **Restore this
version** on every version but the current one, which writes a new version rather than rewriting the
past (spec [knowledge](../knowledge/spec.md) "Keep every document's history and undo a pass as a
whole"), a **See the pass** link on a curation's version, and the diff. A history that cannot be read
MUST say so in one **Load error** row inside the tab — *Couldn't load the history*, the reason,
**Retry** and **Open Activity** — leaving the Document tab working; without git the row is *History
needs git* (see "Offer the hand-off a knowledge refusal carries beside it").

#### Scenario: the history tab lists versions with their writers
- **GIVEN** a document the user created, that curation then changed from a Codex item
- **WHEN** the user opens its History tab and chooses the older version's row
- **THEN** the tab lists both versions newest first with their writers, its diff shows on the right beside the list, and Restore this version is offered on it and not on the current version
- **AND** restoring it writes it back as a new version

#### Scenario: a history that fails to load leaves the document readable
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab
- **THEN** the tab shows one Load error row with Retry and Open Activity, and the Document tab still renders
