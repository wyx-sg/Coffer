## 1. Convention

- [x] 1.1 One opaque cursor codec bound to the list and its filters, `CURSOR_INVALID` on a bad one
- [x] 1.2 Keyset queries with a unique tie-break for audit and invocations

## 2. Lists

- [x] 2.1 Audit log: REST and `coffer log audit --cursor`
- [x] 2.2 Invocation log, per server and across servers: REST and `coffer log mcp --cursor`
- [x] 2.3 Transcript session listing: cursor replaces `offset`
- [x] 2.4 Active and archived conversation listings
- [x] 2.5 Frontend request functions follow the new parameters

## 3. Tests

- [x] 3.1 One test per scenario, and the existing list tests on the new parameters
