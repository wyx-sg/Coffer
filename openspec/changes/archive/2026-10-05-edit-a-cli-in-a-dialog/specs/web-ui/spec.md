## MODIFIED Requirements

### Requirement: Show every CLI a skill requires on the CLIs page
The CLIs page (`/clis`, under Capabilities) MUST list one row per command that
any skill requires or any enabled stdio MCP server starts with (spec
skill-manager "Check every required command where the agent runs"), with the
version found beside the minimum the skills ask for, the login state where the
command has one, and how many MCP servers and skills need it, problems first —
missing, older than the minimum, or not logged in, grouped under Needs attention above
Ready — as a split view with the selected CLI's detail beside the list
(`/clis/<command>`). The detail's Needed by MUST list the MCP servers started
with the command, each opening that server's page and naming its launcher, and
the skills that declare it, each opening that skill's Requires tab and followed by " · <profile>" for each profile that declares the command (spec skill-manager "Read the requirements profile files declare"); each row
carries its kind when both need it. The app MUST NOT show an install, update or
login command, a "run it in a terminal" instruction, or run any of them: a CLI
that needs the user says what it costs in a plain sentence — which servers can't
start and which skills fail — and its detail page and the skill's Requires tab
MUST offer the daemon's hand-off prompt (spec skill-manager "Hand a required
command to an agent with a prompt") through the hand-off split button of "Hand a machine-dependent problem to an agent with one split button"
— **Hand off to <Agent>** starts the hand-off agent in the preferred terminal with the prompt sent, and **Copy prompt** copies it;
with no managed agent available only Copy prompt is offered. **Check**, beside the list pane's filter, probes every command afresh (the header holds Add CLI), and the banner that
states a problem re-checks that one tool. Under the header's meta line a CLI with
a description shows it as plain text, and one without shows nothing there; the
header holds no field to type into.
Every CLI — added by hand or required — has **Edit** on the header's right,
which opens the Add CLI form with the command locked: for a CLI a person added
it edits the display name, description, minimum version and login check, and for one only a
skill or MCP server requires it edits the description alone (spec skill-manager
"Declare a command-line tool without a skill"). Only a CLI a person added also
has a **⋯** menu with **Remove** (a 420-wide confirmation saying the tool stays
installed on this machine). **Add CLI** opens a 480-wide form for a command name
or path, with an optional display name (the request's `title`, shown before the
meta line's "needed by"), minimum version, description and login check, which says what Coffer found — where, which version, and whether it is
already added or required — before anything is saved, and keeps a refused save in
the dialog with Retry (see skill-manager "Declare a command-line tool without a
skill"). With nothing required and nothing added the page shows one
empty state with Add CLI and a link to how `requires:` works; `requires:` entries
Coffer skipped are one muted line under the subtitle with a link to Skills. Coffer
reads no command's `--help` and shows no tree of subcommands. A skill's detail page MUST link each requirement it declares to
that CLI's page, and Overview MUST show an attention item while any required CLI
is missing, outdated or not logged in. What a skill declares and how a command
is probed are specified by skill-manager; this page shows what they report.

#### Scenario: the CLIs page lists problems first
- **GIVEN** skills requiring `jq` (not found), `gh` (minimum 2.40, found 2.30.0), `gcloud` (not logged in) and `uv` (found, current)
- **WHEN** the user opens `/clis`
- **THEN** `jq`, `gh` and `gcloud` are listed under Needs attention above `uv` under Ready, `gh` shows 2.30.0 against 2.40, `gcloud` shows not logged in, and each row counts the skills that need it

#### Scenario: a CLI that needs the user offers a prompt for an agent
- **GIVEN** a required CLI that is missing and a Coffer-managed agent
- **WHEN** the user opens its detail page and presses Hand off to <Agent>
- **THEN** the hand-off agent starts in the preferred terminal with the prompt sent
- **AND** the page offers Copy prompt, shows no install command, and with no managed agent available offers only Copy prompt

#### Scenario: check again after logging in
- **GIVEN** a CLI's detail page showing not logged in, with the hand-off to an agent and no login command shown
- **WHEN** the user logs in and chooses Check
- **THEN** the page probes the command afresh and shows it as logged in

#### Scenario: a CLI an MCP server starts with lists that server
- **GIVEN** `uv` missing, needed by the MCP server `duckdb` (started with `uvx`) and the skill `data-profiling`
- **WHEN** the user opens `/clis/uv`
- **THEN** the list row reads "Not found · duckdb needs it" with "1 server · 1 skill", the header reads "needed by 1 MCP server and 1 skill", and the banner says duckdb can't start and data-profiling fails at the step that calls uv
- **AND** Needed by lists `duckdb` (MCP server, "starts with uvx") opening `/mcp-servers/duckdb` and `data-profiling` (Skill) opening its Requires tab

#### Scenario: every CLI has Edit, only one added by hand has Remove
- **GIVEN** `demo` added by hand and `uv` required by a skill
- **WHEN** the user opens each one's page
- **THEN** `demo` shows Edit and a ⋯ menu whose Remove asks "Remove demo?" and says the tool stays installed, and `uv` shows Edit and no ⋯ menu

#### Scenario: Add CLI shows what Coffer found before anything is saved
- **GIVEN** the Add CLI dialog
- **WHEN** the user types a command name
- **THEN** it says where Coffer found the command and which version, or that it is not on this machine and can still be added, and says when a skill or MCP server already requires it
- **AND** a refused declaration stays in the dialog with its reason

#### Scenario: the empty CLIs page offers Add CLI and the docs
- **GIVEN** no required command and no tool added by hand
- **WHEN** the user opens `/clis`
- **THEN** the page shows "No command-line tools yet" with one Add CLI button, a link to how `requires:` works and no header buttons

#### Scenario: a skill's requirement links to its CLI
- **GIVEN** a skill that requires `gh`
- **WHEN** the user opens the skill's detail page and chooses the `gh` requirement
- **THEN** the app opens `/clis/gh`

#### Scenario: overview flags a required CLI that needs attention
- **GIVEN** a required CLI that is outdated
- **WHEN** the user opens Overview
- **THEN** an attention item names the CLI and the problem, and its name and its Check action open the CLI's page
- **AND** once the daemon's list no longer reports it — every required CLI present, current and logged in — the item is gone

#### Scenario: a required CLI's description is edited in a dialog
- **GIVEN** `uv`, required by a skill and not added by hand
- **WHEN** the user opens `/clis/uv`, chooses Edit, types a description and saves
- **THEN** the page saves that description alone for `uv`, trimmed, and the dialog offers no minimum version or login check
