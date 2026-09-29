## 1. Backend

- [x] 1.1 Envelope, resync and heartbeat Pydantic models, documented in the generated contract
- [x] 1.2 Event broker: sequence, bounded replay buffer, bounded subscriber queues, resync on a gap
- [x] 1.3 Feed the broker from the resource hint seam (upsert and delete) and from an attention watcher
- [x] 1.4 `GET /api/v1/events`: token-gated SSE, `Last-Event-ID` resume, heartbeat

## 2. Tests and docs

- [x] 2.1 Unit tests for the broker; integration tests for the route, one per scenario
- [x] 2.2 docs-site architecture page on the event stream
