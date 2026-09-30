## MODIFIED Requirements

### Requirement: Report usage by model, agent or day over a range
`GET /api/v1/usage/summary` and `coffer usage [--range today|7d|30d|month|custom] [--from <day> --to <day>] [--by model|agent|day] [--agent <agent type>] [--provider <name>] [--json]`
MUST report, for the range in the machine's local days (today; the last 7 or 30 days including today;
this calendar month; or an inclusive custom range), one row per model (with the connection that
served it, by uid and name), per agent or per day: requests, the token totals per category, the
estimated cost, how many requests were unpriced or had unknown usage, and the agent types that sent
the row's requests, most requests first. The summary MUST be narrowable to one agent type
(`agent_type`) and to one connection (`connection_uid`); a filtered summary's rows and totals count
only the requests that match every filter. `GET /api/v1/usage/requests` and `coffer usage requests`
page through the per-request detail, newest first. `GET /api/v1/usage/export.csv` and
`coffer usage --csv` return the same summary, with the same filters, as CSV.

#### Scenario: usage by model names the connection
- **GIVEN** usage of two models over two connections
- **WHEN** the summary is grouped by model
- **THEN** each row names its model and the connection's uid and name, with its requests, tokens and estimated cost

#### Scenario: usage by agent and by day
- **GIVEN** usage by two agents on two days
- **WHEN** the summary is grouped by agent, and then by day
- **THEN** it returns one row per agent, and then one row per day

#### Scenario: usage narrowed to one agent and one provider
- **GIVEN** usage by Claude Code over one connection and by Codex over another
- **WHEN** the summary is narrowed to Codex, then to the first connection, then to both at once
- **THEN** it counts only Codex's requests, then only the first connection's, then nothing
- **AND** each unfiltered row names the agent types that sent its requests, most requests first, and the CSV honours the same filters

#### Scenario: a range resolves in local days
- **GIVEN** a clock on a known local day
- **WHEN** the ranges today, 7d, 30d and this month are resolved
- **THEN** each spans the local days it names, today included

#### Scenario: export usage as CSV
- **GIVEN** usage in the range
- **WHEN** the user exports it
- **THEN** the CSV has a header row and one line per group with the same totals the summary reports
