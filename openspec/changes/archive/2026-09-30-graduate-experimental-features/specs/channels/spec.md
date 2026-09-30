## RENAMED Requirements

- FROM: `### Requirement: Save a sent document into a collection`
- TO: `### Requirement: Save a sent document into a collection (before graduation)`

## REMOVED Requirements

### Requirement: Save a sent document into a collection (before graduation)
**Reason**: Knowledge graduated, so `/kb` is always offered and the scenario "/kb is offered only while knowledge is on" no longer holds. A MODIFIED block cannot drop a scenario, so the requirement is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: Its marker is deleted.

## MODIFIED Requirements

### Requirement: Register the bot's command menu and profile from one roster
The bot MUST introduce itself. Its command menus are registered with the
platform from Coffer's own command roster, and its prose profile (description,
short description) is **filled in when empty**, so a user opening the bot for
the first time sees what it is and what it accepts instead of an empty chat. The
registered menus MUST list the commands the channel actually handles — a command
the help text offers but the private-chat menu omits is a drift bug, not a
design choice. This is enforced structurally rather than by review: the menus,
the help text, the typo guard (see "Pass unreserved slash text to the agent")
and the per-command privacy flag (see "Keep non-answer chatter private in a
group") are all rendered from one roster, so adding a command is one entry plus
its handler, with no second list to forget. Each entry carries its description
in English and Chinese, and whether it belongs in a group's menu. A platform with no menu API (SeaTalk) introduces
the commands through the help card instead (see "Offer the commands as a help
card"). Copy the owner already wrote, and the bot's name, are their branding
decision and MUST NOT be overwritten.

#### Scenario: the command menu matches the commands that exist
- **GIVEN** the channel command roster,
- **WHEN** the transport registers its private-chat command menu,
- **THEN** every command the channel handles is registered.

## ADDED Requirements

### Requirement: Save a sent document into a collection
A document sent to a Coffer channel MUST be ingestible into a collection through
the same conversion path the Knowledge page uses, so the phone and that page are
two ends of one entrance (spec `knowledge`). `/kb` is the command that does it.
The channel MUST confirm the collection with the owner before storing, and MUST
NOT store anything from a non-owner. `/kb` is offered in `/help` and in every
registered menu.

#### Scenario: a document sent to a channel is saved into a collection
- **GIVEN** a paired owner who has sent a document to the channel,
- **WHEN** the owner follows it with `/kb <collection>` naming a collection
  that exists,
- **THEN** the document is ingested into that collection through the same
  conversion path the Knowledge page uses,
- **AND** a `/kb` from anyone but the paired owner stores nothing.

#### Scenario: a save that names no collection asks which one
- **GIVEN** a paired owner who has sent a document but named no collection,
- **WHEN** they send `/kb`,
- **THEN** the channel offers the collections it may save into and stores
  nothing until one is chosen — on a transport without buttons it lists them as
  text,
- **AND** a `/kb` with no document pending is refused in one line.
