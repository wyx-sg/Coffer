## 1. Stall watch

- [x] 1.1 `application/runtime/stall_watch.py`: armed by the lag probe before each sleep; logs `runtime.loop.stalled` with stack and task on a missed deadline, rate-limited
- [x] 1.2 Unit tests: a blocked loop is logged with the blocking frame and the task name; a loop that keeps up logs nothing; repeated stalls are rate-limited

## 2. Tasks by name

- [x] 2.1 `TaskSupervisor.running_by_name()`; `tasks_by_name` on the status `runtime` block; `make contracts`
- [x] 2.2 `coffer daemon status --tasks`
- [x] 2.3 Tests: the route counts by prefix and leaks no suffix; the CLI lists counts largest first

## 3. Remove `binary_path`

- [x] 3.1 Stop writing and parsing it; drop it from test fixtures
- [x] 3.2 Installed-build harness reads the executable from `/daemon/status`
- [x] 3.3 Data model and docs (en + zh)
