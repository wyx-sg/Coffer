## MODIFIED Requirements

### Requirement: Open an MCP server on its Overview
An MCP server's detail page MUST open on a primary "what is this server doing?"
Overview, before the per-capability tabs, and its tabs — Overview, Tools,
Resources, Prompts, Invocations — MUST carry no counts. Under the banner the
Overview stacks **Last 24 hours** (the server's calls and errors, with a table of
the agents that made them and a line for a session that named no agent; for a
server that is off, only its last call and who made it; for a server that is on,
a View invocations link to the server's own Invocations tab), **Requires** — what the
server's command and settings need from this machine (see mcp-gateway "Show what
an MCP server requires"): the launcher as a row reading "Found · <version>" or
"Not found" with a View in CLIs link to `/clis/<launcher>`, and each secret as
named by the secret's own name (the setting that carries it is its tooltip) as
Set, Missing or Waiting for approval with a View in Secrets link to
`/secrets?q=<name>`, the Secrets list searched for it —
and **Most-called tools**: the busiest four, read-only with no switches, each
marked when it sits behind search, with the rest one link away ("Show all N in
Tools").

#### Scenario: a server's detail page opens on its Overview
- **GIVEN** a registered MCP server
- **WHEN** its detail page is opened with no tab named in the URL
- **THEN** the Overview tab is the selected tab and its content is shown
- **AND** the Tools, Resources and Prompts tabs follow it

#### Scenario: the Overview stacks the last 24 hours by agent, what it requires and the busiest tools
- **GIVEN** a server with 312 calls in 24 hours, a launcher that is found, one secret that is missing and five tools
- **WHEN** its Overview opens
- **THEN** it shows the totals and the table of the agents that called it, then Requires with the launcher found and linked to its CLI page and the secret Missing under its own name and linked to Secrets searched for it, then the four busiest tools without switches and a link to all five
- **AND** no Agents section and no reach note sit on it

#### Scenario: the 24-hour block opens the server's own call history
- **GIVEN** a server that is on, with calls in the last 24 hours
- **WHEN** the user chooses View invocations on its Overview
- **THEN** the server's Invocations tab opens on the same page, at `/mcp-servers/<name>/invocations`

## ADDED Requirements

### Requirement: Match a list's search on names only
A search box over a list of named things — MCP servers and their tools, resources
and prompts, skills, channels, model providers, custom tool groups, secrets and
what uses a secret, an agent's skills, plugins, MCP servers and memory folders,
and a picker's options — MUST match the item's name (its title too, where it has
one) and nothing else: not its description, endpoint, host, path, kind or the
names of what it contains. A hook has no name, so the agent's own hooks match on
their command. Searches over records — Activity, conversations, a document's
text — are not lists of named things and keep matching their text.

#### Scenario: a search does not match descriptions
- **GIVEN** a server whose tools' descriptions all contain "does" and whose names do not
- **WHEN** the user searches its Tools tab for "does"
- **THEN** no tool is listed
