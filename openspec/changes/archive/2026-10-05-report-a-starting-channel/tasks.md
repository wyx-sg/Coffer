## 1. Backend

- [x] 1.1 Runtime reports a start still pending; a disabled channel forgets its start failure; tests
- [x] 1.2 Channel status and `GET /channels/{uid}/status` carry `starting`; the attention source skips it; tests

## 2. Frontend

- [x] 2.1 Channel state reads `starting` (or a status that predates the enable) as connecting; test
