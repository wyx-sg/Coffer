## ADDED Requirements

### Requirement: Report the last read of the agents' memory
`GET /api/v1/memory/reading` MUST answer when Coffer last read the agents' memory
(`read_at`, `null` before the first read) and, for each agent whose memory that read could not
parse, the agent, the source path, the reason and when that agent's memory was last read with
nothing failing, if known. The answer MUST be read from the `memory_aggregated` audit events,
which therefore carry each failure's agent, path and reason, so it is the same whoever started
the read — the timer, Update memory or `coffer memory sync` — and survives a daemon restart. Only
the newest read decides what failed. The Memory page's header MUST say "Read 14 min ago", with
"· 1 agent failed" when the last read left an agent unread, and the page MUST then show a
banner naming the agent and the path, saying that agent's memories stay as its last full read
left them, with **Retry** (Update memory) and **Open Activity**.

#### Scenario: the last read and an agent it could not read are reported
- **GIVEN** three reads recorded, the newest two unable to parse Codex's memory and the oldest
  reading every agent
- **WHEN** the last read is asked for
- **THEN** it is the newest read's time, with one failure naming Codex, its path and its reason
- **AND** that failure's last full read is the oldest read's time

### Requirement: Show Update memory's progress
While Update memory runs, `GET /api/v1/upkeep/runs` MUST list it as one `memory` run named
`update` beside the per-partition claims: with no count while it is reading the agents' memory,
then with `done` and `total` over the partitions it has to distil. The Memory page's header MUST
read "Reading agents' memory…" and then "Distilling 2 of 5 partitions" from it, the Update
memory button MUST read "Updating…" while it is listed, and each partition row whose distil pass
is in flight MUST read "Distilling…".

#### Scenario: update memory reports how many partitions it has distilled
- **GIVEN** four partitions, three of them holding entries no pass has distilled
- **WHEN** Update memory runs
- **THEN** its run carries no count while it reads the agents' memory, then 0, 1 and 2 of 3 as it
  distils the three partitions in turn, leaving the fourth alone
- **AND** it is no longer listed once it has answered
