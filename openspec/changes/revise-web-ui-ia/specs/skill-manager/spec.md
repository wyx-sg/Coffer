## MODIFIED Requirements

### Requirement: Expose unmanaged-skill operations on REST, CLI and web
Unmanaged-skill operations MUST be available through the REST API, through the top-level `coffer scan`, `coffer adopt skill <path>` and `coffer discard skill <path>` commands (with `--json` on `scan`), and through the agent's Skills tab in the web UI. The command line groups them with every other thing an agent holds that Coffer does not manage, so neither `coffer skill` nor `coffer agent` carries an unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through `coffer skill enable|disable|scope` and the matching resource routes. The agent detail page decides nothing about delivery: its Skills tab points at the Skills page and otherwise carries only the unmanaged skills found on that agent's disk. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them; the Skills page lists managed skills only (see "Cover skill management on REST, the CLI and the web"). The REST routes and CLI commands for unmanaged skills are unchanged.

#### Scenario: manage unmanaged skills with scan, adopt and discard
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user runs `coffer scan --agent <agent> --json`, then `coffer adopt skill <one path>`, then `coffer discard skill <other path>` and confirms it
- **THEN** the scan is JSON naming both folders as rows of kind `skill`, the first becomes a managed skill and leaves the next scan, and the second is removed from disk
- **AND** neither `coffer skill` nor `coffer agent` offers an `unmanaged`, `adopt` or `rm-unmanaged` command

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it with Adopt, and the Skills page does not list it

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked; the rows carry Adopt and Delete and no Open folder. The detail page MUST show the skill's name with an Unmanaged badge and its location, a back link to that tab, and the actions Open folder (the folder in the OS file manager), Adopt ("Adopt an unmanaged skill"; disabled with its reason for an invalid folder or a foreign link) and Delete ("Delete an unmanaged skill on explicit request", confirmed first). A successful adoption MUST go on to the new managed skill's detail page, since the folder is no longer unmanaged; a successful delete MUST return to that tab.

#### Scenario: open an unmanaged skill's detail page from the agent's Skills tab
- **GIVEN** an agent's Skills tab listing unmanaged skills
- **WHEN** the user clicks one row
- **THEN** that skill's detail page opens, and its Files tab shows the folder's tree and a read-only preview of the chosen file
- **AND** no row in the table carries an Open folder button

#### Scenario: adopt or delete an unmanaged skill from its detail page
- **GIVEN** an unmanaged skill's detail page
- **WHEN** the user adopts it
- **THEN** the page moves to the new managed skill's detail page
- **AND** when the user instead deletes it and confirms, the folder is deleted and the page returns to the agent's Skills tab
