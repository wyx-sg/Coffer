## 1. Sessions

- [x] 1.1 Readers for OpenCode (1.x and 2.x tables), DeepSeek Harness (session folders + projection) and Cursor (`store.db` meta)
- [x] 1.2 Fallback to the conversations Coffer ran when a store cannot be read; paging stays with the source that issued the cursor
- [x] 1.3 OpenCode delete through its own command; no rename or delete where the agent has no command
- [x] 1.4 Terminal resume for Cursor and OpenCode; session ids may hold `_`
- [x] 1.5 Web UI: row menus leave out what the agent cannot do; the empty tab names each agent's store; no New conversation for an agent without a terminal interface

## 2. Tests

- [x] 2.1 Integration tests over stores built in the agents' shapes, and the fallback
- [x] 2.2 agent-cli: after a real turn, OpenCode 1.x/2.x and DeepSeek Harness list the session from their stores; OpenCode deletes it through its command
- [x] 2.3 Web UI test for the row menus

## 3. Docs

- [x] 3.1 ADR, spec requirement, agents and chat guides (en and zh), support table, TODO entry for the DeepSeek Harness model connection
