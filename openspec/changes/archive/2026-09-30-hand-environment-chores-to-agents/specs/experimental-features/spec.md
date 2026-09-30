## MODIFIED Requirements

### Requirement: Close every surface of a switched-off feature
While a feature is off: every REST route under a route prefix it names MUST
answer 404 with code `FEATURE_DISABLED` naming the feature; its MCP tools MUST
be absent from the tool list and a call to one MUST answer as a call to an
unknown tool; its CLI commands MUST print one line naming
`coffer config set feature.<key> on` and exit 1; its sidebar entry MUST be
absent, its pages and objects MUST be absent from the command palette, and its
pages MUST show a notice that says the feature is switched off; its own
background passes MUST skip their rounds. A resource whose kind the feature
owns MUST be out of reach of the kind-agnostic resource routes too: a route
naming such a kind, or a uid whose resource is of it, MUST answer 404
`FEATURE_DISABLED`, and a list MUST leave those resources out.

Switching a feature on is Coffer's own deterministic work, so a page's notice
MUST NOT name a command to run: it MUST offer a **Switch on** button that makes
the same write as the switch on Settings → General
(`PUT /api/v1/daemon/features/{key}`), after which the page itself renders with
no reload and no restart, and a way to open Settings. A feature that
`COFFER_FEATURES` pins cannot be switched there, so its notice MUST explain the
pin instead and offer no Switch on button.

#### Scenario: a switched-off feature's routes answer feature disabled
- **GIVEN** a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** a route under `p` is requested
- **THEN** it answers 404 with code `FEATURE_DISABLED` and the key `f`

#### Scenario: a switched-off feature's resources are out of reach of the resource routes
- **GIVEN** a registered feature `f` that owns kind `k`, a resource of kind `k`, and `f` off
- **WHEN** the resource is read, changed or deleted through `/api/v1/resources/{uid}`, or the resources of kind `k` are listed
- **THEN** each answers 404 with code `FEATURE_DISABLED` and the key `f`
- **AND** an unfiltered list leaves the resource out and what it holds on disk stays in place

#### Scenario: a switched-off feature's tool leaves the tool list
- **GIVEN** a built-in tool tagged with a registered feature `f`, and `f` off
- **WHEN** an agent lists the gateway's tools
- **THEN** the tool is absent
- **AND** a call to it answers as an unknown tool

#### Scenario: a switched-off feature's command says how to switch it on
- **GIVEN** a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** a `coffer` command that reads a route under `p` runs
- **THEN** it prints a line naming `coffer config set feature.f on` and exits 1

#### Scenario: a switched-off feature's page says it is switched off
- **GIVEN** a registered feature `f` whose sidebar entry opens a page, and `f` off
- **WHEN** the user follows a link to that page
- **THEN** the page shows a notice that `f` is switched off, in place of the page
- **AND** the notice names no command and offers a way to open Settings

#### Scenario: a switched-off feature's page switches it on in place
- **GIVEN** a registered feature `f` whose page shows the switched-off notice, and `f` not pinned
- **WHEN** the user presses Switch on
- **THEN** one `PUT /api/v1/daemon/features/f` switches it on and the page itself renders, with no reload

#### Scenario: a pinned feature's page explains the pin instead of switching
- **GIVEN** a registered feature `f` held off by `COFFER_FEATURES`
- **WHEN** the user opens its page
- **THEN** the notice says `COFFER_FEATURES` holds it off and offers no Switch on button
