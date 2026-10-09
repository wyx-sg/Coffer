## 1. Reaper

- [x] 1.1 Stop refreshing activity on stream open, on the keepalive tick and on delivery of a queued notification
- [x] 1.2 Lower `_DEFAULT_IDLE_TIMEOUT_S` to 10 minutes
- [x] 1.3 Tests: a stream held open with no POSTs is reaped and ends; the next request is 404

## 2. Docs

- [x] 2.1 ADR, architecture (en + zh), daemon, configuration, connect-a-client
