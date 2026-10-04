## MODIFIED Requirements

### Requirement: Make a switched-off feature look absent in the UI
While a feature is off, the web UI MUST show nothing that belongs to it: its
sidebar entries, and any sidebar group heading left empty, its pages and
objects in the command palette, its Overview tiles and first-run cards, its
kind in object-kind lists, and every section of another page that exists only
for it. A link to one of its pages MUST show the standard not-found page. The UI
MUST NOT show a notice that a feature is switched off or needs another, and MUST
NOT offer a switch-on button outside Settings → Features. An agent's
Overview › Model section and Settings → Coffer's model MUST omit what depends on `models`:
the section is read-only, with no Provider row and no Change….

#### Scenario: a switched-off feature's page is not found
- **GIVEN** a registered feature `f` whose sidebar entry opens a page, and `f` off
- **WHEN** the user follows a link to that page
- **THEN** the standard not-found page shows, with no notice that `f` is switched off and no switch-on button

#### Scenario: a switched-off feature is absent from the navigation
- **GIVEN** a registered feature `f` that owns a sidebar entry, a palette page and an Overview tile, and `f` off
- **WHEN** the sidebar, the command palette and the Overview render
- **THEN** none of them shows anything of `f`, and a sidebar group left with no entry shows no heading

#### Scenario: a page omits the section that belongs to a switched-off feature
- **GIVEN** `models` off
- **WHEN** the user opens an agent's Overview and Settings → Coffer's model
- **THEN** the Model section shows the agent's own model read-only, with no Provider row and no Change…, and Coffer's model shows nothing that depends on `models`
- **AND** neither shows a notice about it, and `?change-model=1` opens no dialog

