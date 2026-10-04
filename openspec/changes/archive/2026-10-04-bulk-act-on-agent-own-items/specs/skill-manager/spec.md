## MODIFIED Requirements

### Requirement: Expose unmanaged-skill operations on REST and the web
Unmanaged-skill operations MUST be available through the REST API (`GET`, `POST .../adopt` and `DELETE` under `/api/v1/agents/{uid}/unmanaged-skills`) and through the agent's Skills tab in the web UI; the command line carries no unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the resource routes and the Skills page. The agent detail page decides nothing about delivery: its Skills tab opens with one **From Coffer** row — how many skills Coffer delivers to that agent, their first names, and **Open Skills ›**, a link to the Skills page narrowed to that agent — and then lists the unmanaged skills found on that agent's disk (see [agent-registry](../agent-registry/spec.md) "Show what Coffer manages for an agent in one row"). The Skills page accepts an `agent` query parameter, `/skills?agent=<uid>`, and then lists only the managed skills that reach that agent, with the agent named in a filter beside the search. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them, one at a time or several at once (see [agent-registry](../agent-registry/spec.md) "Act on several of an agent's own items at once"); the Skills page lists managed skills only (see "Cover skill management on REST and the web").

#### Scenario: list, adopt and delete an unmanaged skill
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user lists `GET /api/v1/agents/{uid}/unmanaged-skills`, then adopts one with `POST .../unmanaged-skills/{skill}/adopt`, then deletes the other with `DELETE .../unmanaged-skills/{skill}` and confirms it
- **THEN** the list names both folders, the first becomes a managed skill and leaves the next list, and the second is removed from disk
- **AND** the command line offers no command that lists, adopts or deletes an unmanaged skill

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it as the agent's own, with Adopt, and the Skills page does not list it
