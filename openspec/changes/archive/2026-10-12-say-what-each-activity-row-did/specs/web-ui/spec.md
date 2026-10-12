## MODIFIED Requirements

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied, and
which agent's session made it) and the daemon log (what Coffer itself did,
including what broke) — MUST reach a person through one page at `/activity`,
under System. The header carries the title, a **Live** mark (a dot and the word,
**Reconnecting…** while the daemon's change feed is closed), the line "Every
change, tool call and daemon record, newest first."
Five tabs follow, without counts: **Everything**, the default, merging the
changes, the secret uses, the calls and the daemon's warnings and errors into one
newest-first stream, then **Changes**, **Secret use**, **Tool calls** and
**Daemon log** —
each a newest-first table in a bordered box with the columns that record
actually has: Everything — time, an icon, the event, who (an agent or the actor)
and how long a call took; Changes — time, an icon, the change, who; Secret use —
time, a key icon, the use, who; Tool calls —
time, agent, `server.` (muted) and tool, how long it took (right-aligned,
sortable over the loaded rows) and the status as a dot and its word; Daemon log —
time with milliseconds, level, logger and message. The day a run of rows falls
on is a sunken heading row inside the box ("Today · Sep 29"); no summary line
sits above the table.

Changes holds what changed; Secret use holds every time a secret's value was
used — handed by Coffer to a server, a custom tool or a model connection it
starts, handed to a program by `coffer run`, or revealed in the Coffer app
([resource-framework](../resource-framework/spec.md) "Tell a secret's use from a
change in the audit log"). A secret use shows a key icon wherever it appears, and
uses of one secret by one destination less than ten minutes apart fold into one
row ending in "×N", newest first, the drawer listing each.

Every change and use MUST read as a sentence that names what it acted on and,
for a use, where the value went — the secret's name, the server, tool or
connection and the environment variable or header it filled, or the program and
folder `coffer run` started; a file's path; a sync round's outcome and file
counts; the setting and its old and new value; the approval and what it
approves — from fields the record already holds, so records written before this
read the same way. A sentence never names a secret's value. Who MUST read in
words: "You · web UI", "You · Coffer app", "You · command line", "API",
"Coffer" for Coffer itself (`coffer`, `system` and `system:<worker>`), "Sync",
"Outside Coffer" for a vault file edited on disk, or the agent's name. A tab whose log failed to load shows a warning icon. Each tab pages older records on request:
the box's last row says "Showing 30 of 1,204 · next 50 from before 13:58" with
**Load 50 more**, and only once everything kept is shown does it say so, with how
long tool calls are kept and a link to Settings › Data.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its tabs
- **THEN** Everything shows all three newest first, and each other tab renders that record's own newest-first table with the columns that record has, and no tab carries a count
- **AND** a change reads as a plain-language line, not a raw event code
- **AND** Changes has its own Kind filter listing the eleven kinds of change

#### Scenario: a secret Coffer hands to a server reads where it went
- **GIVEN** Coffer started the MCP server `github`, handing it the secret `GITHUB_TOKEN` in the environment variable `GITHUB_TOKEN`, twice within five minutes, and `coffer run` handed `OPENAI_KEY` to `python` in `~/proj`
- **WHEN** the user opens the Secret use tab
- **THEN** one row reads "Handed secret GITHUB_TOKEN to MCP server github (environment variable GITHUB_TOKEN)" with "×2", a key icon and who "Coffer"
- **AND** another reads "Handed secret OPENAI_KEY to coffer run: python, in ~/proj"
- **AND** neither row appears on the Changes tab, and no row says a secret went to `coffer run` when Coffer handed it to a server

#### Scenario: a change names what it changed
- **GIVEN** the user stored the secret `SENTRY_TOKEN` over an older value, a sync round pulled 3 files and pushed 1, and a vault file `knowledge/notes/x.md` was edited on disk
- **WHEN** the user opens the Changes tab
- **THEN** the rows read "Stored secret SENTRY_TOKEN, replacing its value", "Synced: pulled 3 files, pushed 1" and "Edited vault file knowledge/notes/x.md on disk"

#### Scenario: the daemon tab reads every writer in the log
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, an upstream's `LEVEL - logger - message` lines, uvicorn and rich — with a colour-escaped line among them and a traceback written under the record that raised it
- **WHEN** the user opens the Daemon tab
- **THEN** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **AND** no message renders a terminal escape sequence as text
- **AND** the traceback rides with the record that raised it rather than becoming rows of its own
- **AND** the severity-floor filter judges each line by its own level rather than treating every non-JSON line as an error

#### Scenario: the box ends with what is shown and what is kept
- **GIVEN** the Changes tab with more records than the first page holds
- **WHEN** the user reads to the end of the first page, and later of everything kept
- **THEN** the box's last row first says how many are shown of how many, what the next page holds and from before when, with Load 50 more
- **AND** only after the last page does it say "That's everything kept" with how long tool calls are kept and a link to Settings › Data

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter in one row — the search first (240 wide), then
the time range and the pills, with **Clear filters** at the far right while
anything is set — and show no counts in it. Everything: search, time range,
**By** and **Kind**; Changes: search, time range, **By** and **Kind**; Secret use:
search, time range and **By**; Tool calls:
a segmented **All / OK / Failed** first (Failed is an error, a timeout or a
denial), then search, time range and **By**; Daemon log: a segmented **All /
Info / Warnings / Errors** first, then search, time range and **Logger**. There
is no filter for a server: the search matches a server's name. **By** chooses
several values, listing the agents and, under "Not an agent", you (the web UI,
the desktop app), the command line, Coffer itself and sync, last; on Tool calls
it lists agents only. **Kind** on Everything is four flat values — Tool calls,
Changes, Secret uses, Daemon records — and on Changes the eleven kinds of change (a resource
kind, or secrets, sync, settings and CLIs for a change that names no resource),
flat. A pill lists no counts and searches only above eight values. The time
range is the shared picker: Last hour, Last 24 h, Last 7 days, Last 30 days and
a custom range (calendar days, optional HH:MM, an end of "now", at most 90 days
back); a tab opens on the last hour, the Daemon log on the last 24 hours, until
the user picks one. A record passes when it matches any chosen value.

Selecting a row on Everything, Changes, Secret use or Tool calls MUST open it in the shared
right-hand drawer (640 wide until its left edge is dragged, the page dimmed behind it; Esc, a click outside or
its ✕ closes it, ↑ ↓ step to the previous or next record, focus returns to the
row), answer first — a failed call's error and how its server has been doing
(since when it has been failing, and its errors in the last 24 hours), a
change's who and what, then its configuration before and after as a diff, a
daemon record's message and traceback — then the records written within five
minutes of it, ending in its raw underlying record, pretty-printed in a
monospace, scrollable block, open and foldable. The footer holds
the next step: **Open** the resource's own detail page beside **Copy details**. A call's drawer
shows, after its answer, the content the call recorded ([mcp-gateway](../mcp-gateway/spec.md)
"Record invocations with redacted, bounded content"), read when the drawer opens: **Arguments**,
**Result** (or **Error**), and for a custom tool **Request** and **Response**, each a foldable
monospace block — JSON laid out, other text as it is — with **Copy**, and a cut part ending in
"Cut at 16 KB — the call carried N KB". A call recorded while recording was off says "Content
was not recorded for this call" with a link to the setting, and the drawer notes that secret
values are masked before anything is stored. A
change whose event the page has no sentence for reads through the same facts and
diff. On the Daemon log a row opens in place under its own line instead, with its
traceback, **Copy record** and, when the record names a server and tool, **Show
the tool call**, which opens the Tool calls tab looking for that call.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row on Everything, Changes, Secret use or Tool calls
- **THEN** the shared drawer opens over the page with its raw underlying record open — the full JSON, pretty-printed in a monospace, scrollable block

#### Scenario: a daemon log row opens in place
- **GIVEN** the Daemon log tab with an error record carrying a traceback and naming `server=github tool=search_issues`
- **WHEN** the user selects that row, then chooses Show the tool call
- **THEN** the row opens under its own line with the traceback and Copy record, and no drawer opens
- **AND** Show the tool call opens the Tool calls tab searching `github.search_issues`

#### Scenario: who and kind choose several values
- **GIVEN** Everything holding a call by an agent, a change made in the web UI, a change made from the command line and a daemon warning
- **WHEN** the user chooses the agent and "You" under By, then Tool calls and Changes under Kind
- **THEN** the list keeps the agent's call and the web UI's change and drops the others, and the Kind pill reads "Kind: Tool calls, Changes"

#### Scenario: a call's drawer shows its arguments and result
- **GIVEN** a recorded tool call with arguments, a cut result and a call recorded while recording was off
- **WHEN** the user opens each on the Tool calls tab
- **THEN** the first drawer shows Arguments and Result as laid-out JSON with Copy, the result ending in its cut note
- **AND** the second says its content was not recorded and links to Settings › Data

### Requirement: Read each Activity tab from its record owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose) — the
Changes tab `GET /api/v1/audit`, the Tool calls tab `GET /api/v1/mcp/invocations`
and the Daemon tab `GET /api/v1/daemon/logs`, Everything all three — and its
filters list agents and servers from those kinds' own list routes. An agent or
a script that asks "what happened" reads the same three records from the
command line (see "Keep the command-line record readers").

#### Scenario: each activity tab reads its owner's route
- **GIVEN** a running daemon that has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens each of the Activity tabs in turn
- **THEN** each tab shows only its own record's rows, read from that record's owner's route
- **AND** no tab requests a route of the Activity page's own
