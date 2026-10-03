## MODIFIED Requirements

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied, and
which agent's session made it) and the daemon log (what Coffer itself did,
including what broke) — MUST reach a person through one page at `/activity`,
under System. The header carries the title, a **Live** mark (a dot and the word,
**Reconnecting…** while the daemon's change feed is closed), the line "Every
change, tool call and daemon record, newest first." and a ghost **Export** menu.
Four tabs follow, without counts: **Everything**, the default, merging the
changes, the calls and the daemon's warnings and errors into one newest-first
stream, then one tab per record — **Changes**, **MCP calls**, **Daemon log** —
each a newest-first table in a bordered box with the columns that record
actually has: Everything — time, an icon, the event, who (an agent or the actor)
and how long a call took; Changes — time, an icon, the change, who; MCP calls —
time, agent, `server.` (muted) and tool, how long it took (right-aligned,
sortable over the loaded rows) and the status as a dot and its word; Daemon log —
time with milliseconds, level, logger and message. The day a run of rows falls
on is a sunken heading row inside the box ("Today · Sep 29"); no summary line
sits above the table. A tab whose log failed to load shows a warning icon. On the
Daemon log a line above the box names the file the tail is read from, "newest
first", "following" while the change feed is open, and **Open in Finder**, which
reveals the file through the daemon. Each tab pages older records on request:
the box's last row says "Showing 30 of 1,204 · next 50 from before 13:58" with
**Load 50 more**, and only once everything kept is shown does it say so, with how
long MCP calls are kept and a link to Settings › Data.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its tabs
- **THEN** Everything shows all three newest first, and each other tab renders that record's own newest-first table with the columns that record has, and no tab carries a count
- **AND** a change reads as a plain-language line, not a raw event code
- **AND** Changes has its own Kind filter listing the eleven kinds of change

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
- **AND** only after the last page does it say "That's everything kept" with how long MCP calls are kept and a link to Settings › Data

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter in one row — the search first (240 wide), then
the time range and the pills, with **Clear filters** at the far right while
anything is set — and show no counts in it. Everything: search, time range,
**By** and **Kind**; Changes: search, time range, **By** and **Kind**; MCP calls:
a segmented **All / OK / Failed** first (Failed is an error, a timeout or a
denial), then search, time range and **By**; Daemon log: a segmented **All /
Info / Warnings / Errors** first, then search, time range and **Logger**. There
is no filter for a server: the search matches a server's name. **By** chooses
several values, listing the agents and, under "Not an agent", you (the web UI,
the desktop app), the command line, Coffer itself and sync, last; on MCP calls
it lists agents only. **Kind** on Everything is three flat values — MCP calls,
Changes, Daemon records — and on Changes the eleven kinds of change (a resource
kind, or secrets, sync, settings and CLIs for a change that names no resource),
flat. A pill lists no counts and searches only above eight values. The time
range is the shared picker: Last hour, Last 24 h, Last 7 days, Last 30 days and
a custom range (calendar days, optional HH:MM, an end of "now", at most 90 days
back); a tab opens on the last hour, the Daemon log on the last 24 hours, until
the user picks one. A record passes when it matches any chosen value.

Selecting a row on Everything, Changes or MCP calls MUST open it in the shared
right-hand drawer (640 wide, the page dimmed behind it; Esc, a click outside or
its ✕ closes it, ↑ ↓ step to the previous or next record, focus returns to the
row), answer first — a failed call's error and how its server has been doing
(since when it has been failing, and its errors in the last 24 hours), a
change's who and what, then its configuration before and after as a diff, a
daemon record's message and traceback — then the records written within five
minutes of it, ending in its raw underlying record, pretty-printed in a
monospace, scrollable block that stays folded until asked for. The footer holds
the next step: **Open** the resource beside **Copy details**. A call's drawer
shows its metadata only, since Coffer stores no call's arguments or results. A
change whose event the page has no sentence for reads through the same facts and
diff. On the Daemon log a row opens in place under its own line instead, with its
traceback, **Copy record** and, when the record names a server and tool, **Show
the MCP call**, which opens the MCP calls tab looking for that call.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row on Everything, Changes or MCP calls
- **THEN** the shared drawer opens over the page and offers its raw underlying record — the full JSON, pretty-printed in a monospace, scrollable block — once Raw log is unfolded

#### Scenario: a daemon log row opens in place
- **GIVEN** the Daemon log tab with an error record carrying a traceback and naming `server=github tool=search_issues`
- **WHEN** the user selects that row, then chooses Show the MCP call
- **THEN** the row opens under its own line with the traceback and Copy record, and no drawer opens
- **AND** Show the MCP call opens the MCP calls tab searching `github.search_issues`

#### Scenario: who and kind choose several values
- **GIVEN** Everything holding a call by an agent, a change made in the web UI, a change made from the command line and a daemon warning
- **WHEN** the user chooses the agent and "You" under By, then MCP calls and Changes under Kind
- **THEN** the list keeps the agent's call and the web UI's change and drops the others, and the Kind pill reads "Kind: MCP calls, Changes"

### Requirement: Query only the visible Activity tab and isolate failures
Only the visible tab pages through records — Everything through all three
logs, each other tab through its own — and no tab reads a count: tabs carry
none. A record whose route fails MUST render its error inside its own tab,
leaving the other two working — one failing lane must not take the other two
down with it; on Everything the failing record is named in one warning banner
above the box with its error and which records below are complete ("Changes and
daemon records below are complete."), the stream shows the other two records,
the failed record's tab shows a warning icon, and the banner offers **Retry**
for the failed log only. The banner cannot be closed. There MUST be no manual
refresh control and no Pause / Resume control: switching tab or changing a
filter refetches, and new records arrive on their own (see "Stream new Activity
records while the list is at the top").

#### Scenario: a failing record shows its error inside its own tab
- **GIVEN** one of the three routes is unavailable (an older daemon that does not serve it)
- **WHEN** the user opens `/activity`
- **THEN** the failing record's tab renders a readable error and carries a warning icon
- **AND** the other two tabs still render their rows

#### Scenario: a failed log is one banner that retries only that log
- **GIVEN** Everything with the MCP call log unavailable
- **WHEN** the banner's Retry is chosen
- **THEN** only the call log is read again, and the banner has no close control

## RENAMED Requirements

- FROM: `### Requirement: Export the filtered Activity records from the overflow menu`
- TO: `### Requirement: Export the filtered Activity records from the header`

## MODIFIED Requirements

### Requirement: Export the filtered Activity records from the header
The Activity page's header MUST carry a ghost **Export** menu offering **JSON**
and **CSV**, which save the records of the visible tab that match its current
filters — free text, time range and the tab's own filter — and nothing else, not
including a record's hand-off prompt. With no records at all there is no menu.

#### Scenario: export from the menu honours the filters
- **GIVEN** the MCP calls tab filtered by a search and to failed calls
- **WHEN** the user chooses CSV from the header's Export menu
- **THEN** the file holds exactly the calls that match those filters, one per row
- **AND** JSON saves the same records as JSON

## ADDED Requirements

### Requirement: Keep Activity's filters in the address
The Activity page MUST keep its tab and every filter in the address, so a link
or a reload comes back to the same view: `tab`, `q` (the search), `range`
(a preset id or a custom range), `by` and `kind` (comma-joined), `status`,
`level` and `logger`; a value at its default is left out. A link from another
page — "View in Activity" with a name — opens already searching it. Moving to
another tab keeps the search, the time range the reader chose and who, and drops
the filters only the old tab had.

#### Scenario: a link opens already searching
- **GIVEN** the address `/activity?tab=mcp&q=github`
- **WHEN** the page opens
- **THEN** the MCP calls tab shows `github` in its search box and asks the route for calls matching it
- **AND** Clear filters empties the box and removes `q` from the address

### Requirement: Show the first run with nothing to filter
When Coffer has recorded nothing at all — no change, no call and no daemon
warning — the Activity page MUST hide the filter row and Export, keep its tabs,
and say "Changes you make in Coffer and the tools agents call through it show up
here." with **Connect an agent** and **Add an MCP server**. An empty time range
while older records exist is not the first run: it says so and keeps the filters.

#### Scenario: nothing recorded hides the filter row and Export
- **GIVEN** no audit entry, call or daemon record exists
- **WHEN** the user opens `/activity`
- **THEN** the page shows the empty state with its two actions and neither the filter row nor Export
- **AND** with a record older than the time range the filter row and Export stay

### Requirement: Hand an environment failure on Activity to an agent
Activity MUST offer the hand-off ([Ask an agent ▾]) only for a failure that depends
on this machine, with the prompt the backend wrote: the conclusion card of a
call's drawer for a call whose server never answered, and the first button of an
opened daemon ERROR about an external service or the environment. A denied call,
an error the server itself returned and a Coffer-internal error offer no
hand-off; a daemon error offers **Copy record** alone. The drawer's footer for a
call is the server's page; it carries no step to read the daemon log.

#### Scenario: an unanswered call and an environment error carry the hand-off
- **GIVEN** a call refused by its server, a denied call, and a daemon ERROR that is a refused connection beside one that is Coffer's own
- **WHEN** each is opened
- **THEN** the refused call's card and the environment error's button row lead with the hand-off, and the others have none
