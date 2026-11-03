## 1. Git source

- [x] 1.1 Prefetch a subpath's missing objects in one `fetch --stdin` before the checkout; no auto gc, maintenance or commit-graph writes
- [x] 1.2 Fall back once to a clone without the filter on a missing-object error
- [x] 1.3 Hold one Git source operation to 300 s; kill git processes on cancellation
- [x] 1.4 Tests over a `file://` upstream that serves the filter

## 2. CLI

- [x] 2.1 Per-command wait (`RouteCommand.wait`), separate connect timeout, `--request-timeout`
- [x] 2.2 Tell unreachable, connection lost and no answer in time apart
- [x] 2.3 Deterministic slow-server tests

## 3. Docs

- [x] 3.1 ADRs, specs, error codes, skills guide, troubleshooting, CLI reference (en, zh)
