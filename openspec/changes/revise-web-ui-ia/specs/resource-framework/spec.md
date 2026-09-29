## ADDED Requirements

### Requirement: Count a log's matching rows beside each page
The audit log (`GET /api/v1/audit`) and the MCP invocation log (`GET /api/v1/mcp/invocations`,
`GET /api/v1/resources/mcp_server/{uid}/invocations`) answers MUST carry `total`: the number of rows
that match the request's filters across every page. The cursor and `limit` MUST NOT change it, so a
client can say how many entries a filtered view holds without paging through all of them. It is
counted with the same filters as the page (see "Page growing lists by an opaque cursor"), so the two
cannot disagree about which rows are in the view.

#### Scenario: a page carries the count of every matching row
- **GIVEN** an audit log of five entries, three of them about one kind
- **WHEN** it is read filtered to that kind with `limit=2`, and then with the answer's `next_cursor`
- **THEN** both answers carry `total` 3
