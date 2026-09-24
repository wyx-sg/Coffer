## MODIFIED Requirements

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied) and the
daemon log (what Coffer itself did, including what broke) — MUST reach a person
through one page at `/activity`, under System, carrying one tab per record —
Changes, MCP calls, Daemon — each a newest-first table with the columns that
record actually has: an activity line and its actor; a call's server,
capability, duration and outcome; a log record's level, logger and message.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its three tabs
- **THEN** each tab renders that record's own newest-first table with the columns that record has — an activity line and actor; a call's server, capability, duration and outcome; a log record's level, logger and message
- **AND** a change reads as a plain-language line, not a raw event code

#### Scenario: the daemon tab reads every writer in the log
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, the format the daemon itself wrote before [daemon](../daemon/spec.md) "Write one bounded daemon log in one format" was met, uvicorn and rich — with a colour-escaped line among them and a traceback written under the record that raised it
- **WHEN** the user opens the Daemon tab
- **THEN** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **AND** no message renders a terminal escape sequence as text
- **AND** the traceback rides with the record that raised it rather than becoming rows of its own
- **AND** the severity-floor filter judges each line by its own level rather than treating every non-JSON line as an error
