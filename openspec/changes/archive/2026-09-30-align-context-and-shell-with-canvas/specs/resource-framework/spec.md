## MODIFIED Requirements

### Requirement: Carry an optional editable title on the kinds that have one
A resource of a kind that carries a title MUST carry an optional **`title`**: free text of at
most 80 characters that a person chooses for display, separate from the resource's `name`. The
kinds with a title are those whose name is a label a person chose — `provider`, `channel`
and `memory`. A knowledge collection carries none: it is named by its folder, with an editable
description ([knowledge](../knowledge/spec.md) "Name a collection by its folder and edit its description in place"). `agent`, `mcp_server`, `skill` and `knowledge` carry none: each is shown by its fixed
name, and a non-empty title for one MUST be refused as a validation error (422) on registration
and on update, with nothing changed. On a kind that carries one, the title MUST be editable
through the kind-agnostic update (`PATCH /api/v1/resources/{uid}`) and through
`coffer <kind> edit <name> --title <text>`. An empty title MUST clear it. A title longer than 80
characters MUST be refused as a validation error with nothing changed. A title change MUST be
audited like any other update. The web UI and the CLI MUST show the title in place of the name
wherever a resource is listed or shown when a title is set, and the name when it is not. The
title MUST travel with the resource to the user's other machines through vault-sync, and a
resource that arrives without one MUST keep its title empty.

#### Scenario: a title is shown in place of the name
- **GIVEN** a resource of a kind that carries a title, with no title
- **WHEN** the user runs `coffer <kind> edit <name> --title "Team search"` and then lists that kind
- **THEN** the list and `coffer <kind> show` print "Team search" where the name was shown, and `--json` carries both `name` and `title`
- **AND** the change is audited as an update, and the resource's name, uid, reach and enabled state are unchanged

#### Scenario: an over-long title is refused
- **GIVEN** a resource with a title set
- **WHEN** the user submits a title of 81 characters through the update route, and then an empty title
- **THEN** the first is refused as a validation error and the stored title is unchanged
- **AND** the second clears the title, and surfaces show the name again

#### Scenario: a kind without a title refuses one
- **GIVEN** a registered MCP server, a registered skill and a registered agent
- **WHEN** the user submits a title for each through the kind-agnostic update, and registers an MCP server with a title
- **THEN** each is refused as a validation error (422) and nothing is stored
- **AND** `coffer mcp edit` and `coffer mcp add` offer no `--title`, and `coffer skill` offers no `edit`
