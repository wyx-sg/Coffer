## ADDED Requirements

### Requirement: Draw every colour from the theme tokens
Every colour the web UI renders MUST come from a theme token: a role such as
surface, raised surface, border, text, muted text, accent, success, warning or
danger, defined once for the light theme and once for the dark theme in the one
stylesheet that holds the tokens. A component MUST ask for a role, never for a
colour value, so that switching theme re-colours every surface. Colour is
reserved for state and action: the accent marks the primary action, focus and
selection only, and the four status colours are never borrowed for anything
else. A colour literal — a hex value, an `rgb()` or `hsl()` value, or a Tailwind
palette class — anywhere in the frontend source outside the token stylesheet
MUST fail the lint gate.

#### Scenario: a colour literal outside the tokens fails the lint gate
- **GIVEN** a frontend source file other than the token stylesheet that sets a hex colour, an `rgb()` / `hsl()` value or a Tailwind palette class such as `bg-red-500`
- **WHEN** `make lint` runs
- **THEN** the colour gate fails, naming the file, the line and the literal
- **AND** a class that names a role (`bg-surface-raised`, `text-danger`) and an `rgb(var(--role))` read pass

#### Scenario: every colour role is defined for both themes
- **GIVEN** the token stylesheet
- **WHEN** its light and dark definitions are compared
- **THEN** every colour role the light theme defines is defined again for the dark theme

### Requirement: Follow the system theme with a per-viewer override
The UI MUST render in light or dark. By default it MUST follow the operating
system's appearance and follow it live, without a reload, when the system
switches. The viewer MUST be able to override it with a System / Light / Dark
choice on the General tab of Settings; the choice is a display preference of
this browser, persisted in `localStorage` under `coffer.theme`, and never sent to
the daemon. The resolved theme MUST be exposed as `data-theme="light"` or
`data-theme="dark"` on the document's root element.

#### Scenario: the theme follows the system appearance live
- **GIVEN** no stored theme choice and a system in light mode
- **WHEN** the page loads and the system then switches to dark and back
- **THEN** the root element reads `data-theme="light"`, then `dark`, then `light`, with no reload

#### Scenario: a manual theme choice overrides the system and persists
- **GIVEN** a system in light mode
- **WHEN** the viewer chooses Dark
- **THEN** the root element reads `data-theme="dark"`, `coffer.theme` holds `dark`, and a system switch no longer changes the theme
- **AND** after a reload the page opens dark, and choosing System again clears the key and follows the system

#### Scenario: the General tab offers the theme choice
- **GIVEN** the Settings General tab
- **WHEN** it renders
- **THEN** it offers the theme as one choice of System, Light and Dark with the current preference chosen
- **AND** picking one applies it at once, with no Save button

### Requirement: Ship the interface fonts with the app
The interface face (Figtree) and the identifier face (JetBrains Mono) MUST be
bundled into the web build and loaded from the app's own origin, never from a
font service, so the desktop shell's content security policy (`font-src 'self'
data:`) never blocks them and the UI looks the same offline. The interface MUST
run on a 13px base size, with anything a user could paste into a terminal —
paths, ports, tool names, environment keys, commit ids — set in the identifier
face.

#### Scenario: the interface fonts load from the app's own origin
- **GIVEN** the token stylesheet's font declarations
- **WHEN** the web build is produced
- **THEN** every font source is a file bundled with the build, and none is an absolute URL to another host
- **AND** the default face is Figtree at 13px, with JetBrains Mono as the monospace face

### Requirement: Show an agent by its official mark
Wherever the UI names an agent in a compact form, it MUST show the agent's
official mark on a neutral tile — Claude Code as the Claude Spark, Codex as the
OpenAI Blossom beside the word "Codex" — and never letters. An agent type Coffer
does not support MUST get a neutral agent glyph on the same tile. Every agent
sits on the same neutral tile, so colour outside the mark stays reserved for
state: a healthy agent's badge is plain, and only a problem adds a status mark.
A badge shown without its name MUST carry the name, and its state when it has
one, in its accessible label and its tooltip.

#### Scenario: a supported agent is shown by its official mark
- **GIVEN** a Claude Code agent and a Codex agent
- **WHEN** each renders as an agent badge
- **THEN** Claude Code shows the Claude Spark mark and Codex the OpenAI Blossom mark, on the same neutral tile, and neither shows letters
- **AND** a badge without a visible name is labelled with the agent's name and state, such as "Codex, not connected to Coffer"

#### Scenario: an agent Coffer does not support gets the neutral glyph
- **GIVEN** an agent type other than Claude Code or Codex
- **WHEN** it renders as an agent badge
- **THEN** the badge shows the neutral agent glyph on the neutral tile, labelled with the agent's name

### Requirement: Pair every status colour with its word
A status MUST never be conveyed by colour alone: the dot MUST always sit beside
the word it means (Running, Degraded, Failing, Disabled), so the state survives
colour-blindness and a greyscale screenshot. A healthy status reads quietly —
its word in muted text — while a problem colours its word with its status colour.

#### Scenario: a status is a dot beside its word
- **GIVEN** statuses of each tone: running, degraded, failing and disabled
- **WHEN** each renders
- **THEN** each shows a dot and its word together, the dot carrying the status colour
- **AND** the running word is set in muted text while the degraded and failing words take their status colour

### Requirement: Preview a write before it lands
Before Coffer writes into files it does not own on the user's behalf — repairing
drift, connecting an agent, resolving a sync conflict — the UI MUST be able to
show the change first, in one shared preview: the changes grouped by agent and
by file, each file with its operation (add, modify, remove) and its added and
removed line counts, a plain-words summary of what will happen per agent, and
the diff of every changed file. The preview MUST show each of its states —
computing, nothing to change, ready, applying, applied, and failed partway. When
some changes fail, the preview MUST stay open, say which changes were applied,
name the reason each failed one failed, and offer to retry only the failed ones.

#### Scenario: the change preview groups a write by agent and file
- **GIVEN** a planned write of four changes across two agents' files
- **WHEN** the change preview renders it
- **THEN** it summarises the four changes by operation, lists each file under its agent with its operation and line counts, and shows each changed file's diff
- **AND** its primary action reads "Apply 4 changes"

#### Scenario: a write that failed partway retries only what failed
- **GIVEN** a change preview whose apply left one of four changes failed
- **WHEN** it renders the result
- **THEN** it stays open, says the other three were applied, and shows the failed change's reason under its path
- **AND** its retry action names and retries only the one failed change

### Requirement: Show a chosen reach by its agents' badges
A reach control whose resource reaches only chosen agents MUST show each chosen
agent's badge beside its label, in the order of the Agents page, so the reader
sees who has it without opening the panel; the label and the panel's choices are
unchanged. The panel MUST show each agent of the pick-list by its badge and name.

#### Scenario: a reach narrowed to chosen agents shows their badges
- **GIVEN** a resource whose reach names one Claude Code agent
- **WHEN** its reach button renders
- **THEN** it reads the chosen reach's label with the Claude Code badge beside it
- **AND** its panel lists each agent by its badge and name

### Requirement: Mark the app with the Coffer logo
The app MUST carry the Coffer mark — an open rounded square drawn with the
navigation icons' pen around a single accent dot — as the sidebar's brand and
as the browser tab's icon, drawn in theme colours so it reads on light and dark.

#### Scenario: the sidebar carries the Coffer mark
- **GIVEN** the app shell
- **WHEN** the sidebar renders, expanded or collapsed
- **THEN** its brand shows the Coffer mark, labelled "Coffer"
- **AND** the document declares the Coffer mark as its icon
