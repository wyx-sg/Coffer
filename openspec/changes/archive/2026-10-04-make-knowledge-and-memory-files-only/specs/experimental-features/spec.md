## MODIFIED Requirements

### Requirement: Close the knowledge feature's surfaces
While `knowledge` is off, `/api/v1/knowledge` MUST answer 404
`FEATURE_DISABLED` and the `knowledge` kind MUST be out of reach of the resource
routes. The `coffer-guide`
skill MUST be rendered without its knowledge catalogue, and switching
`knowledge` on MUST restore it. The curation pass MUST
skip its rounds. The channel `/kb` command MUST be out of `/help` and the menus
and answer that Knowledge is switched off, keeping any pending document.

#### Scenario: knowledge off closes the knowledge routes
- **GIVEN** `knowledge` off
- **WHEN** a route under `/api/v1/knowledge` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `knowledge`

#### Scenario: knowledge off hides the write tool
- **GIVEN** `knowledge` off
- **WHEN** an agent opens a gateway session and lists the tools
- **THEN** the `coffer__` tools listed are `coffer__search_tools` alone, a call to `coffer__write` answers as an unknown tool, and the handshake instructions name no knowledge tool

#### Scenario: knowledge off re-renders the coffer-guide skill without its knowledge sections
- **GIVEN** `knowledge` off
- **WHEN** the `coffer-guide` skill is rendered
- **THEN** it carries no knowledge catalogue, and the catalogue returns once `knowledge` is on

#### Scenario: knowledge off skips the curation pass
- **GIVEN** `knowledge` off
- **WHEN** the curation pass comes due
- **THEN** it skips its round

#### Scenario: knowledge off answers /kb as switched off
- **GIVEN** `knowledge` off and a channel conversation with a pending document
- **WHEN** the user sends `/kb`
- **THEN** `/kb` is absent from `/help` and the menus and answers that Knowledge is switched off, and the pending document is kept
